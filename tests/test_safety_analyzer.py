"""Tests for cnc/validators/safety_analyzer.py — G-code Safety Analyzer v1."""

import pytest
from cnc.validators.safety_analyzer import analyze_gcode_safety


# ---------------------------------------------------------------------------
# Fixtures / shared G-code snippets
# ---------------------------------------------------------------------------

CLEAN_DRILL_GCODE = """\
G21
G90
G54
G0 Z5
S1200 M03
G0 X0 Y0
G01 Z-5 F100
G0 Z5
M05
M30"""

RAPID_Z_NEG_GCODE = "G21\nG90\nG54\nG0 Z-10\nM30"

NO_UNITS_GCODE = "G90\nG54\nF100\nM30"

MIXED_UNITS_GCODE = "G20\nG21\nG90\nG54\nF100\nM30"

UNITS_MISMATCH_GCODE = "G20\nG90\nG54\nF100\nM30"  # inch when mm expected

ZERO_FEEDRATE_GCODE = "G21\nG90\nG54\nG0 Z5\nG01 Z-5 F0\nM30"

DEEP_CUT_GCODE = "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-20 F100\nG0 Z5\nM05\nM30"

NO_PROGRAM_END_GCODE = "G21\nG90\nG54\nG0 Z5\nG01 Z-5 F100\nM05"

DISALLOWED_GCODE = "G21\nG90\nG54\nG40\nG01 Z-5 F100\nM30"


# ---------------------------------------------------------------------------
# A) Return structure
# ---------------------------------------------------------------------------


def test_result_has_required_keys():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    for key in ("ok", "risk_level", "errors", "warnings", "summary", "findings"):
        assert key in result, f"Missing key: {key}"


def test_result_ok_is_bool():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert isinstance(result["ok"], bool)


def test_result_risk_level_valid():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["risk_level"] in ("low", "medium", "high")


def test_result_errors_is_list():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert isinstance(result["errors"], list)


def test_result_warnings_is_list():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert isinstance(result["warnings"], list)


def test_result_summary_is_dict():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert isinstance(result["summary"], dict)


def test_result_findings_is_list():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert isinstance(result["findings"], list)


def test_summary_has_required_keys():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    summary = result["summary"]
    for key in (
        "machine_type", "units", "positioning_mode", "work_coordinate_system",
        "has_program_end", "has_feedrate", "has_spindle_start", "has_spindle_stop",
        "line_count", "motion_line_count", "min_z", "max_z",
        "feedrates", "spindle_speeds", "unsupported_commands",
    ):
        assert key in summary, f"Summary missing key: {key}"


def test_finding_has_required_keys():
    result = analyze_gcode_safety(RAPID_Z_NEG_GCODE, "mill")
    assert result["findings"]
    finding = result["findings"][0]
    for key in ("severity", "code", "line", "message", "text"):
        assert key in finding, f"Finding missing key: {key}"


def test_finding_severity_values():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    for finding in result["findings"]:
        assert finding["severity"] in ("info", "warning", "error"), \
            f"Invalid severity: {finding['severity']}"


# ---------------------------------------------------------------------------
# B) Clean G-code — low risk, ok=True
# ---------------------------------------------------------------------------


def test_clean_drill_gcode_ok():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["ok"] is True


def test_clean_drill_gcode_low_risk():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["risk_level"] == "low"


def test_clean_drill_gcode_no_errors():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["errors"] == []


def test_clean_drill_gcode_no_warnings():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["warnings"] == []


def test_clean_gcode_summary_units_mm():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["units"] == "mm"


def test_clean_gcode_summary_positioning_absolute():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["positioning_mode"] == "absolute"


def test_clean_gcode_summary_wcs():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["work_coordinate_system"] == "G54"


def test_clean_gcode_summary_has_program_end():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["has_program_end"] is True


def test_clean_gcode_summary_has_feedrate():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["has_feedrate"] is True


def test_clean_gcode_summary_has_spindle_start():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["has_spindle_start"] is True


def test_clean_gcode_summary_has_spindle_stop():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["has_spindle_stop"] is True


def test_clean_gcode_summary_min_z():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["summary"]["min_z"] == -5.0


def test_clean_gcode_summary_feedrates():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert 100.0 in result["summary"]["feedrates"]


