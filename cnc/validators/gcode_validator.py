"""G-code validator — static analysis of G-code text for safety and completeness.

Thin wrapper around analyze_gcode_safety that preserves the existing API.
"""

from cnc.validators.safety_analyzer import analyze_gcode_safety


def validate_gcode_text(gcode: str, machine_type: str = "mill") -> dict:
    """Validate a G-code program text.

    Args:
        gcode: Raw G-code string to validate.
        machine_type: Target machine type (mill, lathe, laser, 3d_printer, ...).

    Returns:
        {
          "ok": bool,
          "errors": list[str],
          "warnings": list[str],
          "machine_type": str,
          "risk_level": str,        # "low", "medium", or "high"
          "summary": dict,          # structured program summary
          "findings": list[dict],   # structured findings with severity/code/line/message
        }
    """
    result = analyze_gcode_safety(gcode, machine_type=machine_type)
    result["machine_type"] = machine_type
    return result
