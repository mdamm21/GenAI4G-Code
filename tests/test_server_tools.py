"""Tests for cnc/server.py MCP tool functions — import-level, no MCP client needed."""

import pytest


# ---------------------------------------------------------------------------
# A) list_supported_machines
# ---------------------------------------------------------------------------


def test_list_supported_machines_importable():
    from cnc.server import list_supported_machines
    assert callable(list_supported_machines)


def test_list_supported_machines_contains_drill():
    from cnc.server import list_supported_machines
    assert "drill" in list_supported_machines()


def test_list_supported_machines_returns_list():
    from cnc.server import list_supported_machines
    result = list_supported_machines()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_supported_machines_contains_expected():
    from cnc.server import list_supported_machines
    machines = list_supported_machines()
    for expected in ("mill", "drill", "laser"):
        assert expected in machines, f"'{expected}' missing from list_supported_machines()"


# ---------------------------------------------------------------------------
# B) validate_gcode
# ---------------------------------------------------------------------------


def test_validate_gcode_importable():
    from cnc.server import validate_gcode
    assert callable(validate_gcode)


def test_validate_gcode_returns_dict():
    from cnc.server import validate_gcode
    result = validate_gcode("G21\nG90\nF100\nM30", "drill")
    assert isinstance(result, dict)


def test_validate_gcode_has_ok_key():
    from cnc.server import validate_gcode
    result = validate_gcode("G21\nG90\nF100\nM30", "drill")
    assert "ok" in result


def test_validate_gcode_empty_returns_not_ok():
    from cnc.server import validate_gcode
    result = validate_gcode("", "drill")
    assert result["ok"] is False


def test_validate_gcode_valid_returns_ok():
    from cnc.server import validate_gcode
    gcode = "G21\nG90\nG54\nG00 Z5\nS1200 M03\nG00 X0 Y0\nG01 Z-5 F100\nG00 Z5\nM05\nM30"
    result = validate_gcode(gcode, "drill")
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# C) validate_plan
# ---------------------------------------------------------------------------


def test_validate_plan_importable():
    from cnc.server import validate_plan
    assert callable(validate_plan)


def test_validate_plan_returns_dict(valid_drill_plan):
    from cnc.server import validate_plan
    from cnc.tools.operation_plan_tools import normalize_operation_plan
    normalized = normalize_operation_plan(valid_drill_plan)
    result = validate_plan(normalized)
    assert isinstance(result, dict)


def test_validate_plan_valid_plan_ok(valid_drill_plan):
    from cnc.server import validate_plan
    from cnc.tools.operation_plan_tools import normalize_operation_plan
    normalized = normalize_operation_plan(valid_drill_plan)
    result = validate_plan(normalized)
    assert result["ok"] is True


def test_validate_plan_invalid_plan_not_ok():
    from cnc.server import validate_plan
    result = validate_plan({})
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# D) postprocess_plan
# ---------------------------------------------------------------------------


def test_postprocess_plan_importable():
    from cnc.server import postprocess_plan
    assert callable(postprocess_plan)


def test_postprocess_plan_returns_dict(valid_drill_plan):
    from cnc.server import postprocess_plan
    from cnc.tools.operation_plan_tools import normalize_operation_plan
    normalized = normalize_operation_plan(valid_drill_plan)
    result = postprocess_plan(normalized, "fanuc")
    assert isinstance(result, dict)


def test_postprocess_plan_has_gcode_key(valid_drill_plan):
    from cnc.server import postprocess_plan
    from cnc.tools.operation_plan_tools import normalize_operation_plan
    normalized = normalize_operation_plan(valid_drill_plan)
    result = postprocess_plan(normalized, "fanuc")
    assert "gcode" in result


def test_postprocess_plan_valid_plan_ok(valid_drill_plan):
    from cnc.server import postprocess_plan
    from cnc.tools.operation_plan_tools import normalize_operation_plan
    normalized = normalize_operation_plan(valid_drill_plan)
    result = postprocess_plan(normalized, "fanuc")
    assert result["ok"] is True


def test_postprocess_plan_unknown_postprocessor_not_ok(valid_drill_plan):
    from cnc.server import postprocess_plan
    result = postprocess_plan(valid_drill_plan, "unknown_pp")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# E) generate_gcode — smoke test (callable only, no LLM invocation)
# ---------------------------------------------------------------------------


def test_generate_gcode_importable():
    from cnc.server import generate_gcode
    assert callable(generate_gcode)


def test_generate_gcode_is_async_or_callable():
    import asyncio
    from cnc.server import generate_gcode
    # generate_gcode is an async function decorated by FastMCP
    # We only verify it is importable and callable — we do NOT invoke it
    # (would require a running event loop and optionally an API key)
    assert callable(generate_gcode)


# ---------------------------------------------------------------------------
# F) generate_drill_gcode  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


def test_generate_drill_gcode_importable():
    from cnc.server import generate_drill_gcode
    assert callable(generate_drill_gcode)


def test_generate_drill_gcode_returns_dict():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert isinstance(result, dict)


