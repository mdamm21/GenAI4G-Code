"""Postprocess tools — convert operation plans to G-code via named postprocessors.

Pipeline:
    1. validate_operation_plan  — reject structurally invalid plans before postprocessing
    2. postprocessor            — deterministic G-code generation
    3. validate_gcode_text      — safety check on the generated G-code

Supported postprocessors: fanuc, grbl, linuxcnc, marlin.
- fanuc / grbl / linuxcnc: full pipeline (validate → generate → validate gcode)
- marlin: stub only; returns ok=False for all machine types until implemented
"""

from cnc.postprocessors import POSTPROCESSORS
from cnc.tools.validation_tools import validate_operation_plan
from cnc.validators.gcode_validator import validate_gcode_text

# Postprocessors that run the full CNC pipeline
_CNC_POSTPROCESSORS = {"fanuc", "grbl", "linuxcnc"}


def postprocess_operations(
    operation_plan: dict,
    postprocessor: str = "fanuc",
) -> dict:
    """Run an operation plan through the named postprocessor.

    The plan is validated before postprocessing and the resulting G-code is
    validated after. If the plan has errors the postprocessor is not called and
    no G-code is returned.

    Args:
        operation_plan: Structured operation plan dict (matches OperationPlan schema).
        postprocessor:  Postprocessor name: "fanuc", "grbl", "linuxcnc", "marlin".

    Returns:
        {
          "ok":           bool,
          "gcode":        str,
          "postprocessor": str,
          "warnings":     list[str],
          "errors":       list[str],
          "validation":   dict,
        }
    """
    _empty_val = {"ok": False, "errors": [], "warnings": []}

    # --- 0. Check postprocessor is known ---
    if postprocessor not in POSTPROCESSORS:
        supported = sorted(POSTPROCESSORS.keys())
        return {
            "ok": False,
            "gcode": "",
            "postprocessor": postprocessor,
            "warnings": [],
            "errors": [
                f"Unsupported postprocessor: '{postprocessor}'. "
                f"Supported: {supported}"
            ],
            "validation": _empty_val,
        }

    # --- 1. Marlin — always a stub; never generates CNC motion ---
    if postprocessor == "marlin":
        machine_type_val = operation_plan.get("machine_type", "")
        if machine_type_val == "3d_printer":
            return {
                "ok": False,
                "gcode": "",
                "postprocessor": postprocessor,
                "warnings": [],
                "errors": ["Marlin 3D-printing postprocessor is not implemented yet."],
                "validation": _empty_val,
            }
        return {
            "ok": False,
            "gcode": "",
            "postprocessor": postprocessor,
            "warnings": [],
            "errors": [
                f"Marlin postprocessor is not supported for machine_type: '{machine_type_val}'. "
                "Use fanuc, grbl, or linuxcnc for CNC operations."
            ],
            "validation": _empty_val,
        }

    # --- 2. Validate operation plan (for CNC postprocessors) ---
    plan_val = validate_operation_plan(operation_plan)

    if plan_val.get("errors"):
        return {
            "ok": False,
            "gcode": "",
            "postprocessor": postprocessor,
            "warnings": plan_val.get("warnings", []),
            "errors": plan_val.get("errors", []),
            "validation": plan_val,
        }

    warnings: list[str] = list(plan_val.get("warnings", []))

    # --- 3. Run postprocessor ---
    pp_fn = POSTPROCESSORS[postprocessor]
    try:
        gcode = pp_fn(operation_plan)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gcode": "",
            "postprocessor": postprocessor,
            "warnings": warnings,
            "errors": [f"Postprocessor '{postprocessor}' raised an exception: {exc}"],
            "validation": plan_val,
        }

    # --- 4. Validate generated G-code ---
    machine_type = operation_plan.get("machine_type") or "mill"
    gcode_val = validate_gcode_text(gcode, machine_type=machine_type)

    errors: list[str] = list(gcode_val.get("errors", []))
    warnings.extend(gcode_val.get("warnings", []))

    return {
        "ok": len(errors) == 0,
        "gcode": gcode,
        "postprocessor": postprocessor,
        "warnings": warnings,
        "errors": errors,
        "validation": gcode_val,
        "risk_level": gcode_val.get("risk_level", "low"),
        "safety_summary": gcode_val.get("summary", {}),
        "findings": gcode_val.get("findings", []),
    }
