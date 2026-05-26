"""Tests for multi-hole drill pattern — build_drill_pattern_operation_plan and
generate_drill_pattern_gcode_from_params."""

import pytest
from cnc.tools.drill_tools import (
    build_drill_pattern_operation_plan,
    generate_drill_pattern_gcode_from_params,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

THREE_HOLES = [
    {"x": 0, "y": 0, "depth": 5},
    {"x": 10, "y": 0, "depth": 5},
    {"x": 10, "y": 10, "depth": 8},
]

TWO_HOLES = [
    {"x": 0, "y": 0, "depth": 5},
    {"x": 25, "y": 15, "depth": 10},
]


# ---------------------------------------------------------------------------
# A) build_drill_pattern_operation_plan — structure
# ---------------------------------------------------------------------------


def test_pattern_plan_machine_type():
    plan = build_drill_pattern_operation_plan(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert plan["machine_type"] == "drill"


def test_pattern_plan_three_operations():
    plan = build_drill_pattern_operation_plan(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert len(plan["operations"]) == 3


def test_pattern_plan_first_hole_z():
    plan = build_drill_pattern_operation_plan(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert plan["operations"][0]["parameters"]["z"] == -5.0


def test_pattern_plan_second_hole_z():
    plan = build_drill_pattern_operation_plan(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert plan["operations"][1]["parameters"]["z"] == -5.0


def test_pattern_plan_third_hole_z():
    plan = build_drill_pattern_operation_plan(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert plan["operations"][2]["parameters"]["z"] == -8.0


def test_pattern_plan_hole_xy_coordinates():
    plan = build_drill_pattern_operation_plan(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert plan["operations"][0]["parameters"]["x"] == 0.0
    assert plan["operations"][0]["parameters"]["y"] == 0.0
    assert plan["operations"][1]["parameters"]["x"] == 10.0
    assert plan["operations"][2]["parameters"]["x"] == 10.0
    assert plan["operations"][2]["parameters"]["y"] == 10.0


def test_pattern_plan_operations_type_drill():
    plan = build_drill_pattern_operation_plan(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    for op in plan["operations"]:
        assert op["type"] == "drill"


def test_pattern_plan_tool_diameter_in_name():
    plan = build_drill_pattern_operation_plan(
        holes=TWO_HOLES, tool_diameter=8, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "8" in plan["tools"][0]["name"]


def test_pattern_plan_safe_z_stored():
    plan = build_drill_pattern_operation_plan(
        holes=TWO_HOLES, tool_diameter=5, safe_z=7.5, feedrate=100, spindle_speed=1200,
    )
    assert plan["safe_z"] == 7.5


def test_pattern_plan_feedrate_in_operation():
    plan = build_drill_pattern_operation_plan(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5, feedrate=150, spindle_speed=1200,
    )
    for op in plan["operations"]:
        assert op.get("feedrate") == 150


# ---------------------------------------------------------------------------
# B) generate_drill_pattern_gcode_from_params — full pipeline
# ---------------------------------------------------------------------------


def test_pattern_gcode_ok():
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is True


def test_pattern_gcode_machine_type():
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["machine_type"] == "drill"


def test_pattern_gcode_has_m30():
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "M30" in result["gcode"]


def test_pattern_gcode_has_three_g1_plunges():
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    gcode = result["gcode"]
    g01_count = gcode.count("G01 Z")
    assert g01_count >= 3, f"Expected >=3 G01 Z plunges, got {g01_count}"


def test_pattern_gcode_has_percent_fanuc():
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["gcode"].startswith("%")


def test_pattern_gcode_has_z_minus_8():
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "Z-8.000" in result["gcode"]


def test_pattern_gcode_spindle_starts_once():
    """With same spindle speed, M03 should appear only once (not per hole)."""
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    gcode = result["gcode"]
    m03_count = gcode.count("M03")
    assert m03_count == 1, f"Expected exactly 1 M03, got {m03_count}"


def test_pattern_gcode_spindle_stops_once():
    """Spindle stop (M05) should appear once at end, not after each hole."""
    result = generate_drill_pattern_gcode_from_params(
        holes=THREE_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    gcode = result["gcode"]
    m05_count = gcode.count("M05")
    assert m05_count == 1, f"Expected exactly 1 M05, got {m05_count}"


def test_pattern_gcode_postprocessor_field():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
        postprocessor="grbl",
    )
    assert result["postprocessor"] == "grbl"


def test_pattern_gcode_machine_profile_field_in_result():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, feedrate=100, spindle_speed=1200,
        machine_profile="generic_drill_mm",
    )
    assert result["machine_profile"] == "generic_drill_mm"


# ---------------------------------------------------------------------------
# C) machine_profile supplies safe_z when None
# ---------------------------------------------------------------------------


def test_profile_supplies_safe_z():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, feedrate=100, spindle_speed=1200,
        safe_z=None,
        machine_profile="generic_drill_mm",
    )
    plan = result["operation_plan"]
    assert plan["safe_z"] == 5.0


def test_profile_generic_drill_mm_plan_ok():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, feedrate=100, spindle_speed=1200,
        machine_profile="generic_drill_mm",
    )
    assert result["ok"] is True


def test_profile_generic_drill_inch():
    result = generate_drill_pattern_gcode_from_params(
        holes=[{"x": 0, "y": 0, "depth": 0.5}],
        tool_diameter=0.25,
        feedrate=5,
        spindle_speed=3000,
        machine_profile="generic_drill_inch",
    )
    plan = result["operation_plan"]
    assert plan["safe_z"] == 0.2
    assert plan["units"] == "inch"


def test_unknown_profile_adds_warning():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5, feedrate=100,
        machine_profile="nonexistent_profile",
    )
    warnings_text = " ".join(result.get("warnings", []))
    assert "nonexistent_profile" in warnings_text or "not recognised" in warnings_text


# ---------------------------------------------------------------------------
# D) Missing feedrate → errors, no G-code
# ---------------------------------------------------------------------------


def test_missing_feedrate_not_ok():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5,
        feedrate=None,  # missing
        spindle_speed=1200,
    )
    assert result["ok"] is False


def test_missing_feedrate_gcode_empty():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5,
        feedrate=None,
        spindle_speed=1200,
    )
    assert result["gcode"] == ""


def test_missing_feedrate_has_errors():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5,
        feedrate=None,
        spindle_speed=1200,
    )
    assert len(result["errors"]) > 0


def test_missing_safe_z_not_ok():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5,
        safe_z=None,
        feedrate=100,
        spindle_speed=1200,
    )
    assert result["ok"] is False


def test_empty_holes_not_ok():
    result = generate_drill_pattern_gcode_from_params(
        holes=[], tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# E) Negative depth → warning, correct Z
# ---------------------------------------------------------------------------


def test_negative_depth_z_target():
    holes = [{"x": 0, "y": 0, "depth": -8}]
    plan = build_drill_pattern_operation_plan(
        holes=holes, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert plan["operations"][0]["parameters"]["z"] == -8.0


def test_negative_depth_adds_warning():
    holes = [{"x": 0, "y": 0, "depth": -8}]
    plan = build_drill_pattern_operation_plan(
        holes=holes, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    warnings_text = " ".join(plan["warnings"])
    assert "negative" in warnings_text.lower()


def test_negative_depth_full_pipeline_ok():
    holes = [{"x": 0, "y": 0, "depth": -8}, {"x": 10, "y": 0, "depth": 5}]
    result = generate_drill_pattern_gcode_from_params(
        holes=holes, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is True
    assert "Z-8.000" in result["gcode"]


# ---------------------------------------------------------------------------
# F) No spindle speed — safe handling
# ---------------------------------------------------------------------------


def test_no_spindle_speed_ok_but_warned():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5, feedrate=100,
        spindle_speed=None,
    )
    # ok may be True (no hard error) but must have a spindle warning
    warnings_text = " ".join(result.get("warnings", []))
    assert "spindle" in warnings_text.lower()


def test_no_spindle_no_m03_in_gcode():
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5, feedrate=100,
        spindle_speed=None,
    )
    gcode = result.get("gcode", "")
    # M03 must not appear as an actual command (lines starting with M03 or S... M03)
    # It may appear inside comments — check non-comment lines only
    m03_command = any(
        "M03" in line and not line.strip().startswith("(")
        for line in gcode.splitlines()
    )
    assert not m03_command, "M03 spindle command found in G-code despite no spindle speed"


# ---------------------------------------------------------------------------
# G) Postprocessor parametrisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pp", ["fanuc", "grbl", "linuxcnc"])
def test_pattern_gcode_postprocessors(pp):
    result = generate_drill_pattern_gcode_from_params(
        holes=TWO_HOLES, tool_diameter=5, safe_z=5, feedrate=100, spindle_speed=1200,
        postprocessor=pp,
    )
    assert isinstance(result, dict)
    assert result["postprocessor"] == pp
    if result["ok"]:
        assert "Z-5" in result["gcode"] or "Z-10" in result["gcode"]
