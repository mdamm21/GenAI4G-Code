"""Job I/O tools — create, validate, save, load, and postprocess CNC job specs.

A CNCJobSpec is a reproducible JSON container that bundles:
  - operation_plan  (the technical truth)
  - machine_profile
  - material
  - tool_ids
  - postprocessor
  - metadata

G-code is NEVER stored in a job spec.  It is always regenerated
deterministically from ``operation_plan`` via ``job_spec_to_gcode``.
"""

from __future__ import annotations

import copy
import json
import uuid

from cnc.tools.machine_profiles import get_machine_profile
from cnc.tools.material_library import normalize_material
from cnc.tools.parameter_guardrails import evaluate_parameter_guardrails
from cnc.tools.postprocess_tools import postprocess_operations
from cnc.tools.validation_tools import validate_operation_plan

# Tool library may not exist in all installations — import defensively.
try:
    from cnc.tools.tool_library import get_tool as _get_tool  # type: ignore
    from cnc.tools.tool_library import resolve_operation_plan_tools as _resolve_op_tools  # type: ignore
    _HAS_TOOL_LIBRARY = True
except ImportError:
    _HAS_TOOL_LIBRARY = False


# ---------------------------------------------------------------------------
# create_job_spec
# ---------------------------------------------------------------------------

def create_job_spec(
    operation_plan: dict,
    name: str | None = None,
    description: str | None = None,
    machine_profile: str | None = None,
    material: str | None = None,
    tool_ids: list[str] | None = None,
    postprocessor: str = "fanuc",
    metadata: dict | None = None,
) -> dict:
    """Create a CNCJobSpec-compatible dict from an OperationPlan.

    G-code fields on ``operation_plan`` are stripped and a warning is added.
    Returns a plain dict (not a Pydantic model instance) so callers do not
    need to import the schema.
    """
    warnings: list[str] = []

    # Deep-copy so we never mutate the caller's dict.
    op = copy.deepcopy(operation_plan) if isinstance(operation_plan, dict) else {}

    # Strip any gcode field — G-code must never be persisted in a job spec.
    if "gcode" in op:
        op.pop("gcode")
        warnings.append(
            "Stored gcode field stripped from operation_plan; "
            "G-code will be regenerated from operation_plan."
        )

    # Resolve machine_type from operation_plan.
    machine_type = op.get("machine_type")

    # Resolve material: explicit arg wins, then operation_plan.
    resolved_material = material if material is not None else op.get("material")

    # Resolve tool_ids: explicit arg wins, then extract from op["tools"].
    if tool_ids is not None:
        resolved_tool_ids = list(tool_ids)
    else:
        tools_list = op.get("tools", [])
        resolved_tool_ids = [
            str(t["id"])
            for t in tools_list
            if isinstance(t, dict) and "id" in t
        ]

    # Carry over assumptions / warnings / missing_info from the operation_plan.
    op_assumptions = list(op.get("assumptions", []))
    op_warnings = list(op.get("warnings", []))
    op_missing_info = list(op.get("missing_info", []))

    job: dict = {
        "schema_version": "0.1",
        "job_id": str(uuid.uuid4()),
        "name": name,
        "description": description,
        "machine_type": machine_type,
        "machine_profile": machine_profile,
        "postprocessor": postprocessor,
        "material": resolved_material,
        "tool_ids": resolved_tool_ids,
        "operation_plan": op,
        "assumptions": op_assumptions,
        "warnings": op_warnings + warnings,
        "missing_info": op_missing_info,
        "metadata": copy.deepcopy(metadata) if metadata else {},
    }
    return job


# ---------------------------------------------------------------------------
# validate_job_spec
# ---------------------------------------------------------------------------

