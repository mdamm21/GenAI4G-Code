"""Postprocess tools — convert operation plans to G-code via named postprocessors."""

from cnc.postprocessors import POSTPROCESSORS


def postprocess_operations(
    operation_plan: dict,
    postprocessor: str = "fanuc",
) -> dict:
    """Run an operation plan through the named postprocessor.

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
        }
    """
    warnings: list[str] = []
    errors: list[str] = []

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
        }

    try:
        gcode = pp_fn(operation_plan)
        return {
            "ok": True,
            "gcode": gcode,
            "postprocessor": postprocessor,
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return {
            "ok": False,
            "gcode": None,
            "postprocessor": postprocessor,
            "warnings": warnings,
            "errors": [f"Postprocessor error: {exc}"],
        }
