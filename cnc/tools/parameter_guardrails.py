"""Parameter Guardrails v0 — plausibility and context checks for OperationPlans.

Guardrails do NOT generate G-code. They do NOT modify the plan. They do NOT
derive or suggest cutting parameters. They evaluate the plan for common
problems and material-related context, and return structured findings.

Public API:
    evaluate_parameter_guardrails(operation_plan, material) → dict
"""

from __future__ import annotations


def _finding(
    severity: str,
    code: str,
    message: str,
    operation_index: int | None = None,
) -> dict:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "operation_index": operation_index,
    }


def evaluate_parameter_guardrails(
    operation_plan: dict,
    material: str | None = None,
) -> dict:
    """Evaluate parameter plausibility and material context for an OperationPlan.

    Does NOT modify the plan. Does NOT generate or alter G-code.
    Does NOT derive feedrate, spindle_speed, step_down, or step_over.

    Args:
        operation_plan: OperationPlan dict to evaluate.
        material:       Optional material name/ID override.
                        If None, falls back to ``operation_plan.get("material")``.

    Returns:
        {
          "ok":       bool,   (True when no errors; warnings are allowed)
          "errors":   list[str],
          "warnings": list[str],
          "info":     list[str],
          "material": dict | None,
          "findings": list[dict],
        }

        Each finding dict:
        {
          "severity":        "info" | "warning" | "error",
          "code":            str,
          "message":         str,
          "operation_index": int | None,
        }
    """
    from cnc.tools.material_library import normalize_material

    findings: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if not isinstance(operation_plan, dict):
        err = "evaluate_parameter_guardrails: operation_plan must be a dict."
        errors.append(err)
        findings.append(_finding("error", "INVALID_PLAN_TYPE", err))
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "material": None,
            "findings": findings,
        }

    # ------------------------------------------------------------------
    # Resolve material
    # ------------------------------------------------------------------
    resolved_material_str = material or operation_plan.get("material")
    mat_result = normalize_material(resolved_material_str)
    material_info: dict | None = mat_result.get("material")

    # Material warnings
    if not resolved_material_str:
        w = "Material was not specified."
        warnings.append(w)
        findings.append(_finding("warning", "NO_MATERIAL", w))
    elif not mat_result.get("ok"):
        for w in mat_result.get("warnings", []):
            warnings.append(w)
            findings.append(_finding("warning", "UNKNOWN_MATERIAL", w))
    else:
        # Known material — add info
        mat_name = material_info.get("name", resolved_material_str) if material_info else resolved_material_str
        msg = f"Material resolved: {mat_name!r}."
        info.append(msg)
        findings.append(_finding("info", "MATERIAL_RESOLVED", msg))

    # ------------------------------------------------------------------
    # Material category-specific warnings
    # ------------------------------------------------------------------
    if material_info:
        cat = material_info.get("category", "")
        if cat == "stainless_steel":
            w = "Stainless steel requires conservative, verified cutting parameters."
            warnings.append(w)
            findings.append(_finding("warning", "STAINLESS_STEEL_CAUTION", w))
        elif cat == "wood":
            w = "Wood machining may require dust extraction and fire-risk controls."
            warnings.append(w)
            findings.append(_finding("warning", "WOOD_SAFETY", w))
        elif cat == "plastic":
            w = "Plastic machining may require chip evacuation and heat control."
            warnings.append(w)
            findings.append(_finding("warning", "PLASTIC_HEAT", w))

        # Pass along material's own warnings
        for mw in material_info.get("warnings", []):
            if mw not in warnings:
                warnings.append(mw)
                findings.append(_finding("warning", "MATERIAL_WARNING", mw))

    # ------------------------------------------------------------------
    # Plan-level checks
    # ------------------------------------------------------------------
    safe_z = operation_plan.get("safe_z")
    if safe_z is None:
        e = "Missing required field: safe_z."
        errors.append(e)
        findings.append(_finding("error", "MISSING_SAFE_Z", e))

    # ------------------------------------------------------------------
    # Per-operation checks
    # ------------------------------------------------------------------
    operations = operation_plan.get("operations") or []

    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            continue

        op_type = (op.get("type") or "").strip().lower()
        params = op.get("parameters") or {}

        # -- Material-operation compatibility --
        if material_info and op_type:
            supported = material_info.get("supported_operations", [])
            if supported and op_type not in supported:
                w = (
                    f"Material {material_info.get('name', resolved_material_str)!r} "
                    f"does not list support for operation type '{op_type}'."
                )
                warnings.append(w)
                findings.append(_finding("warning", "UNSUPPORTED_OPERATION", w, i))

        # -- Feedrate --
        if not op.get("feedrate_mmpm") and not op.get("feedrate"):
            e = f"Operation {i} ('{op_type}'): missing required 'feedrate'."
            errors.append(e)
            findings.append(_finding("error", "MISSING_FEEDRATE", e, i))

        # -- Spindle speed --
        if not op.get("spindle_rpm") and not op.get("spindle_speed"):
            w = (
                f"Operation {i} ('{op_type}'): no spindle_speed specified. "
                "Spindle start (M03) will be skipped."
            )
            warnings.append(w)
            findings.append(_finding("warning", "MISSING_SPINDLE", w, i))

        # -- tool_diameter --
        td = params.get("tool_diameter")
        if td is not None and isinstance(td, (int, float)) and td <= 0:
            e = f"Operation {i}: tool_diameter={td} is not positive."
            errors.append(e)
            findings.append(_finding("error", "INVALID_TOOL_DIAMETER", e, i))

        # -- Unusual depth (> 200mm) --
        target_z = params.get("target_z")
        if target_z is None:
            target_z = params.get("z")
        if isinstance(target_z, (int, float)):
            depth_abs = abs(target_z)
            if depth_abs > 200:
                w = (
                    f"Operation {i}: depth ({depth_abs:.3g}) seems unusually large. "
                    "Verify target_z is correct."
                )
                warnings.append(w)
                findings.append(_finding("warning", "UNUSUAL_DEPTH", w, i))

        # -- step_down > total depth --
        step_down = params.get("step_down")
        if (
            isinstance(step_down, (int, float))
            and isinstance(target_z, (int, float))
            and step_down > abs(target_z)
        ):
            w = (
                f"Operation {i}: step_down ({step_down}) > total depth ({abs(target_z)}). "
                "A single pass to target_z will be used."
            )
            warnings.append(w)
            findings.append(_finding("warning", "STEP_DOWN_EXCEEDS_DEPTH", w, i))

        # -- step_over > tool_diameter --
        step_over = params.get("step_over")
        td_val = params.get("tool_diameter")
        if (
            isinstance(step_over, (int, float))
            and isinstance(td_val, (int, float))
            and td_val > 0
            and step_over > td_val
        ):
            w = (
                f"Operation {i}: step_over ({step_over}) > tool_diameter ({td_val}). "
                "May leave uncut material."
            )
            warnings.append(w)
            findings.append(_finding("warning", "STEP_OVER_EXCEEDS_DIAMETER", w, i))

    ok = len(errors) == 0
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "material": material_info,
        "findings": findings,
    }
