"""Tests for cnc/tools/drill_tools.py — typed, deterministic drill pipeline."""

import pytest
from cnc.tools.drill_tools import build_drill_operation_plan, generate_drill_gcode_from_params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_plan(**overrides) -> dict:
    kwargs = dict(
        x=0.0, y=0.0, depth=5.0, tool_diameter=5.0,
        safe_z=5.0, feedrate=100.0, spindle_speed=1200.0,
    )
    kwargs.update(overrides)
    return build_drill_operation_plan(**kwargs)


# ---------------------------------------------------------------------------
# A) build_drill_operation_plan — structure
# ---------------------------------------------------------------------------


def test_machine_type_is_drill():
    plan = _default_plan()
    assert plan["machine_type"] == "drill"


def test_units_default_mm():
    plan = _default_plan()
    assert plan["units"] == "mm"


def test_units_inch():
    plan = _default_plan(units="inch")
    assert plan["units"] == "inch"


def test_safe_z_preserved():
    plan = _default_plan(safe_z=8.0)
    assert plan["safe_z"] == 8.0


def test_wcs_default_g54():
    plan = _default_plan()
    assert plan["work_coordinate_system"] == "G54"


def test_wcs_custom():
    plan = _default_plan(work_coordinate_system="G55")
    assert plan["work_coordinate_system"] == "G55"


def test_has_one_tool():
    plan = _default_plan()
    assert len(plan["tools"]) == 1


def test_tool_id_is_t1():
    plan = _default_plan()
    assert plan["tools"][0]["id"] == "T1"


def test_tool_diameter():
    plan = _default_plan(tool_diameter=8.5)
    assert plan["tools"][0]["diameter"] == 8.5


def test_tool_name_contains_diameter():
    plan = _default_plan(tool_diameter=10.0)
    assert "10" in plan["tools"][0]["name"]


def test_has_one_operation():
    plan = _default_plan()
    assert len(plan["operations"]) == 1


def test_operation_type_is_drill():
    plan = _default_plan()
    assert plan["operations"][0]["type"] == "drill"


def test_operation_tool_id_is_t1():
    plan = _default_plan()
    assert plan["operations"][0]["tool_id"] == "T1"


def test_operation_feedrate():
    plan = _default_plan(feedrate=150.0)
    assert plan["operations"][0]["feedrate"] == 150.0


def test_operation_spindle_speed():
    plan = _default_plan(spindle_speed=2000.0)
    assert plan["operations"][0]["spindle_speed"] == 2000.0


# ---------------------------------------------------------------------------
# B) depth normalisation
# ---------------------------------------------------------------------------


def test_positive_depth_becomes_negative_z():
    plan = _default_plan(depth=5.0)
    z = plan["operations"][0]["parameters"]["z"]
    assert z == -5.0


def test_zero_depth_becomes_zero_z():
    plan = _default_plan(depth=0.0)
    z = plan["operations"][0]["parameters"]["z"]
    assert z == 0.0


def test_negative_depth_normalised_to_negative_z():
    """Negative depth input: z must still be negative (same value)."""
    plan = _default_plan(depth=-5.0)
    z = plan["operations"][0]["parameters"]["z"]
    assert z == -5.0


def test_negative_depth_produces_warning():
    plan = _default_plan(depth=-5.0)
    warnings_text = " ".join(plan["warnings"]).lower()
    assert "negative" in warnings_text or "interpreted" in warnings_text


def test_positive_depth_no_negative_warning():
    plan = _default_plan(depth=5.0)
    warnings_text = " ".join(plan["warnings"]).lower()
    assert "negative" not in warnings_text


# ---------------------------------------------------------------------------
# C) hole coordinates
# ---------------------------------------------------------------------------


def test_x_coordinate():
    plan = _default_plan(x=25.5)
    assert plan["operations"][0]["parameters"]["x"] == 25.5


def test_y_coordinate():
    plan = _default_plan(y=-10.0)
    assert plan["operations"][0]["parameters"]["y"] == -10.0


def test_coordinates_are_floats():
    plan = _default_plan(x=0, y=0)
    params = plan["operations"][0]["parameters"]
    assert isinstance(params["x"], float)
    assert isinstance(params["y"], float)
    assert isinstance(params["z"], float)


# ---------------------------------------------------------------------------
# D) material and spindle_speed handling
# ---------------------------------------------------------------------------


