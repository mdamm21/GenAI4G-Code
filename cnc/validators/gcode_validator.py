"""G-code validator — static analysis of G-code text for safety and completeness."""

import re


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
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Basic checks ---
    if not gcode or not gcode.strip():
        errors.append("G-code is empty.")
        return {"ok": False, "errors": errors, "warnings": warnings, "machine_type": machine_type}

    lines = [ln.strip() for ln in gcode.splitlines()]
    upper = gcode.upper()

    # --- Unit declaration ---
    has_g20 = bool(re.search(r"\bG20\b", upper))
    has_g21 = bool(re.search(r"\bG21\b", upper))
    if not has_g20 and not has_g21:
        warnings.append("No unit declaration found (G20 inches / G21 mm). Assumed mm.")

    # --- Positioning mode ---
    has_g90 = bool(re.search(r"\bG90\b", upper))
    has_g91 = bool(re.search(r"\bG91\b", upper))
    if not has_g90 and not has_g91:
        warnings.append("No positioning mode found (G90 absolute / G91 incremental). Assumed G90.")

    # --- Feedrate ---
    has_feedrate = bool(re.search(r"\bF[\d.]+", upper))
    if not has_feedrate:
        warnings.append("No feedrate (F<value>) found in program.")

    # --- Program end ---
    has_m30 = bool(re.search(r"\bM30\b", upper))
    has_m02 = bool(re.search(r"\bM02\b", upper))
    if not has_m30 and not has_m02:
        warnings.append("No program end command found (M30 or M02).")

    # --- Machine-type specific checks ---
    if machine_type in ("mill", "lathe", "drill", "grinder"):
        has_spindle_on = bool(re.search(r"\bM0[34]\b", upper))
        has_spindle_off = bool(re.search(r"\bM05\b", upper))
        if not has_spindle_on:
            warnings.append("No spindle start command (M03/M04) found.")
        if has_spindle_on and not has_spindle_off:
            warnings.append("Spindle is started (M03/M04) but never stopped (M05) before program end.")

    if machine_type == "laser":
        has_laser_on = bool(re.search(r"\bM0[34]\b", upper))
        if not has_laser_on:
            warnings.append("No laser enable command (M03/M04) found for laser machine type.")

    if machine_type == "3d_printer":
        has_temp = bool(re.search(r"\bM10[49]\b", upper))  # M104/M109 hotend temp
        if not has_temp:
            warnings.append("No hotend temperature command (M104/M109) found for 3D printer.")

    # --- Dangerous patterns ---
    # G00 rapid into potentially non-zero Z without prior retract
    rapid_z_down = re.findall(r"G0+\s+Z-[\d.]+", upper)
    if rapid_z_down:
        errors.append(
            f"Rapid move (G00) to negative Z detected ({len(rapid_z_down)}x). "
            "Never rapid into workpiece — use G01 for plunge moves."
        )

    # Spindle active near program end without M05
    if machine_type not in ("laser", "3d_printer"):
        last_spindle_on = max(
            (i for i, ln in enumerate(lines) if re.search(r"\bM0[34]\b", ln.upper())),
            default=-1,
        )
        last_spindle_off = max(
            (i for i, ln in enumerate(lines) if re.search(r"\bM05\b", ln.upper())),
            default=-1,
        )
        if last_spindle_on > last_spindle_off:
            warnings.append(
                "Last spindle-on command (M03/M04) appears after last spindle-off (M05). "
                "Ensure spindle is stopped before program end."
            )

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings, "machine_type": machine_type}
