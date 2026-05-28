"""G-code Pipeline — deterministic regeneration from OperationPlan.

Architecture principle:
    Agents plan.  OperationPlan is the truth.
    Postprocessor generates final G-code deterministically.
    Agent-generated G-code text is NEVER trusted as final output.

Public API:
    regenerate_gcode_from_operation_plan(result, ...)

Usage:
    from cnc.tools.gcode_pipeline import regenerate_gcode_from_operation_plan
    result = regenerate_gcode_from_operation_plan(agent_result)
"""

from __future__ import annotations


def regenerate_gcode_from_operation_plan(
    result: dict,
    default_postprocessor: str = "fanuc",
    allow_plan_list_first_item: bool = True,
) -> dict:
    """Regenerate G-code deterministically from result["operation_plan"].

    Agent-provided ``result["gcode"]`` is always discarded when an
    ``operation_plan`` is present — LLMs may abbreviate or truncate long
    G-code blocks.  This function is the single authoritative path:

        operation_plan → validate_operation_plan → postprocess_operations

    Args:
        result:
            A dict (e.g. the return value of ``CNCAgent.run()`` or a dict
            built by the MCP server).  Must contain ``"operation_plan"``.
        default_postprocessor:
            Postprocessor to use when neither ``result`` nor
            ``operation_plan`` specifies one.  Defaults to ``"fanuc"``.
        allow_plan_list_first_item:
            When ``operation_plan`` is a *list*, use the first element if
            ``True`` (with a warning).  If ``False`` and the list has more
            than one item, return an error instead.

    Returns:
        Updated copy of ``result`` with:

        - ``gcode``         — deterministically regenerated G-code string
                              (or empty string on error)
        - ``operation_plan``— normalised single plan dict (or original)
        - ``validation``    — validation result dict
        - ``warnings``      — accumulated warnings
        - ``errors``        — accumulated errors
        - ``postprocessor`` — resolved postprocessor name
        - ``ok``            — True only if G-code was generated without errors

        Never raises; exceptions are captured and returned as errors.
    """
    # ------------------------------------------------------------------
    # Guard: result must be a dict
    # ------------------------------------------------------------------
    if not isinstance(result, dict):
        return {
            "ok": False,
            "gcode": "",
            "operation_plan": None,
            "validation": {
                "ok": False,
                "errors": [
                    f"regenerate_gcode_from_operation_plan: result must be a dict, "
                    f"got {type(result).__name__}."
                ],
                "warnings": [],
            },
            "warnings": [],
            "errors": [
                f"regenerate_gcode_from_operation_plan: result must be a dict, "
                f"got {type(result).__name__}."
            ],
            "postprocessor": default_postprocessor,
        }

    try:
        # Work on a shallow copy so we never mutate the caller's dict.
        result = dict(result)

        warnings: list[str] = list(result.get("warnings") or [])
        errors: list[str] = list(result.get("errors") or [])

        # ------------------------------------------------------------------
        # No operation_plan → skip regeneration
        # ------------------------------------------------------------------
        op = result.get("operation_plan")

        if op is None:
            result["warnings"] = warnings + [
                "No operation_plan found; deterministic G-code regeneration skipped."
            ]
            return result

        # ------------------------------------------------------------------
        # Handle operation_plan as list
        # ------------------------------------------------------------------
        if isinstance(op, list):
            if len(op) == 0:
                result["gcode"] = ""
                result["errors"] = errors + [
                    "operation_plan was returned as an empty list; cannot regenerate G-code."
                ]
                result["warnings"] = warnings
                result["ok"] = False
                return result

            if len(op) == 1:
                op = op[0]
                warnings = warnings + [
                    "operation_plan was returned as a list; using the first item."
                ]
            else:
                # Multiple plans in list
                if allow_plan_list_first_item:
                    op = op[0]
                    warnings = warnings + [
                        "operation_plan contained multiple plans; using the first item only."
                    ]
                else:
                    result["gcode"] = ""
                    result["errors"] = errors + [
                        "operation_plan contained multiple plans and "
                        "allow_plan_list_first_item=False; cannot regenerate G-code."
                    ]
                    result["warnings"] = warnings
                    result["ok"] = False
                    return result

        # ------------------------------------------------------------------
        # operation_plan must now be a dict
        # ------------------------------------------------------------------
        if not isinstance(op, dict):
            result["gcode"] = ""
            result["errors"] = errors + [
                f"operation_plan must be a dict, got {type(op).__name__}."
            ]
            result["warnings"] = warnings
            result["ok"] = False
            return result

        # ------------------------------------------------------------------
        # Discard existing agent-provided G-code
        # ------------------------------------------------------------------
        existing_gcode = result.get("gcode", "")
        if existing_gcode:
            warnings = warnings + [
                "Agent-provided gcode was discarded and regenerated "
                "deterministically from operation_plan."
            ]

        # ------------------------------------------------------------------
        # Resolve postprocessor
        # Priority: result["postprocessor"] > operation_plan["postprocessor"]
        #           > default_postprocessor
        # ------------------------------------------------------------------
        resolved_pp: str = (
            result.get("postprocessor")
            or op.get("postprocessor")
            or default_postprocessor
        )

        # ------------------------------------------------------------------
        # Validate operation_plan
        # ------------------------------------------------------------------
        from cnc.tools.validation_tools import validate_operation_plan

        plan_val = validate_operation_plan(op)

        if plan_val.get("errors"):
            result["gcode"] = ""
            result["operation_plan"] = op
            result["validation"] = plan_val
            result["warnings"] = warnings + list(plan_val.get("warnings", []))
            result["errors"] = errors + list(plan_val.get("errors", []))
            result["postprocessor"] = resolved_pp
            result["ok"] = False
            return result

        # ------------------------------------------------------------------
        # Postprocess → deterministic G-code
        # ------------------------------------------------------------------
        from cnc.tools.postprocess_tools import postprocess_operations

        pp = postprocess_operations(op, postprocessor=resolved_pp)

        result["operation_plan"] = op
        result["postprocessor"] = resolved_pp

        pp_warnings = list(plan_val.get("warnings", [])) + list(pp.get("warnings", []))

        if pp.get("ok") and pp.get("gcode"):
            result["gcode"] = pp["gcode"]
            result["validation"] = pp.get("validation", plan_val)
            result["ok"] = True
            result["warnings"] = warnings + pp_warnings
            result["errors"] = []
        else:
            result["gcode"] = ""
            result["validation"] = pp.get("validation", plan_val)
            result["ok"] = False
            result["warnings"] = warnings + pp_warnings
            result["errors"] = errors + list(pp.get("errors", []))

        return result

    except Exception as exc:  # noqa: BLE001
        # Never let an exception escape — capture and report it
        safe_errors = list(result.get("errors") or []) if isinstance(result, dict) else []
        safe_result = dict(result) if isinstance(result, dict) else {}
        safe_result.update({
            "ok": False,
            "gcode": "",
            "errors": safe_errors + [
                f"regenerate_gcode_from_operation_plan: unexpected exception: {exc}"
            ],
        })
        return safe_result
