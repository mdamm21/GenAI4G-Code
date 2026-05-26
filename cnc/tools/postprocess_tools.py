"""Postprocess tools — convert operation plans to G-code via named postprocessors.

Pipeline:
    1. validate_operation_plan  — reject structurally invalid plans before postprocessing
    2. postprocessor            — deterministic G-code generation
    3. validate_gcode_text      — safety check on the generated G-code
"""

from cnc.postprocessors import POSTPROCESSORS
from cnc.tools.validation_tools import validate_operation_plan
from cnc.validators.gcode_validator import validate_gcode_text


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
        postprocessor: Postprocessor name: "fanuc", "grbl", "marlin", "linuxcnc".

    Returns:
        {
          "ok": bool,
          "gcode": str | None,
          "postprocessor": str,
          "warnings": list[str],
          "errors": list[str],
          "validation": dict,   # G-code validation result (or plan validation on early exit)
        }
    """
    warnings: list[str] = []
    errors: list[str] = []

    # --- 0. Check postprocessor is supported ---
    pp_fn = POSTPROCESSORS.get(postprocessor)
    if pp_fn is None:
        supported = list(POSTPROCESSORS.keys())
        return {
            "ok": False,
            "gcode": None,
            "postprocessor": postprocessor,
            "warnings": warnings,
            "errors": [
                f"Postprocessor '{postprocessor}' not supported. "
                f"Available: {supported}"
            ],
            "validation": {"ok": False, "errors": [], "warnings": []},
        }

    # --- 1. Validate operation plan ---
    plan_val = validate_operation_plan(operation_plan)

    if plan_val.get("errors"):
        # Hard errors — do not attempt postprocessing
        return {
            "ok": False,
            "gcode": None,
            "postprocessor": postprocessor,
            "warnings": plan_val.get("warnings", []),
            "errors": plan_val.get("errors", []),
            "validation": plan_val,
        }

    # Carry plan warnings forward
    warnings.extend(plan_val.get("warnings", []))

    # --- 2. Run postprocessor ---
    try:
        gcode = pp_fn(operation_plan)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gcode": None,
            "postprocessor": postprocessor,
            "warnings": warnings,
            "errors": [f"Postprocessor '{postprocessor}' raised an exception: {exc}"],
            "validation": plan_val,
        }

    # --- 3. Validate generated G-code ---
    machine_type = operation_plan.get("machine_type") or "mill"
    gcode_val = validate_gcode_text(gcode, machine_type=machine_type)

    errors.extend(gcode_val.get("errors", []))
    warnings.extend(gcode_val.get("warnings", []))

    ok = len(errors) == 0
    return {
        "ok": ok,
        "gcode": gcode,
        "postprocessor": postprocessor,
        "warnings": warnings,
        "errors": errors,
        "validation": gcode_val,
    }
