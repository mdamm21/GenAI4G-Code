"""Tests for cnc/tools/milling_tools.py — deterministic milling facing pipeline."""

import pytest
from cnc.tools.milling_tools import (
    build_milling_facing_operation_plan,
    generate_milling_facing_gcode_from_params,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

FACING_DEFAULTS = dict(
    origin_x=0.0,
    origin_y=0.0,
    width=20.0,
    height=10.0,
    depth=1.0,
    step_over=2.0,
    tool_diameter=5.0,
    safe_z=5.0,
    feedrate=150.0,
    spindle_speed=3000.0,
)


def _plan(**overrides) -> dict:
    return build_milling_facing_operation_plan(**{**FACING_DEFAULTS, **overrides})


def _gcode(**overrides) -> dict:
    return generate_milling_facing_gcode_from_params(**{**FACING_DEFAULTS, **overrides})


# ---------------------------------------------------------------------------
# A) build_milling_facing_operation_plan — structure
# ---------------------------------------------------------------------------


def test_plan_machine_type():
    plan = _plan()
    assert plan["machine_type"] == "mill"


def test_plan_operation_type_facing():
    plan = _plan()
    assert plan["operations"][0]["type"] == "facing"


def test_plan_target_z_from_positive_depth():
    plan = _plan(depth=1.0)
    assert plan["operations"][0]["parameters"]["target_z"] == -1.0


def test_plan_target_z_from_depth_3():
    plan = _plan(depth=3.0)
    assert plan["operations"][0]["parameters"]["target_z"] == -3.0


def test_plan_width_stored():
    plan = _plan(width=30.0)
    assert plan["operations"][0]["parameters"]["width"] == 30.0


def test_plan_height_stored():
    plan = _plan(height=15.0)
    assert plan["operations"][0]["parameters"]["height"] == 15.0


def test_plan_step_over_stored():
    plan = _plan(step_over=3.0)
    assert plan["operations"][0]["parameters"]["step_over"] == 3.0


def test_plan_tool_diameter_in_name():
    plan = _plan(tool_diameter=8.0)
    assert "8" in plan["tools"][0]["name"]


def test_plan_tool_type_end_mill():
    plan = _plan()
    assert "end mill" in plan["tools"][0]["name"]


def test_plan_safe_z_stored():
    plan = _plan(safe_z=7.5)
    assert plan["safe_z"] == 7.5


def test_plan_feedrate_in_operation():
    plan = _plan(feedrate=200.0)
    assert plan["operations"][0]["feedrate"] == 200.0


def test_plan_spindle_in_operation():
    plan = _plan(spindle_speed=5000.0)
    assert plan["operations"][0]["spindle_speed"] == 5000.0


def test_plan_origin_xy_stored():
    plan = _plan(origin_x=10.0, origin_y=5.0)
    params = plan["operations"][0]["parameters"]
    assert params["origin_x"] == 10.0
    assert params["origin_y"] == 5.0


def test_plan_material_assumption():
    plan = _plan(material="6061 aluminium")
    assumptions_text = " ".join(plan["assumptions"])
    assert "6061 aluminium" in assumptions_text


def test_plan_no_material_assumption():
    plan = _plan(material=None)
    assumptions_text = " ".join(plan["assumptions"])
    assert "not specified" in assumptions_text.lower()


# ---------------------------------------------------------------------------
# B) generate_milling_facing_gcode_from_params — full pipeline
# ---------------------------------------------------------------------------


def test_gcode_ok():
    result = _gcode()
    assert result["ok"] is True


def test_gcode_machine_type():
    result = _gcode()
    assert result["machine_type"] == "mill"


def test_gcode_has_g21():
    result = _gcode()
    assert "G21" in result["gcode"]


def test_gcode_has_g90():
    result = _gcode()
    assert "G90" in result["gcode"]


def test_gcode_has_wcs():
    result = _gcode()
    assert "G54" in result["gcode"]


def test_gcode_has_spindle_start():
    result = _gcode(spindle_speed=3000)
    assert "S3000" in result["gcode"]
    assert "M03" in result["gcode"]


def test_gcode_has_g1_cut():
    result = _gcode()
    assert "G01 X" in result["gcode"]


def test_gcode_has_feedrate():
    result = _gcode(feedrate=150)
    assert "F150" in result["gcode"]


def test_gcode_has_negative_target_z():
    result = _gcode(depth=1.0)
    assert "Z-1.000" in result["gcode"]


def test_gcode_has_m30():
    result = _gcode()
    assert "M30" in result["gcode"]


def test_gcode_has_percent_fanuc():
    result = _gcode()
    assert result["gcode"].startswith("%")


def test_gcode_multiple_passes():
    # height=10, step_over=2 → should generate several passes
    result = _gcode(height=10.0, step_over=2.0)
    gcode = result["gcode"]
    # Expect at least 5 G01 X moves (one per pass)
    assert gcode.count("G01 X") >= 5


def test_gcode_postprocessor_field():
    result = _gcode(postprocessor="fanuc")
    assert result["postprocessor"] == "fanuc"


def test_gcode_machine_profile_field():
    result = _gcode(machine_profile="generic_mill_mm")
    assert result["machine_profile"] == "generic_mill_mm"


# ---------------------------------------------------------------------------
# C) machine_profile generic_mill_mm supplies safe_z when None
# ---------------------------------------------------------------------------


def test_profile_supplies_safe_z():
    result = generate_milling_facing_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=1, step_over=2, tool_diameter=5,
        safe_z=None, feedrate=150, spindle_speed=3000,
        machine_profile="generic_mill_mm",
    )
    assert result["operation_plan"]["safe_z"] == 5.0