# ---------------------------------------------------------------------------
# C) Empty G-code
# ---------------------------------------------------------------------------


def test_empty_gcode_not_ok():
    result = analyze_gcode_safety("", "mill")
    assert result["ok"] is False


def test_empty_gcode_high_risk():
    result = analyze_gcode_safety("", "mill")
    assert result["risk_level"] == "high"


def test_empty_gcode_has_error():
    result = analyze_gcode_safety("", "mill")
    assert result["errors"]


def test_whitespace_gcode_not_ok():
    result = analyze_gcode_safety("   \n\t  ", "drill")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# D) Rapid Z-negative — error
# ---------------------------------------------------------------------------


def test_rapid_z_negative_not_ok():
    result = analyze_gcode_safety(RAPID_Z_NEG_GCODE, "mill")
    assert result["ok"] is False


def test_rapid_z_negative_high_risk():
    result = analyze_gcode_safety(RAPID_Z_NEG_GCODE, "mill")
    assert result["risk_level"] == "high"


def test_rapid_z_negative_error_message():
    result = analyze_gcode_safety(RAPID_Z_NEG_GCODE, "mill")
    errors_text = " ".join(result["errors"]).lower()
    assert "rapid" in errors_text or "g00" in errors_text or "negative" in errors_text


def test_rapid_z_negative_finding_code():
    result = analyze_gcode_safety(RAPID_Z_NEG_GCODE, "mill")
    codes = [f["code"] for f in result["findings"]]
    assert "RAPID_Z_NEGATIVE" in codes


def test_rapid_z_negative_finding_has_line():
    result = analyze_gcode_safety(RAPID_Z_NEG_GCODE, "mill")
    rapid_findings = [f for f in result["findings"] if f["code"] == "RAPID_Z_NEGATIVE"]
    assert rapid_findings
    assert rapid_findings[0]["line"] is not None


# ---------------------------------------------------------------------------
# E) Units checks
# ---------------------------------------------------------------------------


def test_no_units_ok():
    result = analyze_gcode_safety(NO_UNITS_GCODE, "drill")
    assert result["ok"] is True


def test_no_units_medium_risk():
    result = analyze_gcode_safety(NO_UNITS_GCODE, "drill")
    assert result["risk_level"] == "medium"


def test_no_units_warning():
    result = analyze_gcode_safety(NO_UNITS_GCODE, "drill")
    warnings_text = " ".join(result["warnings"]).lower()
    assert "unit" in warnings_text or "g20" in warnings_text or "g21" in warnings_text


def test_mixed_units_not_ok():
    result = analyze_gcode_safety(MIXED_UNITS_GCODE, "mill")
    assert result["ok"] is False


def test_mixed_units_error():
    result = analyze_gcode_safety(MIXED_UNITS_GCODE, "mill")
    errors_text = " ".join(result["errors"]).lower()
    assert "unit" in errors_text or "g20" in errors_text or "g21" in errors_text


def test_units_mismatch_error():
    result = analyze_gcode_safety(UNITS_MISMATCH_GCODE, "mill", expected_units="mm")
    assert result["ok"] is False
    errors_text = " ".join(result["errors"]).lower()
    assert "mismatch" in errors_text or "unit" in errors_text


def test_correct_units_no_mismatch_error():
    result = analyze_gcode_safety(UNITS_MISMATCH_GCODE, "mill", expected_units="inch")
    # G20 = inch, expected_units=inch → no mismatch error
    error_codes = [f["code"] for f in result["findings"] if f["severity"] == "error"]
    assert "UNITS_MISMATCH" not in error_codes


def test_summary_units_unknown_when_no_declaration():
    result = analyze_gcode_safety(NO_UNITS_GCODE, "mill")
    assert result["summary"]["units"] == "unknown"


# ---------------------------------------------------------------------------
# F) Feedrate checks
# ---------------------------------------------------------------------------


def test_zero_feedrate_not_ok():
    result = analyze_gcode_safety(ZERO_FEEDRATE_GCODE, "mill")
    assert result["ok"] is False


def test_zero_feedrate_error():
    result = analyze_gcode_safety(ZERO_FEEDRATE_GCODE, "mill")
    errors_text = " ".join(result["errors"]).lower()
    assert "feedrate" in errors_text or "f0" in errors_text