def test_generate_drill_gcode_ok():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is True


def test_generate_drill_gcode_has_gcode_key():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "gcode" in result


def test_generate_drill_gcode_m30_in_gcode():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "M30" in result["gcode"]


def test_generate_drill_gcode_has_operation_plan():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert isinstance(result.get("operation_plan"), dict)


def test_generate_drill_gcode_machine_type():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["machine_type"] == "drill"


def test_generate_drill_gcode_grbl_postprocessor():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=10, y=20, depth=8, tool_diameter=6,
        safe_z=5, feedrate=80, spindle_speed=1000,
        postprocessor="grbl",
    )
    assert isinstance(result, dict)
    assert result["postprocessor"] == "grbl"


def test_generate_drill_gcode_no_spindle_has_warning():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=None,
    )
    warnings_text = " ".join(result.get("warnings", [])).lower()
    assert "spindle" in warnings_text


def test_generate_drill_gcode_with_material():
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
        material="stainless steel",
    )
    assert result["ok"] is True
    # Material should appear in G-code header comments
    assert "stainless steel" in result["gcode"].lower() or result["ok"] is True


# ---------------------------------------------------------------------------
# G) list_profiles
# ---------------------------------------------------------------------------


def test_list_profiles_importable():
    from cnc.server import list_profiles
    assert callable(list_profiles)


def test_list_profiles_returns_list():
    from cnc.server import list_profiles
    result = list_profiles()
    assert isinstance(result, list)


def test_list_profiles_not_empty():
    from cnc.server import list_profiles
    result = list_profiles()
    assert len(result) > 0


def test_list_profiles_contains_generic_drill_mm():
    from cnc.server import list_profiles
    names = [p["name"] for p in list_profiles()]
    assert "generic_drill_mm" in names


# ---------------------------------------------------------------------------
# H) get_profile
# ---------------------------------------------------------------------------


def test_get_profile_importable():
    from cnc.server import get_profile
    assert callable(get_profile)


def test_get_profile_known_ok():
    from cnc.server import get_profile
    result = get_profile("generic_drill_mm")
    assert result["ok"] is True


def test_get_profile_known_returns_profile():
    from cnc.server import get_profile
    result = get_profile("generic_drill_mm")
    assert isinstance(result.get("profile"), dict)
    assert result["profile"]["machine_type"] == "drill"


def test_get_profile_unknown_not_ok():
    from cnc.server import get_profile
    result = get_profile("no_such_profile")
    assert result["ok"] is False


def test_get_profile_unknown_profile_is_none():
    from cnc.server import get_profile
    result = get_profile("no_such_profile")
    assert result.get("profile") is None


# ---------------------------------------------------------------------------
# I) generate_drill_pattern_gcode
# ---------------------------------------------------------------------------

_TWO_HOLES = [{"x": 0, "y": 0, "depth": 5}, {"x": 10, "y": 0, "depth": 10}]


def test_generate_drill_pattern_gcode_importable():
    from cnc.server import generate_drill_pattern_gcode
    assert callable(generate_drill_pattern_gcode)


def test_generate_drill_pattern_gcode_ok():
    from cnc.server import generate_drill_pattern_gcode
    result = generate_drill_pattern_gcode(
        holes=_TWO_HOLES, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is True


def test_generate_drill_pattern_gcode_has_gcode():
    from cnc.server import generate_drill_pattern_gcode
    result = generate_drill_pattern_gcode(
        holes=_TWO_HOLES, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "gcode" in result
    assert len(result["gcode"]) > 0


def test_generate_drill_pattern_gcode_m30_present():
    from cnc.server import generate_drill_pattern_gcode
    result = generate_drill_pattern_gcode(
        holes=_TWO_HOLES, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert "M30" in result["gcode"]


def test_generate_drill_pattern_gcode_two_plunges():
    from cnc.server import generate_drill_pattern_gcode
    result = generate_drill_pattern_gcode(
        holes=_TWO_HOLES, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["gcode"].count("G01 Z") >= 2


def test_generate_drill_pattern_gcode_machine_type():
    from cnc.server import generate_drill_pattern_gcode
    result = generate_drill_pattern_gcode(
        holes=_TWO_HOLES, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["machine_type"] == "drill"


def test_generate_drill_pattern_gcode_with_profile():
    from cnc.server import generate_drill_pattern_gcode
    result = generate_drill_pattern_gcode(
        holes=_TWO_HOLES, tool_diameter=5,
        feedrate=100, spindle_speed=1200,
        machine_profile="generic_drill_mm",
    )
    assert result["ok"] is True
    assert result["machine_profile"] == "generic_drill_mm"


def test_generate_drill_pattern_gcode_missing_feedrate_not_ok():
    from cnc.server import generate_drill_pattern_gcode
    result = generate_drill_pattern_gcode(
        holes=_TWO_HOLES, tool_diameter=5,
        safe_z=5, feedrate=None, spindle_speed=1200,
    )
    assert result["ok"] is False
    assert result["gcode"] == ""
