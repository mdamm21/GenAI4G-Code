"""Tests for milling pocket — build_milling_pocket_operation_plan and
generate_milling_pocket_gcode_from_params."""

import pytest
from cnc.tools.milling_tools import (
    build_milling_pocket_operation_plan,
    generate_milling_pocket_gcode_from_params,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

POCKET_DEFAULTS = dict(
    origin_x=0.0,
    origin_y=0.0,
    width=20.0,
    height=10.0,
    depth=3.0,
    tool_diameter=5.0,
    step_down=1.0,
    step_over=2.0,
    safe_z=5.0,
    feedrate=150.0,
    spindle_speed=3000.0,
)


def _plan(**overrides) -> dict:
    return build_milling_pocket_operation_plan(**{**POCKET_DEFAULTS, **overrides})


def _gcode(**overrides) -> dict:
    return generate_milling_pocket_gcode_from_params(**{**POCKET_DEFAULTS, **overrides})


# ---------------------------------------------------------------------------
# A) build_milling_pocket_operation_plan — structure
# ---------------------------------------------------------------------------


def test_plan_machine_type():
    plan = _plan()
    assert plan["machine_type"] == "mill"


def test_plan_operation_type_pocket():
    plan = _plan()
    assert plan["operations"][0]["type"] == "pocket"


def test_plan_target_z_from_positive_depth():
    plan = _plan(depth=3.0)
    assert plan["operations"][0]["parameters"]["target_z"] == -3.0


def test_plan_target_z_depth_5():
    plan = _plan(depth=5.0)
    assert plan["operations"][0]["parameters"]["target_z"] == -5.0


def test_plan_step_down_stored():
    plan = _plan(step_down=1.0)
    assert plan["operations"][0]["parameters"]["step_down"] == 1.0


def test_plan_step_over_stored():
    plan = _plan(step_over=2.0)
    assert plan["operations"][0]["parameters"]["step_over"] == 2.0


def test_plan_width_height_stored():
    plan = _plan(width=30.0, height=15.0)
    params = plan["operations"][0]["parameters"]
    assert params["width"] == 30.0
    assert params["height"] == 15.0


def test_plan_origin_xy_stored():
    plan = _plan(origin_x=5.0, origin_y=10.0)
    params = plan["operations"][0]["parameters"]
    assert params["origin_x"] == 5.0
    assert params["origin_y"] == 10.0


def test_plan_tool_diameter_stored():
    plan = _plan(tool_diameter=8.0)
    assert plan["operations"][0]["parameters"]["tool_diameter"] == 8.0


def test_plan_tool_name_contains_end_mill():
    plan = _plan()
    assert "end mill" in plan["tools"][0]["name"]


def test_plan_safe_z_stored():
    plan = _plan(safe_z=7.0)
    assert plan["safe_z"] == 7.0


def test_plan_raster_assumption():
    plan = _plan()
    assert any("raster" in a.lower() for a in plan["assumptions"])


def test_plan_no_cutter_comp_assumption():
    plan = _plan()
    assert any("cutter compensation" in a.lower() for a in plan["assumptions"])


def test_plan_material_assumption():
    plan = _plan(material="aluminium")
    assert any("aluminium" in a for a in plan["assumptions"])


# ---------------------------------------------------------------------------
# B) generate_milling_pocket_gcode_from_params — full pipeline
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


def test_gcode_has_feedrate():
    result = _gcode(feedrate=150)
    assert "F150" in result["gcode"]


def test_gcode_has_m30():
    result = _gcode()
    assert "M30" in result["gcode"]


def test_gcode_has_percent_fanuc():
    result = _gcode()
    assert result["gcode"].startswith("%")


def test_gcode_three_z_passes_depth3_stepdown1():
    """depth=3, step_down=1 -> three passes at Z-1, Z-2, Z-3."""
    result = _gcode(depth=3.0, step_down=1.0)
    gcode = result["gcode"]
    assert "Z-1.000" in gcode
    assert "Z-2.000" in gcode
    assert "Z-3.000" in gcode


def test_gcode_pass_count_matches_depth_stepdown():
    """depth=3, step_down=1 -> 3 Z passes."""
    result = _gcode(depth=3.0, step_down=1.0)
    pass_count = result["gcode"].count("Z PASS")
    assert pass_count == 3, f"Expected 3 Z passes, got {pass_count}"


def test_gcode_step_down_larger_than_depth_single_pass():
    """step_down=10 > depth=3 -> single Z pass to Z-3."""
    result = _gcode(depth=3.0, step_down=10.0)
    assert result["ok"] is True
    pass_count = result["gcode"].count("Z PASS")
    assert pass_count == 1


def test_gcode_raster_rows_present():
    """Should have at least one CUT ROW comment."""
    result = _gcode()
    assert "CUT ROW" in result["gcode"]


def test_gcode_postprocessor_field():
    result = _gcode()
    assert result["postprocessor"] == "fanuc"


def test_gcode_machine_profile_field():
    result = _gcode(machine_profile="generic_mill_mm")
    assert result["machine_profile"] == "generic_mill_mm"


# ---------------------------------------------------------------------------
# C) Missing step_down -> errors, no G-code
# ---------------------------------------------------------------------------


def test_missing_step_down_not_ok():
    result = _gcode(step_down=None)
    assert result["ok"] is False


def test_missing_step_down_gcode_empty():
    result = _gcode(step_down=None)
    assert result["gcode"] == ""


def test_missing_step_down_has_errors():
    result = _gcode(step_down=None)
    errors_text = " ".join(result["errors"])
    assert "step_down" in errors_text


def test_invalid_step_down_zero_not_ok():
    result = _gcode(step_down=0)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# D) Missing step_over -> errors, no G-code
# ---------------------------------------------------------------------------


def test_missing_step_over_not_ok():
    result = _gcode(step_over=None)
    assert result["ok"] is False


def test_missing_step_over_gcode_empty():
    result = _gcode(step_over=None)
    assert result["gcode"] == ""


def test_missing_step_over_has_errors():
    result = _gcode(step_over=None)
    errors_text = " ".join(result["errors"])
    assert "step_over" in errors_text


def test_invalid_step_over_zero_not_ok():
    result = _gcode(step_over=0)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# E) step_over > tool_diameter -> warning (not error)
# ---------------------------------------------------------------------------


def test_step_over_larger_than_tool_still_ok():
    """step_over > tool_diameter is a warning, not a hard error."""
    result = _gcode(step_over=8.0, tool_diameter=5.0)
    assert result["ok"] is True


def test_step_over_larger_than_tool_has_warning():
    result = _gcode(step_over=8.0, tool_diameter=5.0)
    warnings_text = " ".join(result.get("warnings", []))
    assert "step_over" in warnings_text.lower() or "uncut" in warnings_text.lower()


# ---------------------------------------------------------------------------
# F) Negative depth -> target_z + warning
# ---------------------------------------------------------------------------


def test_negative_depth_target_z():
    plan = _plan(depth=-4.0)
    assert plan["operations"][0]["parameters"]["target_z"] == -4.0


def test_negative_depth_warning():
    plan = _plan(depth=-4.0)
    warnings_text = " ".join(plan["warnings"])
    assert "negative" in warnings_text.lower()


def test_negative_depth_full_pipeline_ok():
    result = _gcode(depth=-3.0)
    assert result["ok"] is True
    assert "Z-3.000" in result["gcode"]


# ---------------------------------------------------------------------------
# G) Missing feedrate / safe_z
# ---------------------------------------------------------------------------


def test_missing_feedrate_not_ok():
    result = _gcode(feedrate=None)
    assert result["ok"] is False


def test_missing_feedrate_gcode_empty():
    result = _gcode(feedrate=None)
    assert result["gcode"] == ""


def test_missing_safe_z_not_ok():
    result = generate_milling_pocket_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10, depth=3, tool_diameter=5,
        safe_z=None, feedrate=150, spindle_speed=3000, step_down=1, step_over=2,
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# H) Machine profile
# ---------------------------------------------------------------------------


def test_profile_generic_mill_mm_supplies_safe_z():
    result = generate_milling_pocket_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10, depth=3, tool_diameter=5,
        safe_z=None, feedrate=150, spindle_speed=3000, step_down=1, step_over=2,
        machine_profile="generic_mill_mm",
    )
    assert result["operation_plan"]["safe_z"] == 5.0


def test_profile_generic_mill_mm_ok():
    result = generate_milling_pocket_gcode_from_params(
        origin_x=0, origin_y=0, width=20, height=10, depth=3, tool_diameter=5,
        feedrate=150, spindle_speed=3000, step_down=1, step_over=2,
        machine_profile="generic_mill_mm",
    )
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# I) No spindle — safe handling
# ---------------------------------------------------------------------------


def test_no_spindle_has_warning():
    result = _gcode(spindle_speed=None)
    warnings_text = " ".join(result.get("warnings", []))
    assert "spindle" in warnings_text.lower()


def test_no_spindle_no_m03_command():
    result = _gcode(spindle_speed=None)
    gcode = result.get("gcode", "")
    m03_in_non_comment = any(
        "M03" in line and not line.strip().startswith("(")
        for line in gcode.splitlines()
    )
    assert not m03_in_non_comment


# ---------------------------------------------------------------------------
# J) Non-zero origin position
# ---------------------------------------------------------------------------


def test_nonzero_origin_in_gcode():
    result = _gcode(origin_x=15.0, origin_y=5.0)
    assert "X15.000" in result["gcode"]
    assert "Y5.000" in result["gcode"]