def test_no_feedrate_warning():
    gcode = "G21\nG90\nG54\nM30"
    result = analyze_gcode_safety(gcode, "mill")
    warnings_text = " ".join(result["warnings"]).lower()
    assert "feedrate" in warnings_text


def test_no_feedrate_ok():
    """Missing feedrate is a warning, not an error."""
    gcode = "G21\nG90\nG54\nM30"
    result = analyze_gcode_safety(gcode, "mill")
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# G) max_depth check
# ---------------------------------------------------------------------------


def test_max_depth_exceeded_not_ok():
    result = analyze_gcode_safety(DEEP_CUT_GCODE, "mill", max_depth=10.0)
    assert result["ok"] is False


def test_max_depth_exceeded_error():
    result = analyze_gcode_safety(DEEP_CUT_GCODE, "mill", max_depth=10.0)
    errors_text = " ".join(result["errors"]).lower()
    assert "depth" in errors_text or "z" in errors_text


def test_max_depth_not_exceeded_ok():
    result = analyze_gcode_safety(DEEP_CUT_GCODE, "mill", max_depth=25.0)
    # Ensure no EXCEEDS_MAX_DEPTH error
    error_codes = [f["code"] for f in result["findings"] if f["severity"] == "error"]
    assert "EXCEEDS_MAX_DEPTH" not in error_codes


# ---------------------------------------------------------------------------
# H) allowed_commands check
# ---------------------------------------------------------------------------


def test_disallowed_command_not_ok():
    # G40 is in the gcode but not allowed
    result = analyze_gcode_safety(
        DISALLOWED_GCODE, "mill",
        allowed_commands=["G21", "G90", "G54", "G0", "G1", "G01", "M30"],
    )
    assert result["ok"] is False


def test_disallowed_command_error_message():
    result = analyze_gcode_safety(
        DISALLOWED_GCODE, "mill",
        allowed_commands=["G21", "G90", "G54", "G0", "G1", "G01", "M30"],
    )
    errors_text = " ".join(result["errors"]).lower()
    assert "allowed" in errors_text or "disallowed" in errors_text or "g40" in errors_text


def test_all_commands_allowed_no_disallowed_error():
    result = analyze_gcode_safety(
        CLEAN_DRILL_GCODE, "drill",
        allowed_commands=["G0", "G1", "G21", "G90", "G54", "M3", "M03", "M5", "M05", "M30"],
    )
    error_codes = [f["code"] for f in result["findings"] if f["severity"] == "error"]
    assert "DISALLOWED_COMMAND" not in error_codes


# ---------------------------------------------------------------------------
# I) Machine-type specific checks
# ---------------------------------------------------------------------------


def test_mill_no_spindle_warning():
    gcode = "G21\nG90\nG54\nG01 Z-5 F100\nM30"
    result = analyze_gcode_safety(gcode, "mill")
    warnings_text = " ".join(result["warnings"]).lower()
    assert "spindle" in warnings_text or "m03" in warnings_text


def test_laser_no_laser_enable_warning():
    gcode = "G21\nG90\nG0 X0 Y0\nM30"
    result = analyze_gcode_safety(gcode, "laser")
    warnings_text = " ".join(result["warnings"]).lower()
    assert "laser" in warnings_text or "m03" in warnings_text or "m04" in warnings_text


def test_3d_printer_no_hotend_temp_warning():
    gcode = "G21\nG90\nG0 X0 Y0\nM30"
    result = analyze_gcode_safety(gcode, "3d_printer")
    warnings_text = " ".join(result["warnings"]).lower()
    assert "hotend" in warnings_text or "m104" in warnings_text or "m109" in warnings_text


# ---------------------------------------------------------------------------
# J) Risk level mapping
# ---------------------------------------------------------------------------


def test_errors_produce_high_risk():
    result = analyze_gcode_safety(RAPID_Z_NEG_GCODE, "mill")
    assert result["risk_level"] == "high"


def test_warnings_only_produce_medium_risk():
    result = analyze_gcode_safety(NO_UNITS_GCODE, "drill")
    assert result["risk_level"] == "medium"


def test_no_issues_produce_low_risk():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    assert result["risk_level"] == "low"


# ---------------------------------------------------------------------------
# K) No program end
# ---------------------------------------------------------------------------