def test_profile_generic_mill_mm_ok():
    result = generate_milling_facing_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=1, step_over=2, tool_diameter=5,
        feedrate=150, spindle_speed=3000,
        machine_profile="generic_mill_mm",
    )
    assert result["ok"] is True


def test_unknown_profile_adds_warning():
    result = generate_milling_facing_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=1, step_over=2, tool_diameter=5,
        safe_z=5, feedrate=150, spindle_speed=3000,
        machine_profile="nonexistent_mill_profile",
    )
    warnings_text = " ".join(result.get("warnings", []))
    assert "nonexistent_mill_profile" in warnings_text or "not recognised" in warnings_text


# ---------------------------------------------------------------------------
# D) Missing feedrate → errors, no G-code
# ---------------------------------------------------------------------------


def test_missing_feedrate_not_ok():
    result = _gcode(feedrate=None)
    assert result["ok"] is False


def test_missing_feedrate_gcode_empty():
    result = _gcode(feedrate=None)
    assert result["gcode"] == ""


def test_missing_feedrate_has_errors():
    result = _gcode(feedrate=None)
    assert len(result["errors"]) > 0


def test_missing_safe_z_not_ok():
    result = generate_milling_facing_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=1, step_over=2, tool_diameter=5,
        safe_z=None, feedrate=150, spindle_speed=3000,
    )
    assert result["ok"] is False


def test_missing_safe_z_gcode_empty():
    result = generate_milling_facing_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=1, step_over=2, tool_diameter=5,
        safe_z=None, feedrate=150, spindle_speed=3000,
    )
    assert result["gcode"] == ""


def test_invalid_width_not_ok():
    result = _gcode(width=0)
    assert result["ok"] is False


def test_invalid_height_not_ok():
    result = _gcode(height=-5)
    assert result["ok"] is False


def test_invalid_step_over_not_ok():
    result = _gcode(step_over=0)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# E) Negative depth → target_z, warning added
# ---------------------------------------------------------------------------


def test_negative_depth_target_z():
    plan = _plan(depth=-2.5)
    assert plan["operations"][0]["parameters"]["target_z"] == -2.5


def test_negative_depth_warning():
    plan = _plan(depth=-2.5)
    warnings_text = " ".join(plan["warnings"])
    assert "negative" in warnings_text.lower()


def test_negative_depth_full_pipeline_ok():
    result = _gcode(depth=-1.0)
    assert result["ok"] is True
    assert "Z-1.000" in result["gcode"]


# ---------------------------------------------------------------------------
# F) No spindle — safe handling
# ---------------------------------------------------------------------------


def test_no_spindle_has_warning():
    result = _gcode(spindle_speed=None)
    warnings_text = " ".join(result.get("warnings", []))
    assert "spindle" in warnings_text.lower()


def test_no_spindle_no_m03_command():
    result = _gcode(spindle_speed=None)
    gcode = result.get("gcode", "")
    m03_command = any(
        "M03" in line and not line.strip().startswith("(")
        for line in gcode.splitlines()
    )
    assert not m03_command


# ---------------------------------------------------------------------------
# G) Non-zero origin
# ---------------------------------------------------------------------------


def test_non_zero_origin_in_gcode():
    result = _gcode(origin_x=10.0, origin_y=5.0)
    gcode = result["gcode"]
    assert "X10.000" in gcode
    assert "Y5.000" in gcode
