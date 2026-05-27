"""G-code Safety Analyzer v1 — structured static analysis of G-code programs.

This analyzer extracts structural information from G-code and identifies
obvious safety and completeness issues. It does NOT simulate machine motion,
does NOT guarantee machine safety, and does NOT replace expert review.

All results should be treated as advisory only.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Known G and M codes (normalized — no leading zeros)
# Not-in-this-list → unsupported_commands (warning only unless allowed_commands set)
# ---------------------------------------------------------------------------

_KNOWN_GCODES: frozenset[str] = frozenset({
    "0", "1", "2", "3",                        # basic motion
    "17", "18", "19",                           # plane selection
    "20", "21",                                 # units
    "28",                                       # home
    "40", "41", "42",                           # cutter comp
    "43", "44", "49",                           # tool length offset
    "54", "55", "56", "57", "58", "59",        # work coordinate systems
    "80", "81", "82", "83", "84", "85",        # canned cycles
    "90", "91",                                 # positioning mode
    "92",                                       # set position
    "94", "95",                                 # feed rate mode
})

_KNOWN_MCODES: frozenset[str] = frozenset({
    "0", "1", "2", "3", "4", "5", "6",        # program control, spindle, tool change
    "7", "8", "9",                              # coolant
    "30",                                       # program end
    "104", "106", "107", "109",                # 3D printer hotend/fan
    "140", "190",                              # 3D printer bed
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Remove parenthetical (...) and semicolon comments from a G-code line."""
    # Remove all (...) blocks (non-greedy, handles multiple per line)
    line = re.sub(r'\([^)]*\)', '', line)
    # Remove ; to end-of-line
    semicolon = line.find(';')
    if semicolon >= 0:
        line = line[:semicolon]
    return line.strip()


def _normalize_code(digits: str) -> str:
    """Strip leading zeros from a numeric code string: '01' → '1', '00' → '0'."""
    try:
        return str(int(digits))
    except ValueError:
        return digits


def _find_gcodes(stripped: str) -> list[str]:
    """Return normalized G-code numbers found on a stripped line."""
    return [_normalize_code(m) for m in re.findall(r'\bG(\d+(?:\.\d+)?)\b', stripped, re.IGNORECASE)]


def _find_mcodes(stripped: str) -> list[str]:
    """Return normalized M-code numbers found on a stripped line."""
    return [_normalize_code(m) for m in re.findall(r'\bM(\d+)\b', stripped, re.IGNORECASE)]


def _find_z_values(stripped: str) -> list[float]:
    """Return Z values (with sign) found on a stripped line."""
    matches = re.findall(r'\bZ\s*(-?[\d.]+)', stripped, re.IGNORECASE)
    result = []
    for m in matches:
        try:
            result.append(float(m))
        except ValueError:
            pass
    return result


def _find_f_values(stripped: str) -> list[float]:
    """Return F (feedrate) values found on a stripped line."""
    matches = re.findall(r'\bF\s*([\d.]+)', stripped, re.IGNORECASE)
    result = []
    for m in matches:
        try:
            result.append(float(m))
        except ValueError:
            pass
    return result


def _find_s_values(stripped: str) -> list[float]:
    """Return S (spindle speed) values found on a stripped line."""
    matches = re.findall(r'\bS\s*([\d.]+)', stripped, re.IGNORECASE)
    result = []
    for m in matches:
        try:
            result.append(float(m))
        except ValueError:
            pass
    return result


def _finding(severity: str, code: str, message: str,
             line: int | None = None, text: str | None = None) -> dict:
    return {
        "severity": severity,
        "code": code,
        "line": line,
        "message": message,
        "text": text,
    }


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------