def validate_job_spec(job: dict) -> dict:
    """Validate a CNCJobSpec dict without generating G-code.

    Returns::

        {
          "ok": bool,
          "errors": list[str],
          "warnings": list[str],
          "job": dict | None,
          "operation_plan_validation": dict | None,
          "guardrails": dict | None,
        }
    """
    errors: list[str] = []
    warnings: list[str] = []
    op_validation: dict | None = None
    guardrails: dict | None = None

    if not isinstance(job, dict):
        return {
            "ok": False,
            "errors": ["job must be a dict."],
            "warnings": [],
            "job": None,
            "operation_plan_validation": None,
            "guardrails": None,
        }

    # --- schema_version ---
    if "schema_version" not in job:
        errors.append("Missing required field: schema_version.")

    # --- operation_plan ---
    op = job.get("operation_plan")
    if op is None:
        errors.append("Missing required field: operation_plan.")
    elif not isinstance(op, dict):
        errors.append("operation_plan must be a dict.")
        op = None

    # --- machine_type consistency ---
    job_mt = job.get("machine_type")
    if op and job_mt:
        op_mt = op.get("machine_type")
        if op_mt and op_mt != job_mt:
            errors.append(
                f"machine_type mismatch: job says '{job_mt}' "
                f"but operation_plan says '{op_mt}'."
            )

    # --- postprocessor ---
    pp = job.get("postprocessor")
    if not pp:
        errors.append("Missing required field: postprocessor.")

    # --- machine_profile ---
    profile_name = job.get("machine_profile")
    if profile_name:
        profile = get_machine_profile(profile_name)
        if profile is None:
            warnings.append(f"Unknown machine_profile: '{profile_name}'.")
        else:
            # Check machine_type consistency with profile.
            if job_mt and profile.get("machine_type") and profile["machine_type"] != job_mt:
                warnings.append(
                    f"machine_profile '{profile_name}' is for machine_type "
                    f"'{profile['machine_type']}' but job specifies '{job_mt}'."
                )

    # --- material ---
    material = job.get("material")
    if material:
        mat_result = normalize_material(material)
        if not mat_result["ok"]:
            for w in mat_result.get("warnings", []):
                warnings.append(w)

    # --- tool_ids ---
    if _HAS_TOOL_LIBRARY:
        for tid in job.get("tool_ids", []):
            tool = _get_tool(tid)
            if tool is None:
                warnings.append(f"Unknown tool_id: '{tid}'.")

        # Resolve tool references inside the operation_plan.
        if op is not None:
            try:
                op_tool_resolution = _resolve_op_tools(op)
                for w in op_tool_resolution.get("warnings", []):
                    warnings.append(f"tool_resolution: {w}")
                for e in op_tool_resolution.get("errors", []):
                    errors.append(f"tool_resolution: {e}")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"tool resolution raised exception: {exc}")

    # --- validate operation_plan ---
    if op is not None:
        try:
            op_validation = validate_operation_plan(op)
            for e in op_validation.get("errors", []):
                errors.append(f"operation_plan: {e}")
            for w in op_validation.get("warnings", []):
                warnings.append(f"operation_plan: {w}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"operation_plan validation raised exception: {exc}")

    # --- guardrails ---
    if op is not None:
        try:
            guardrails = evaluate_parameter_guardrails(op, material=material)
            for e in guardrails.get("errors", []):
                errors.append(f"guardrails: {e}")
            # Guardrail warnings are informational — don't double-count them
            # as job-level warnings; they are available in guardrails["warnings"].
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"guardrails evaluation raised exception: {exc}")

    ok = len(errors) == 0
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "job": job if ok else None,
        "operation_plan_validation": op_validation,
        "guardrails": guardrails,
    }


# ---------------------------------------------------------------------------
# job_spec_to_gcode
# ---------------------------------------------------------------------------