def test_no_program_end_warning():
    result = analyze_gcode_safety(NO_PROGRAM_END_GCODE, "mill")
    warnings_text = " ".join(result["warnings"]).lower()
    assert "program" in warnings_text or "m30" in warnings_text or "m02" in warnings_text


def test_no_program_end_ok():
    """Missing program end is a warning, not an error."""
    result = analyze_gcode_safety(NO_PROGRAM_END_GCODE, "mill")
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# L) safe_z heuristic check
# ---------------------------------------------------------------------------


def test_safe_z_not_reached_warning():
    # safe_z=10, but max_z in program is only 5
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill", safe_z=10.0)
    # max_z in CLEAN_DRILL_GCODE is 5 which is < safe_z=10
    warning_codes = [f["code"] for f in result["findings"] if f["severity"] == "warning"]
    assert "SAFE_Z_NOT_REACHED" in warning_codes


def test_safe_z_met_no_warning():
    # safe_z=5, max_z=5 — exactly meets safe_z
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill", safe_z=5.0)
    warning_codes = [f["code"] for f in result["findings"] if f["severity"] == "warning"]
    assert "SAFE_Z_NOT_REACHED" not in warning_codes


# ---------------------------------------------------------------------------
# M) Info findings
# ---------------------------------------------------------------------------


def test_info_findings_present():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    info_findings = [f for f in result["findings"] if f["severity"] == "info"]
    assert info_findings


def test_units_detected_info_finding():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    info_codes = [f["code"] for f in result["findings"] if f["severity"] == "info"]
    assert "UNITS_DETECTED" in info_codes


def test_wcs_detected_info_finding():
    result = analyze_gcode_safety(CLEAN_DRILL_GCODE, "drill")
    info_codes = [f["code"] for f in result["findings"] if f["severity"] == "info"]
    assert "WCS_DETECTED" in info_codes


# ---------------------------------------------------------------------------
# N) G91 stateful analysis — G28 G91 Z0 idiom
# ---------------------------------------------------------------------------


G90_DRILL_WITH_G28_G91_GCODE = """\
G21
G90
G54
G0 Z5
S1200 M3
G1 Z-18 F80
G0 Z5
M5
G28 G91 Z0
G90
M30"""


def test_g28_g91_no_relative_negative_z_for_earlier_g90_moves():
    """Z-18 under G90 must NOT trigger RELATIVE_NEGATIVE_Z / G91_NEGATIVE_Z."""
    result = analyze_gcode_safety(G90_DRILL_WITH_G28_G91_GCODE, "drill")
    warning_codes = [f["code"] for f in result["findings"] if f["severity"] == "warning"]
    assert "G91_NEGATIVE_Z" not in warning_codes


def test_g28_g91_scoped_idiom_info_or_warning():
    """G28 G91 Z0 / G90 should produce at most one info or warning for the idiom."""
    result = analyze_gcode_safety(G90_DRILL_WITH_G28_G91_GCODE, "drill")
    g91_findings = [f for f in result["findings"]
                    if f["code"] == "RELATIVE_POSITIONING"]
    assert len(g91_findings) <= 1
    if g91_findings:
        # Should be info (scoped idiom), not warning
        assert g91_findings[0]["severity"] == "info"


def test_g28_g91_no_duplicate_warnings():
    """G91 should not produce multiple separate warnings."""
    result = analyze_gcode_safety(G90_DRILL_WITH_G28_G91_GCODE, "drill")
    g91_findings = [f for f in result["findings"]
                    if "G91" in f.get("code", "") or "RELATIVE" in f.get("code", "")]
    # At most one finding for the scoped G91 idiom
    assert len(g91_findings) <= 1


def test_real_relative_negative_z_warns():
    """Actual G91 with negative Z cutting should warn."""
    gcode = "G21\nG91\nG1 Z-5 F100\nM30"
    result = analyze_gcode_safety(gcode, "mill")
    warning_codes = [f["code"] for f in result["findings"] if f["severity"] == "warning"]
    assert "G91_NEGATIVE_Z" in warning_codes


def test_real_relative_negative_z_risk():
    """G91 negative Z should produce at least medium risk."""
    gcode = "G21\nG91\nG1 Z-5 F100\nM30"
    result = analyze_gcode_safety(gcode, "mill")
    assert result["risk_level"] in ("medium", "high")