def analyze_gcode_safety(
    gcode: str,
    machine_type: str = "mill",
    expected_units: str | None = None,
    safe_z: float | None = None,
    max_depth: float | None = None,
    allowed_commands: list[str] | None = None,
) -> dict:
    """Analyze a G-code program for obvious safety and completeness issues.

    This is static analysis only — no machine motion is simulated.
    Results are advisory. Expert review and simulation remain mandatory.

    Args:
        gcode:             G-code program text.
        machine_type:      "mill", "drill", "lathe", "laser", "3d_printer", etc.
        expected_units:    "mm" or "inch" — error if program uses the other unit.
        safe_z:            Expected safe retract height — used for Z-pattern checks.
        max_depth:         Maximum allowed cutting depth (positive number).
                           Error if min_z < -abs(max_depth).
        allowed_commands:  If set, error on any G/M command not in this list.

    Returns:
        {
          "ok": bool,
          "risk_level": "low" | "medium" | "high",
          "errors": list[str],
          "warnings": list[str],
          "summary": dict,
          "findings": list[dict],
        }
    """
    findings: list[dict] = []

    # ------------------------------------------------------------------
    # 0. Basic validation
    # ------------------------------------------------------------------
    if not isinstance(gcode, str) or not gcode.strip():
        f = _finding("error", "EMPTY_GCODE", "G-code is empty or not a string.")
        return _build_result(
            findings=[f],
            machine_type=machine_type,
            summary=_empty_summary(machine_type),
        )

    # ------------------------------------------------------------------
    # 1. Parse line by line
    # ------------------------------------------------------------------
    raw_lines = gcode.splitlines()

    # Collected data
    units_codes: list[str] = []          # "20" or "21"
    positioning_codes: list[str] = []    # "90" or "91"
    wcs_codes: list[str] = []            # "54".."59"
    feedrates: list[float] = []
    spindle_speeds: list[float] = []
    all_gcodes: list[str] = []           # every G code (normalized)
    all_mcodes: list[str] = []           # every M code (normalized)
    z_values_all: list[float] = []       # all Z values seen
    motion_line_count = 0
    unsupported_commands: list[str] = []
    has_e_values = False

    # Per-line tracking for ordering checks
    spindle_on_lines: list[int] = []     # line indices with M3/M4
    spindle_off_lines: list[int] = []    # line indices with M5
    spindle_speed_before_on: dict[int, bool] = {}  # line_idx → had S value

    # For G91 + negative Z pattern
    current_positioning = "absolute"  # assume absolute until G91 seen
    has_g91 = False

    # Rapid Z-negative tracking
    rapid_z_neg_lines: list[int] = []

    line_count = len(raw_lines)
    last_s_value: float | None = None

    for line_idx, raw_line in enumerate(raw_lines):
        line_num = line_idx + 1
        stripped = _strip_comment(raw_line)
        if not stripped:
            continue

        # Extract components
        gcodes = _find_gcodes(stripped)
        mcodes = _find_mcodes(stripped)
        z_vals = _find_z_values(stripped)
        f_vals = _find_f_values(stripped)
        s_vals = _find_s_values(stripped)

        all_gcodes.extend(gcodes)
        all_mcodes.extend(mcodes)
        feedrates.extend(f_vals)
        z_values_all.extend(z_vals)

        if s_vals:
            spindle_speeds.extend(s_vals)
            last_s_value = s_vals[-1]

        # Units
        for g in gcodes:
            if g == "20":
                units_codes.append("20")
            elif g == "21":
                units_codes.append("21")
            elif g in ("90",):
                positioning_codes.append("90")
                current_positioning = "absolute"
            elif g in ("91",):
                positioning_codes.append("91")
                has_g91 = True
                current_positioning = "relative"
            elif g in ("54", "55", "56", "57", "58", "59"):
                wcs_codes.append(g)

        # E values (3D printer extrusion)
        if re.search(r'\bE[-\d.]', stripped, re.IGNORECASE):
            has_e_values = True

        # Motion lines: G0/G1 or F present
        is_motion = bool(set(gcodes) & {"0", "1"}) or bool(f_vals)
        if is_motion:
            motion_line_count += 1

        # Rapid Z-negative check (G0 with negative Z on same line)
        if "0" in gcodes and z_vals:
            for z in z_vals:
                if z < 0:
                    rapid_z_neg_lines.append(line_num)
                    findings.append(_finding(
                        "error", "RAPID_Z_NEGATIVE",
                        f"Rapid move (G00) to negative Z ({z}) detected on line {line_num}. "
                        "Never rapid into workpiece — use G01 for plunge moves.",
                        line=line_num, text=raw_line.strip(),
                    ))

        # Spindle on/off tracking
        for m in mcodes:
            if m in ("3", "4"):
                spindle_on_lines.append(line_num)
                spindle_speed_before_on[line_num] = (last_s_value is not None and last_s_value > 0)
            elif m == "5":
                spindle_off_lines.append(line_num)

        # Unsupported commands check
        for g in gcodes:
            if g not in _KNOWN_GCODES:
                cmd = f"G{g}"
                if cmd not in unsupported_commands:
                    unsupported_commands.append(cmd)
        for m in mcodes:
            if m not in _KNOWN_MCODES:
                cmd = f"M{m}"
                if cmd not in unsupported_commands:
                    unsupported_commands.append(cmd)

        # allowed_commands check
        if allowed_commands is not None:
            allowed_upper = {c.upper() for c in allowed_commands}
            for g in gcodes:
                cmd = f"G{g}"
                if cmd.upper() not in allowed_upper:
                    findings.append(_finding(
                        "error", "DISALLOWED_COMMAND",
                        f"Command {cmd} on line {line_num} is not in the allowed list.",
                        line=line_num, text=raw_line.strip(),
                    ))
            for m in mcodes:
                cmd = f"M{m}"
                if cmd.upper() not in allowed_upper:
                    findings.append(_finding(
                        "error", "DISALLOWED_COMMAND",
                        f"Command {cmd} on line {line_num} is not in the allowed list.",
                        line=line_num, text=raw_line.strip(),
                    ))

    # ------------------------------------------------------------------
    # 2. Compute summary values
    # ------------------------------------------------------------------
    # Units
    has_g20 = "20" in all_gcodes
    has_g21 = "21" in all_gcodes
    if has_g21 and not has_g20:
        units = "mm"
    elif has_g20 and not has_g21:
        units = "inch"
    elif has_g20 and has_g21:
        units = "mixed"
    else:
        units = "unknown"

    # Positioning mode
    has_g90 = "90" in all_gcodes
    if has_g91 and not has_g90:
        positioning_mode = "relative"
    elif has_g90:
        positioning_mode = "absolute"
    else:
        positioning_mode = "unknown"

    # WCS
    wcs = f"G{wcs_codes[0]}" if wcs_codes else None

    # Program end: M2/M02 → "2", M30 → "30"
    has_program_end = "2" in all_mcodes or "30" in all_mcodes

    # Feedrate: any positive feedrate
    positive_feedrates = [f for f in feedrates if f > 0]
    has_feedrate = len(positive_feedrates) > 0

    # Spindle
    has_spindle_start = bool(spindle_on_lines)
    has_spindle_stop = bool(spindle_off_lines)

    # Z stats
    min_z = min(z_values_all) if z_values_all else None
    max_z = max(z_values_all) if z_values_all else None

    summary = {
        "machine_type": machine_type,
        "units": units,
        "positioning_mode": positioning_mode,
        "work_coordinate_system": wcs,
        "has_program_end": has_program_end,
        "has_feedrate": has_feedrate,
        "has_spindle_start": has_spindle_start,
        "has_spindle_stop": has_spindle_stop,
        "line_count": line_count,
        "motion_line_count": motion_line_count,
        "min_z": min_z,
        "max_z": max_z,
        "feedrates": sorted(set(positive_feedrates)),
        "spindle_speeds": sorted(set(s for s in spindle_speeds if s > 0)),
        "unsupported_commands": sorted(unsupported_commands),
    }

    # ------------------------------------------------------------------
    # 3. Cross-field checks (warnings and errors)
    # ------------------------------------------------------------------

    # Info findings
    if units != "unknown":
        findings.append(_finding("info", "UNITS_DETECTED",
            f"Units: {units.upper()} (G{'21' if units == 'mm' else '20'})."))
    if positioning_mode != "unknown":
        findings.append(_finding("info", "POSITIONING_DETECTED",
            f"Positioning mode: {positioning_mode} (G{'90' if positioning_mode == 'absolute' else '91'})."))
    if wcs:
        findings.append(_finding("info", "WCS_DETECTED",
            f"Work coordinate system: {wcs}."))
    if min_z is not None:
        findings.append(_finding("info", "Z_RANGE",
            f"Z range: min={min_z}, max={max_z}."))
    if motion_line_count > 0:
        findings.append(_finding("info", "MOTION_LINES",
            f"Motion lines detected: {motion_line_count}."))

    # --- Errors ---

    # Conflicting units in same program
    if has_g20 and has_g21:
        findings.append(_finding(
            "error", "MIXED_UNITS",
            "Both G20 (inch) and G21 (mm) found in the same program. "
            "Units must be consistent.",
        ))

    # expected_units mismatch
    if expected_units is not None:
        unit_code = "21" if expected_units == "mm" else "20"
        wrong_code = "20" if expected_units == "mm" else "21"
        if wrong_code in all_gcodes and unit_code not in all_gcodes:
            actual = "inch" if wrong_code == "20" else "mm"
            findings.append(_finding(
                "error", "UNITS_MISMATCH",
                f"Units mismatch: expected {expected_units.upper()} (G{unit_code}) "
                f"but found G{wrong_code} ({actual.upper()}).",
            ))

    # Feedrate = 0 or negative
    zero_or_neg_feeds = [f for f in feedrates if f <= 0]
    for bad_f in zero_or_neg_feeds:
        findings.append(_finding(
            "error", "INVALID_FEEDRATE",
            f"Invalid feedrate F{bad_f} detected. Feedrate must be positive (> 0).",
        ))

    # max_depth violation
    if max_depth is not None and min_z is not None:
        if min_z < -abs(float(max_depth)):
            findings.append(_finding(
                "error", "EXCEEDS_MAX_DEPTH",
                f"Minimum Z ({min_z}) exceeds allowed max depth (-{abs(float(max_depth))}). "
                "Program cuts deeper than the configured max_depth.",
            ))

    # --- Warnings ---

    # No unit declaration
    if not has_g20 and not has_g21:
        findings.append(_finding(
            "warning", "NO_UNITS",
            "No unit declaration found (G20 inches / G21 mm). Assumed mm.",
        ))

    # No positioning mode
    if not has_g90 and not has_g91:
        findings.append(_finding(
            "warning", "NO_POSITIONING",
            "No positioning mode found (G90 absolute / G91 incremental). Assumed G90.",
        ))

    # G91 relative positioning
    if has_g91:
        findings.append(_finding(
            "warning", "RELATIVE_POSITIONING",
            "G91 relative positioning detected. Incremental mode can cause unexpected "
            "motion if not properly initialized. Verify all moves are intentional.",
        ))

    # G91 + negative Z together
    if has_g91 and min_z is not None and min_z < 0:
        findings.append(_finding(
            "warning", "G91_NEGATIVE_Z",
            f"Relative positioning (G91) combined with negative Z value ({min_z}). "
            "Incremental Z moves may produce unexpected depth if origin is not correctly set.",
        ))

    # No WCS
    if wcs is None:
        findings.append(_finding(
            "warning", "NO_WCS",
            "No work coordinate system (G54–G59) found. "
            "Ensure correct WCS is active on the machine.",
        ))

    # No feedrate
    if not has_feedrate and not zero_or_neg_feeds:
        findings.append(_finding(
            "warning", "NO_FEEDRATE",
            "No feedrate (F<value>) found in program. "
            "Feed moves require an explicit feedrate.",
        ))

    # No program end
    if not has_program_end:
        findings.append(_finding(
            "warning", "NO_PROGRAM_END",
            "No program end command found (M30 or M02/M2). "
            "Program may not terminate cleanly.",
        ))

    # Unsupported commands
    if unsupported_commands:
        findings.append(_finding(
            "warning", "UNSUPPORTED_COMMANDS",
            f"Unrecognised commands found: {', '.join(unsupported_commands)}. "
            "Verify these are supported by the target controller.",
        ))

    # Machine-type specific checks
    if machine_type in ("mill", "drill", "lathe", "grinder"):
        # No spindle start
        if not has_spindle_start:
            findings.append(_finding(
                "warning", "NO_SPINDLE_START",
                "No spindle start command (M03/M04) found. "
                "Ensure spindle is started before cutting moves.",
            ))
        # Spindle on but no M5
        if has_spindle_start and not has_spindle_stop:
            findings.append(_finding(
                "warning", "SPINDLE_NOT_STOPPED",
                "Spindle is started (M03/M04) but never stopped (M05) before program end. "
                "Ensure spindle is stopped after machining.",
            ))
        # M3/M4 without S value
        if has_spindle_start and not spindle_speeds:
            findings.append(_finding(
                "warning", "SPINDLE_NO_SPEED",
                "Spindle start (M03/M04) found but no S value in program. "
                "Specify spindle speed with S<rpm> before M03/M04.",
            ))
        # Last spindle-on after last spindle-off
        if spindle_on_lines and spindle_off_lines:
            if max(spindle_on_lines) > max(spindle_off_lines):
                findings.append(_finding(
                    "warning", "SPINDLE_ON_AFTER_OFF",
                    "Last spindle-on command (M03/M04) appears after last spindle-off (M05). "
                    "Ensure spindle is stopped before program end.",
                ))

    if machine_type == "laser":
        if not has_spindle_start:
            findings.append(_finding(
                "warning", "NO_LASER_ENABLE",
                "No laser enable command (M03/M04) found for laser machine type.",
            ))

    if machine_type == "3d_printer":
        has_temp = "104" in all_mcodes or "109" in all_mcodes
        if not has_temp:
            findings.append(_finding(
                "warning", "NO_HOTEND_TEMP",
                "No hotend temperature command (M104/M109) found for 3D printer. "
                "Hotend temperature should be set before printing.",
            ))
        if has_e_values and not has_temp:
            findings.append(_finding(
                "warning", "E_WITHOUT_TEMP",
                "E-axis values (extrusion) found but no temperature command (M104/M109). "
                "Ensure hotend is at print temperature before extruding.",
            ))

    # Abnormally deep cuts (heuristic, only when max_depth not set)
    if max_depth is None and min_z is not None:
        threshold = -100.0 if units != "inch" else -4.0
        if min_z < threshold:
            findings.append(_finding(
                "warning", "UNUSUAL_DEPTH",
                f"Minimum Z ({min_z}) is unusually deep. "
                f"Verify this is intentional for machine type '{machine_type}'.",
            ))

    # safe_z check: negative Z without prior safe retract (simplified heuristic)
    if safe_z is not None and min_z is not None and min_z < 0:
        if max_z is None or max_z < float(safe_z):
            findings.append(_finding(
                "warning", "SAFE_Z_NOT_REACHED",
                f"safe_z is {safe_z} but maximum Z in program ({max_z}) "
                "may not reach the expected safe retract height.",
            ))

    # ------------------------------------------------------------------
    # 4. Build result
    # ------------------------------------------------------------------
    return _build_result(findings=findings, machine_type=machine_type, summary=summary)


def _empty_summary(machine_type: str) -> dict:
    return {
        "machine_type": machine_type,
        "units": "unknown",
        "positioning_mode": "unknown",
        "work_coordinate_system": None,
        "has_program_end": False,
        "has_feedrate": False,
        "has_spindle_start": False,
        "has_spindle_stop": False,
        "line_count": 0,
        "motion_line_count": 0,
        "min_z": None,
        "max_z": None,
        "feedrates": [],
        "spindle_speeds": [],
        "unsupported_commands": [],
    }


def _build_result(findings: list[dict], machine_type: str, summary: dict) -> dict:
    errors = [f["message"] for f in findings if f["severity"] == "error"]
    warnings = [f["message"] for f in findings if f["severity"] == "warning"]

    ok = len(errors) == 0
    if errors:
        risk_level = "high"
    elif warnings:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "ok": ok,
        "risk_level": risk_level,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
        "findings": findings,
    }