def job_spec_to_gcode(job: dict) -> dict:
    """Regenerate deterministic G-code from a CNCJobSpec dict.

    Any stored ``gcode`` field on the job or its operation_plan is ignored.
    G-code is always produced by the postprocessor pipeline.

    Returns::

        {
          "ok": bool,
          "gcode": str,
          "job": dict,
          "validation": dict,
          "warnings": list[str],
          "errors": list[str],
          "postprocessor": str,
          "safety_report": dict | None,
        }
    """
    warnings: list[str] = []
    errors: list[str] = []

    if not isinstance(job, dict):
        return {
            "ok": False,
            "gcode": "",
            "job": job,
            "validation": {},
            "warnings": warnings,
            "errors": ["job must be a dict."],
            "postprocessor": "fanuc",
            "safety_report": None,
        }

    # Warn if a stored gcode field is present anywhere in the job.
    if "gcode" in job:
        warnings.append(
            "Stored gcode field ignored; regenerating from operation_plan."
        )
    op = job.get("operation_plan") or {}
    if "gcode" in op:
        warnings.append(
            "Stored gcode field on operation_plan ignored; "
            "regenerating from operation_plan."
        )

    postprocessor = job.get("postprocessor") or "fanuc"

    # Validate before generating.
    val_result = validate_job_spec(job)
    if not val_result["ok"]:
        errors.extend(val_result["errors"])
        warnings.extend(val_result["warnings"])
        return {
            "ok": False,
            "gcode": "",
            "job": job,
            "validation": val_result,
            "warnings": warnings,
            "errors": errors,
            "postprocessor": postprocessor,
            "safety_report": None,
        }

    warnings.extend(val_result["warnings"])

    # Generate G-code deterministically.
    try:
        pp_result = postprocess_operations(op, postprocessor=postprocessor)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gcode": "",
            "job": job,
            "validation": val_result,
            "warnings": warnings,
            "errors": [f"postprocessor raised exception: {exc}"],
            "postprocessor": postprocessor,
            "safety_report": None,
        }

    ok = pp_result.get("ok", False)
    gcode = pp_result.get("gcode", "")
    pp_errors = pp_result.get("errors", [])
    pp_warnings = pp_result.get("warnings", [])
    errors.extend(pp_errors)
    warnings.extend(pp_warnings)

    # Build safety_report from postprocess result.
    safety_val = pp_result.get("validation") or {}
    safety_report: dict | None = None
    if safety_val:
        safety_report = {
            "risk_level": safety_val.get("risk_level", "low"),
            "summary": safety_val.get("summary", {}),
            "findings": safety_val.get("findings", []),
        }

    return {
        "ok": ok and len(errors) == 0,
        "gcode": gcode if ok else "",
        "job": job,
        "validation": val_result,
        "warnings": warnings,
        "errors": errors,
        "postprocessor": postprocessor,
        "safety_report": safety_report,
    }


# ---------------------------------------------------------------------------
# save_job_spec / load_job_spec
# ---------------------------------------------------------------------------

def save_job_spec(job: dict, path: str) -> dict:
    """Serialise a CNCJobSpec dict to a UTF-8 JSON file.

    Returns::

        {"ok": bool, "path": str, "errors": list[str], "warnings": list[str]}
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(job, dict):
        return {
            "ok": False,
            "path": path,
            "errors": ["job must be a dict."],
            "warnings": [],
        }

    # Warn if someone tries to persist a gcode field.
    if "gcode" in job:
        warnings.append(
            "gcode field found in job — it will be saved as-is. "
            "Note: stored G-code is ignored on load; "
            "always regenerate via job_spec_to_gcode."
        )

    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(job, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        errors.append(f"Could not write file '{path}': {exc}")
    except TypeError as exc:
        errors.append(f"Job is not JSON-serialisable: {exc}")

    return {
        "ok": len(errors) == 0,
        "path": path,
        "errors": errors,
        "warnings": warnings,
    }


def load_job_spec(path: str) -> dict:
    """Load a CNCJobSpec dict from a UTF-8 JSON file.

    Returns::

        {
          "ok": bool,
          "job": dict | None,
          "path": str,
          "errors": list[str],
          "warnings": list[str],
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {
            "ok": False,
            "job": None,
            "path": path,
            "errors": [f"File not found: '{path}'."],
            "warnings": [],
        }
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "job": None,
            "path": path,
            "errors": [f"Invalid JSON in '{path}': {exc}"],
            "warnings": [],
        }
    except OSError as exc:
        return {
            "ok": False,
            "job": None,
            "path": path,
            "errors": [f"Could not read file '{path}': {exc}"],
            "warnings": [],
        }

    if not isinstance(data, dict):
        return {
            "ok": False,
            "job": None,
            "path": path,
            "errors": ["File does not contain a JSON object at the top level."],
            "warnings": [],
        }

    # Warn if a stored gcode field is present.
    if "gcode" in data:
        warnings.append(
            "Loaded job contains a 'gcode' field. "
            "It will be ignored — use job_spec_to_gcode to regenerate G-code."
        )

    return {
        "ok": True,
        "job": data,
        "path": path,
        "errors": errors,
        "warnings": warnings,
    }