def test_no_material_adds_assumption():
    plan = _default_plan(material=None)
    assumptions_text = " ".join(plan["assumptions"]).lower()
    assert "material" in assumptions_text and "not specified" in assumptions_text


def test_material_specified_in_assumptions():
    plan = _default_plan(material="aluminium")
    assumptions_text = " ".join(plan["assumptions"]).lower()
    assert "aluminium" in assumptions_text


def test_no_spindle_speed_adds_warning():
    plan = _default_plan(spindle_speed=None)
    warnings_text = " ".join(plan["warnings"]).lower()
    assert "spindle" in warnings_text


def test_no_spindle_speed_not_in_operation():
    plan = _default_plan(spindle_speed=None)
    assert "spindle_speed" not in plan["operations"][0]


def test_spindle_speed_present_in_operation():
    plan = _default_plan(spindle_speed=1500.0)
    assert plan["operations"][0].get("spindle_speed") == 1500.0


def test_no_spindle_speed_not_in_tool():
    plan = _default_plan(spindle_speed=None)
    assert "spindle_speed" not in plan["tools"][0]


# ---------------------------------------------------------------------------
# E) generate_drill_gcode_from_params — happy path
# ---------------------------------------------------------------------------


def test_full_pipeline_ok():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is True


def test_result_machine_type():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["machine_type"] == "drill"


def test_result_gcode_not_empty():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["gcode"]


def test_result_has_required_keys():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    for key in ("ok", "machine_type", "operation_plan", "gcode",
                "validation", "warnings", "errors", "postprocessor"):
        assert key in result, f"Missing key: {key}"


def test_gcode_has_g21(spindle_speed=1200):
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "G21" in result["gcode"]


def test_gcode_has_g90():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "G90" in result["gcode"]


def test_gcode_has_wcs():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "G54" in result["gcode"]


def test_gcode_has_spindle_start():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "S1200" in result["gcode"]
    assert "M03" in result["gcode"]


def test_gcode_has_plunge():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "Z-5" in result["gcode"]


def test_gcode_has_feedrate():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "F100" in result["gcode"]


def test_gcode_has_m30():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "M30" in result["gcode"]


def test_validation_ok():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["validation"]["ok"] is True


def test_no_errors():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# F) spindle_speed=None — warning but still generates G-code
# ---------------------------------------------------------------------------


def test_no_spindle_ok():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=None,
    )
    # ok depends on G-code validator (spindle warning is a warning, not error)
    assert isinstance(result["ok"], bool)


def test_no_spindle_has_warning():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=None,
    )
    warnings_text = " ".join(result["warnings"]).lower()
    assert "spindle" in warnings_text


def test_no_spindle_no_s_m03_in_gcode():
    """Without a spindle speed, the G-code must not contain S<value> M03."""
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=None,
    )
    gcode = result.get("gcode") or ""
    # S<digits> M03 should not appear (spindle start without speed is unsafe)
    import re
    has_s_m03 = bool(re.search(r"S\d+\s+M03", gcode))
    assert not has_s_m03, "G-code must not contain S<n> M03 when spindle_speed is None"


# ---------------------------------------------------------------------------
# G) negative depth normalisation in full pipeline
# ---------------------------------------------------------------------------


def test_negative_depth_pipeline_ok():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=-5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is True


def test_negative_depth_same_gcode_as_positive():
    pos = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    neg = generate_drill_gcode_from_params(
        x=0, y=0, depth=-5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    # Both should produce Z-5 in the G-code
    assert "Z-5" in pos["gcode"]
    assert "Z-5" in neg["gcode"]


# ---------------------------------------------------------------------------
# H) postprocessor parameter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pp", ["fanuc", "grbl", "marlin", "linuxcnc"])
def test_all_postprocessors(pp):
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
        postprocessor=pp,
    )
    assert isinstance(result, dict)
    assert result["postprocessor"] == pp


def test_unknown_postprocessor_not_ok():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
        postprocessor="not_a_postprocessor",
    )
    assert result["ok"] is False
    assert result["gcode"] == ""


# ---------------------------------------------------------------------------
# I) operation_plan in result
# ---------------------------------------------------------------------------


def test_result_contains_operation_plan():
    result = generate_drill_gcode_from_params(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert isinstance(result["operation_plan"], dict)
    assert result["operation_plan"]["machine_type"] == "drill"
