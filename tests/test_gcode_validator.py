"""Tests for cnc/validators/gcode_validator.py — static G-code analysis."""

import pytest
from cnc.validators.gcode_validator import validate_gcode_text


# ---------------------------------------------------------------------------
# A) Valid drill G-code
# ---------------------------------------------------------------------------

VALID_DRILL_GCODE = """\
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


def test_valid_drill_gcode_ok():
    result = validate_gcode_text(VALID_DRILL_GCODE, "drill")
    assert result["ok"] is True
    assert result["errors"] == []


def test_valid_drill_gcode_machine_type_preserved():
    result = validate_gcode_text(VALID_DRILL_GCODE, "drill")
    assert result["machine_type"] == "drill"


def test_valid_drill_gcode_has_no_critical_warnings():
    """No warnings about missing units, positioning mode, feedrate, or program end."""
    result = validate_gcode_text(VALID_DRILL_GCODE, "drill")
    combined = " ".join(result.get("warnings", []))
    assert "unit" not in combined.lower()
    assert "feedrate" not in combined.lower()
    assert "M30" not in combined.upper() or "no program end" not in combined.lower()


# ---------------------------------------------------------------------------
# B) Empty G-code
# ---------------------------------------------------------------------------


def test_empty_gcode_not_ok():
    result = validate_gcode_text("", "drill")
    assert result["ok"] is False
    assert result["errors"]


def test_whitespace_only_gcode_not_ok():
    result = validate_gcode_text("   \n\t  ", "mill")
    assert result["ok"] is False
    assert result["errors"]


# ---------------------------------------------------------------------------
# C) G-code without unit declaration
# ---------------------------------------------------------------------------

NO_UNITS_GCODE = """\
G90
F100
M30"""


def test_no_units_still_ok():
    """Missing units is a warning, not an error."""
    result = validate_gcode_text(NO_UNITS_GCODE, "drill")
    assert result["ok"] is True


def test_no_units_produces_warning():
    result = validate_gcode_text(NO_UNITS_GCODE, "drill")
    warnings_text = " ".join(result.get("warnings", [])).lower()
    assert "g20" in warnings_text or "g21" in warnings_text or "unit" in warnings_text


# ---------------------------------------------------------------------------
# D) G-code with spindle concerns
# ---------------------------------------------------------------------------

NO_SPINDLE_SPEED_GCODE = """\
G21
G90
M03
F100
M30"""


def test_no_spindle_speed_does_not_crash():
    result = validate_gcode_text(NO_SPINDLE_SPEED_GCODE, "drill")
    assert "ok" in result
    assert "errors" in result
    assert "warnings" in result


def test_rapid_plunge_to_negative_z_is_error():
    """G00 to a negative Z is dangerous — must be an error."""
    gcode = "G21\nG90\nG54\nG0 Z-10\nM30"
    result = validate_gcode_text(gcode, "mill")
    assert result["ok"] is False
    assert result["errors"]
    assert any("rapid" in e.lower() or "G00" in e or "negative" in e.lower()
               for e in result["errors"])


# ---------------------------------------------------------------------------
# E) Machine-type checks
# ---------------------------------------------------------------------------


def test_mill_warns_missing_spindle_start():
    gcode = "G21\nG90\nG54\nG0 X0\nG01 Z-5 F100\nM30"
    result = validate_gcode_text(gcode, "mill")
    warnings_text = " ".join(result.get("warnings", [])).lower()
    assert "spindle" in warnings_text or "m03" in warnings_text


def test_3d_printer_warns_missing_hotend_temp():
    gcode = "G21\nG90\nG0 X0 Y0\nM30"
    result = validate_gcode_text(gcode, "3d_printer")
    warnings_text = " ".join(result.get("warnings", [])).lower()
    assert "m104" in warnings_text or "m109" in warnings_text or "hotend" in warnings_text


def test_laser_warns_missing_laser_enable():
    gcode = "G21\nG90\nG0 X0 Y0\nM30"
    result = validate_gcode_text(gcode, "laser")
    warnings_text = " ".join(result.get("warnings", [])).lower()
    assert "m03" in warnings_text or "m04" in warnings_text or "laser" in warnings_text


# ---------------------------------------------------------------------------
# F) Return structure
# ---------------------------------------------------------------------------


def test_result_always_has_required_keys():
    for mt in ("mill", "drill", "laser", "lathe", "3d_printer"):
        result = validate_gcode_text("G21 G90 M30", mt)
        assert "ok" in result
        assert "errors" in result
        assert "warnings" in result
        assert "machine_type" in result
