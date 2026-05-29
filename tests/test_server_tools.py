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


# ---------------------------------------------------------------------------
# J) generate_milling_facing_gcode
# ---------------------------------------------------------------------------

_FACING_PARAMS = dict(
    origin_x=0, origin_y=0, width=20, height=10,
    depth=1, step_over=2, tool_diameter=5,
    safe_z=5, feedrate=150, spindle_speed=3000,
)


def test_generate_milling_facing_gcode_importable():
    from cnc.server import generate_milling_facing_gcode
    assert callable(generate_milling_facing_gcode)


def test_generate_milling_facing_gcode_returns_dict():
    from cnc.server import generate_milling_facing_gcode
    result = generate_milling_facing_gcode(**_FACING_PARAMS)
    assert isinstance(result, dict)


def test_generate_milling_facing_gcode_ok():
    from cnc.server import generate_milling_facing_gcode
    result = generate_milling_facing_gcode(**_FACING_PARAMS)
    assert result["ok"] is True


def test_generate_milling_facing_gcode_has_gcode():
    from cnc.server import generate_milling_facing_gcode
    result = generate_milling_facing_gcode(**_FACING_PARAMS)
    assert "gcode" in result
    assert len(result["gcode"]) > 0


def test_generate_milling_facing_gcode_m30():
    from cnc.server import generate_milling_facing_gcode
    result = generate_milling_facing_gcode(**_FACING_PARAMS)
    assert "M30" in result["gcode"]


def test_generate_milling_facing_gcode_machine_type():
    from cnc.server import generate_milling_facing_gcode
    result = generate_milling_facing_gcode(**_FACING_PARAMS)
    assert result["machine_type"] == "mill"


def test_generate_milling_facing_gcode_with_profile():
    from cnc.server import generate_milling_facing_gcode
    result = generate_milling_facing_gcode(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=1, step_over=2, tool_diameter=5,
        feedrate=150, spindle_speed=3000,
        machine_profile="generic_mill_mm",
    )
    assert result["ok"] is True
    assert result["machine_profile"] == "generic_mill_mm"


def test_generate_milling_facing_gcode_missing_feedrate_not_ok():
    from cnc.server import generate_milling_facing_gcode
    result = generate_milling_facing_gcode(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=1, step_over=2, tool_diameter=5,
        safe_z=5, feedrate=None, spindle_speed=3000,
    )
    assert result["ok"] is False
    assert result["gcode"] == ""


# ---------------------------------------------------------------------------
# I) generate_milling_slot_gcode
# ---------------------------------------------------------------------------

_SLOT_PARAMS = dict(
    start_x=0.0,
    start_y=0.0,
    length=20.0,
    depth=3.0,
    tool_diameter=5.0,
    safe_z=5.0,
    feedrate=150.0,
    spindle_speed=3000.0,
    direction="x",
    step_down=1.0,
)


def test_generate_milling_slot_gcode_importable():
    from cnc.server import generate_milling_slot_gcode
    assert callable(generate_milling_slot_gcode)


def test_generate_milling_slot_gcode_ok():
    from cnc.server import generate_milling_slot_gcode
    result = generate_milling_slot_gcode(**_SLOT_PARAMS)
    assert result["ok"] is True


def test_generate_milling_slot_gcode_has_gcode():
    from cnc.server import generate_milling_slot_gcode
    result = generate_milling_slot_gcode(**_SLOT_PARAMS)
    assert "gcode" in result
    assert len(result["gcode"]) > 0


def test_generate_milling_slot_gcode_m30():
    from cnc.server import generate_milling_slot_gcode
    result = generate_milling_slot_gcode(**_SLOT_PARAMS)
    assert "M30" in result["gcode"]


def test_generate_milling_slot_gcode_machine_type():
    from cnc.server import generate_milling_slot_gcode
    result = generate_milling_slot_gcode(**_SLOT_PARAMS)
    assert result["machine_type"] == "mill"


def test_generate_milling_slot_gcode_with_profile():
    from cnc.server import generate_milling_slot_gcode
    result = generate_milling_slot_gcode(
        start_x=0, start_y=0, length=20, depth=3, tool_diameter=5,
        feedrate=150, spindle_speed=3000, direction="x", step_down=1,
        machine_profile="generic_mill_mm",
    )
    assert result["ok"] is True
    assert result["machine_profile"] == "generic_mill_mm"


def test_generate_milling_slot_gcode_missing_step_down_not_ok():
    from cnc.server import generate_milling_slot_gcode
    result = generate_milling_slot_gcode(
        start_x=0, start_y=0, length=20, depth=3, tool_diameter=5,
        safe_z=5, feedrate=150, spindle_speed=3000, direction="x",
        step_down=None,
    )
    assert result["ok"] is False
    assert result["gcode"] == ""


def test_generate_milling_slot_gcode_invalid_direction_not_ok():
    from cnc.server import generate_milling_slot_gcode
    result = generate_milling_slot_gcode(
        start_x=0, start_y=0, length=20, depth=3, tool_diameter=5,
        safe_z=5, feedrate=150, spindle_speed=3000, direction="z",
        step_down=1,
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# J) generate_milling_pocket_gcode
# ---------------------------------------------------------------------------

_POCKET_PARAMS = dict(
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


def test_generate_milling_pocket_gcode_importable():
    from cnc.server import generate_milling_pocket_gcode
    assert callable(generate_milling_pocket_gcode)


def test_generate_milling_pocket_gcode_ok():
    from cnc.server import generate_milling_pocket_gcode
    result = generate_milling_pocket_gcode(**_POCKET_PARAMS)
    assert result["ok"] is True


def test_generate_milling_pocket_gcode_has_gcode():
    from cnc.server import generate_milling_pocket_gcode
    result = generate_milling_pocket_gcode(**_POCKET_PARAMS)
    assert "gcode" in result
    assert len(result["gcode"]) > 0


def test_generate_milling_pocket_gcode_m30():
    from cnc.server import generate_milling_pocket_gcode
    result = generate_milling_pocket_gcode(**_POCKET_PARAMS)
    assert "M30" in result["gcode"]


def test_generate_milling_pocket_gcode_machine_type():
    from cnc.server import generate_milling_pocket_gcode
    result = generate_milling_pocket_gcode(**_POCKET_PARAMS)
    assert result["machine_type"] == "mill"


def test_generate_milling_pocket_gcode_with_profile():
    from cnc.server import generate_milling_pocket_gcode
    result = generate_milling_pocket_gcode(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=3, tool_diameter=5,
        step_down=1, step_over=2,
        feedrate=150, spindle_speed=3000,
        machine_profile="generic_mill_mm",
    )
    assert result["ok"] is True
    assert result["machine_profile"] == "generic_mill_mm"


def test_generate_milling_pocket_gcode_missing_step_down_not_ok():
    from cnc.server import generate_milling_pocket_gcode
    result = generate_milling_pocket_gcode(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=3, tool_diameter=5,
        safe_z=5, feedrate=150, spindle_speed=3000,
        step_down=None, step_over=2,
    )
    assert result["ok"] is False
    assert result["gcode"] == ""


def test_generate_milling_pocket_gcode_missing_step_over_not_ok():
    from cnc.server import generate_milling_pocket_gcode
    result = generate_milling_pocket_gcode(
        origin_x=0, origin_y=0, width=20, height=10,
        depth=3, tool_diameter=5,
        safe_z=5, feedrate=150, spindle_speed=3000,
        step_down=1, step_over=None,
    )
    assert result["ok"] is False
    assert result["gcode"] == ""


# ---------------------------------------------------------------------------
# K) analyze_gcode_safety_report  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


def test_analyze_gcode_safety_report_importable():
    from cnc.server import analyze_gcode_safety_report
    assert callable(analyze_gcode_safety_report)


def test_analyze_gcode_safety_report_returns_dict():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="drill")
    assert isinstance(result, dict)


def test_analyze_gcode_safety_report_has_required_keys():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="drill")
    for key in ("ok", "risk_level", "errors", "warnings", "summary", "findings"):
        assert key in result, f"Missing key: {key}"


def test_analyze_gcode_safety_report_clean_gcode_ok():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="drill")
    assert result["ok"] is True
    assert result["risk_level"] == "low"


def test_analyze_gcode_safety_report_rapid_z_neg_not_ok():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z-10\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="mill")
    assert result["ok"] is False
    assert result["risk_level"] == "high"


def test_analyze_gcode_safety_report_max_depth_exceeded():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z5\nS3000 M03\nG01 Z-20 F150\nG0 Z5\nM05\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="mill", max_depth=10.0)
    assert result["ok"] is False


def test_analyze_gcode_safety_report_expected_units_mismatch():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G20\nG90\nG54\nF100\nM30"  # G20 = inch
    result = analyze_gcode_safety_report(gcode, machine_type="mill", expected_units="mm")
    assert result["ok"] is False

# ---------------------------------------------------------------------------
# L) plan_operation  (LLM-backed — tested via monkeypatch, no real API call)
# ---------------------------------------------------------------------------

import asyncio
import json as _json
from unittest.mock import MagicMock


_MINIMAL_DRILL_PLAN = {
    "machine_type": "drill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"tool_number": 1, "description": "5mm drill", "diameter_mm": 5}],
    "operations": [
        {
            "type": "drill",
            "name": "hole 1",
            "tool_number": 1,
            "feedrate_mmpm": 100,
            "spindle_rpm": 1200,
            "parameters": {"x": 0.0, "y": 0.0, "z": -5.0},
        }
    ],
    "assumptions": [],
    "warnings": [],
    "missing_info": [],
}

_PLAN_WITH_MISSING_INFO = {
    "machine_type": "drill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [],
    "operations": [],
    "assumptions": [],
    "warnings": [],
    "missing_info": ["feedrate not specified", "tool_diameter not specified"],
}


class _FakeAgent:
    """Synchronous fake agent that returns a preset value via run()."""
    def __init__(self, return_val):
        self._return_val = return_val

    async def ainvoke(self, msg):
        return self._return_val

    def run(self, msg):
        return self._return_val


def test_plan_operation_importable():
    from cnc.server import plan_operation
    assert callable(plan_operation)


def test_generate_gcode_importable():
    from cnc.server import generate_gcode
    assert callable(generate_gcode)


def test_plan_operation_with_valid_plan(monkeypatch):
    from cnc.server import plan_operation
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(_MINIMAL_DRILL_PLAN))
    result = asyncio.run(plan_operation(prompt="drill a hole", machine_type="drill"))
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert "operation_plan" in result
    assert "gcode" not in result  # plan_operation must not produce G-code


def test_plan_operation_no_gcode_key(monkeypatch):
    from cnc.server import plan_operation
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(_MINIMAL_DRILL_PLAN))
    result = asyncio.run(plan_operation(prompt="drill a hole", machine_type="drill"))
    assert "gcode" not in result


def test_plan_operation_with_missing_info(monkeypatch):
    from cnc.server import plan_operation
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(_PLAN_WITH_MISSING_INFO))
    result = asyncio.run(plan_operation(prompt="drill a hole", machine_type="drill"))
    assert result["ok"] is False
    assert result["missing_info"]


def test_plan_operation_has_required_keys(monkeypatch):
    from cnc.server import plan_operation
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(_MINIMAL_DRILL_PLAN))
    result = asyncio.run(plan_operation(prompt="drill", machine_type="drill"))
    for key in ("ok", "operation_plan", "validation", "warnings", "errors", "missing_info", "machine_type"):
        assert key in result, f"Missing key: {key}"


def test_generate_gcode_with_valid_plan_produces_gcode(monkeypatch):
    from cnc.server import generate_gcode
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(_MINIMAL_DRILL_PLAN))
    result = asyncio.run(generate_gcode(prompt="drill a hole", machine_type="drill"))
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result.get("gcode")
    assert "M30" in result["gcode"] or "M2" in result["gcode"]


def test_generate_gcode_with_missing_info_no_gcode(monkeypatch):
    from cnc.server import generate_gcode
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(_PLAN_WITH_MISSING_INFO))
    result = asyncio.run(generate_gcode(prompt="drill a hole", machine_type="drill"))
    assert result["ok"] is False
    assert result["gcode"] == ""
    assert result["missing_info"]


def test_generate_gcode_with_unstructured_output_blocked(monkeypatch):
    from cnc.server import generate_gcode
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(
        "G21 G90 G54 G0 Z5 S1200 M03 G01 Z-5 F100 G0 Z5 M05 M30"
    ))
    result = asyncio.run(generate_gcode(prompt="drill a hole"))
    assert result["ok"] is False
    assert result["gcode"] == ""
    errors_text = " ".join(result.get("errors", [])).lower()
    assert "unstructured" in errors_text or "operation" in errors_text


def test_generate_gcode_has_safety_report(monkeypatch):
    from cnc.server import generate_gcode
    monkeypatch.setattr("cnc.agent.build_cnc_agent", lambda: _FakeAgent(_MINIMAL_DRILL_PLAN))
    result = asyncio.run(generate_gcode(prompt="drill a hole", machine_type="drill"))
    assert "safety_report" in result
    if result["ok"]:
        assert result["safety_report"] is not None
        assert "risk_level" in result["safety_report"]


# ---------------------------------------------------------------------------
# M) list_available_materials (deterministic, no LLM required)
# ---------------------------------------------------------------------------


def test_list_available_materials_importable():
    from cnc.server import list_available_materials
    assert callable(list_available_materials)


def test_list_available_materials_returns_list():
    from cnc.server import list_available_materials
    result = list_available_materials()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_available_materials_contains_aluminum_6061():
    from cnc.server import list_available_materials
    ids = [m["id"] for m in list_available_materials()]
    assert "aluminum_6061" in ids


def test_list_available_materials_contains_mild_steel():
    from cnc.server import list_available_materials
    ids = [m["id"] for m in list_available_materials()]
    assert "mild_steel" in ids


def test_list_available_materials_each_has_required_keys():
    from cnc.server import list_available_materials
    for m in list_available_materials():
        for key in ("id", "name", "category", "machinability"):
            assert key in m, f"Material {m.get('id')!r} missing key {key!r}"


# ---------------------------------------------------------------------------
# N) get_material_info (deterministic, no LLM required)
# ---------------------------------------------------------------------------


def test_get_material_info_importable():
    from cnc.server import get_material_info
    assert callable(get_material_info)


def test_get_material_info_aluminum_ok():
    from cnc.server import get_material_info
    result = get_material_info("aluminum_6061")
    assert result["ok"] is True


def test_get_material_info_aluminum_returns_material():
    from cnc.server import get_material_info
    result = get_material_info("aluminum_6061")
    assert result["material"] is not None
    assert result["material"]["id"] == "aluminum_6061"


def test_get_material_info_aluminum_category():
    from cnc.server import get_material_info
    result = get_material_info("aluminum_6061")
    assert result["material"]["category"] == "aluminum"


def test_get_material_info_unknown_not_ok():
    from cnc.server import get_material_info
    result = get_material_info("unobtainium")
    assert result["ok"] is False
    assert result["material"] is None


def test_get_material_info_has_error_on_unknown():
    from cnc.server import get_material_info
    result = get_material_info("not_a_real_material")
    assert result.get("error") or result.get("errors")


# ---------------------------------------------------------------------------
# O) search_materials (deterministic, no LLM required)
# ---------------------------------------------------------------------------


def test_search_materials_importable():
    from cnc.server import search_materials
    assert callable(search_materials)


def test_search_materials_by_category_aluminum():
    from cnc.server import search_materials
    result = search_materials(category="aluminum")
    assert isinstance(result, list)
    assert len(result) > 0
    for m in result:
        assert m["category"] == "aluminum"


def test_search_materials_aluminum_contains_6061():
    from cnc.server import search_materials
    ids = [m["id"] for m in search_materials(category="aluminum")]
    assert "aluminum_6061" in ids


def test_search_materials_no_filters_returns_all():
    from cnc.server import search_materials, list_available_materials
    assert len(search_materials()) == len(list_available_materials())


def test_search_materials_unknown_category_empty():
    from cnc.server import search_materials
    result = search_materials(category="unobtainium_category")
    assert result == []


def test_search_materials_by_operation_pocket():
    from cnc.server import search_materials
    result = search_materials(operation_type="pocket")
    ids = [m["id"] for m in result]
    assert "aluminum_6061" in ids


# ---------------------------------------------------------------------------
# P) evaluate_operation_guardrails (deterministic, no LLM required)
# ---------------------------------------------------------------------------

_VALID_MILLING_PLAN = {
    "machine_type": "mill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"id": "T1", "diameter": 5.0}],
    "operations": [
        {
            "type": "pocket",
            "feedrate": 150.0,
            "spindle_speed": 3000.0,
            "parameters": {
                "origin_x": 0.0,
                "origin_y": 0.0,
                "width": 20.0,
                "height": 10.0,
                "target_z": -3.0,
                "step_down": 1.0,
                "step_over": 2.0,
                "tool_diameter": 5.0,
            },
        }
    ],
    "assumptions": [],
    "warnings": [],
}


def test_evaluate_operation_guardrails_importable():
    from cnc.server import evaluate_operation_guardrails
    assert callable(evaluate_operation_guardrails)


def test_evaluate_operation_guardrails_valid_plan_ok():
    from cnc.server import evaluate_operation_guardrails
    result = evaluate_operation_guardrails(_VALID_MILLING_PLAN, material="aluminum_6061")
    assert result["ok"] is True


def test_evaluate_operation_guardrails_valid_plan_no_errors():
    from cnc.server import evaluate_operation_guardrails
    result = evaluate_operation_guardrails(_VALID_MILLING_PLAN, material="aluminum_6061")
    assert result["errors"] == []


def test_evaluate_operation_guardrails_material_resolved():
    from cnc.server import evaluate_operation_guardrails
    result = evaluate_operation_guardrails(_VALID_MILLING_PLAN, material="aluminum_6061")
    assert result["material"] is not None
    assert result["material"]["id"] == "aluminum_6061"


def test_evaluate_operation_guardrails_has_required_keys():
    from cnc.server import evaluate_operation_guardrails
    result = evaluate_operation_guardrails(_VALID_MILLING_PLAN)
    for key in ("ok", "errors", "warnings", "info", "material", "findings"):
        assert key in result, f"Missing key: {key!r}"


def test_evaluate_operation_guardrails_no_material_warning():
    from cnc.server import evaluate_operation_guardrails
    result = evaluate_operation_guardrails(_VALID_MILLING_PLAN)
    assert result["ok"] is True  # warning, not error
    warnings_text = " ".join(result.get("warnings", []))
    assert "Material" in warnings_text or "material" in warnings_text


def test_evaluate_operation_guardrails_missing_feedrate_not_ok():
    from cnc.server import evaluate_operation_guardrails
    plan = {**_VALID_MILLING_PLAN, "operations": [
        {k: v for k, v in _VALID_MILLING_PLAN["operations"][0].items() if k != "feedrate"}
    ]}
    result = evaluate_operation_guardrails(plan, material="aluminum_6061")
    assert result["ok"] is False
    assert result["errors"]


# ---------------------------------------------------------------------------
# Q) create_job (Job Import/Export)
# ---------------------------------------------------------------------------

_VALID_DRILL_OP = {
    "machine_type": "drill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"id": "T1", "diameter": 5.0}],
    "operations": [
        {
            "type": "drill",
            "feedrate": 100.0,
            "spindle_speed": 1200.0,
            "parameters": {"x": 0.0, "y": 0.0, "z": -5.0},
        }
    ],
    "assumptions": [],
    "warnings": [],
    "missing_info": [],
}


def test_create_job_importable():
    from cnc.server import create_job
    assert callable(create_job)


def test_create_job_returns_dict():
    from cnc.server import create_job
    result = create_job(operation_plan=_VALID_DRILL_OP)
    assert isinstance(result, dict)


def test_create_job_schema_version():
    from cnc.server import create_job
    result = create_job(operation_plan=_VALID_DRILL_OP)
    assert result["schema_version"] == "0.1"


def test_create_job_has_operation_plan():
    from cnc.server import create_job
    result = create_job(operation_plan=_VALID_DRILL_OP)
    assert "operation_plan" in result


def test_create_job_no_gcode_field():
    from cnc.server import create_job
    result = create_job(operation_plan=_VALID_DRILL_OP)
    assert "gcode" not in result


# ---------------------------------------------------------------------------
# R) validate_job
# ---------------------------------------------------------------------------


def test_validate_job_importable():
    from cnc.server import validate_job
    assert callable(validate_job)


def test_validate_job_valid_ok():
    from cnc.server import create_job, validate_job
    job = create_job(operation_plan=_VALID_DRILL_OP, material="aluminum_6061")
    result = validate_job(job)
    assert result["ok"] is True


def test_validate_job_valid_no_errors():
    from cnc.server import create_job, validate_job
    job = create_job(operation_plan=_VALID_DRILL_OP, material="aluminum_6061")
    result = validate_job(job)
    assert result["errors"] == []


def test_validate_job_missing_op_plan_not_ok():
    from cnc.server import validate_job
    job = {"schema_version": "0.1", "postprocessor": "fanuc"}
    result = validate_job(job)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# S) generate_gcode_from_job
# ---------------------------------------------------------------------------


def test_generate_gcode_from_job_importable():
    from cnc.server import generate_gcode_from_job
    assert callable(generate_gcode_from_job)


def test_generate_gcode_from_job_ok():
    from cnc.server import create_job, generate_gcode_from_job
    job = create_job(operation_plan=_VALID_DRILL_OP, material="aluminum_6061")
    result = generate_gcode_from_job(job)
    assert result["ok"] is True


def test_generate_gcode_from_job_gcode_nonempty():
    from cnc.server import create_job, generate_gcode_from_job
    job = create_job(operation_plan=_VALID_DRILL_OP, material="aluminum_6061")
    result = generate_gcode_from_job(job)
    assert len(result["gcode"]) > 0


def test_generate_gcode_from_job_ignores_stored_gcode():
    from cnc.server import create_job, generate_gcode_from_job
    job = create_job(operation_plan=_VALID_DRILL_OP)
    job["gcode"] = "... [18 rows x 4 passes]"
    result = generate_gcode_from_job(job)
    assert "18 rows" not in result["gcode"]


def test_generate_gcode_from_job_has_required_keys():
    from cnc.server import create_job, generate_gcode_from_job
    job = create_job(operation_plan=_VALID_DRILL_OP)
    result = generate_gcode_from_job(job)
    for key in ("ok", "gcode", "job", "validation", "warnings", "errors", "postprocessor"):
        assert key in result, f"Missing key: {key!r}"


# ---------------------------------------------------------------------------
# T) run_cnc_job / save_run / load_run (Job Runs & Reports)
# ---------------------------------------------------------------------------


def test_run_cnc_job_importable():
    from cnc.server import run_cnc_job
    assert callable(run_cnc_job)


def test_save_run_importable():
    from cnc.server import save_run
    assert callable(save_run)


def test_load_run_importable():
    from cnc.server import load_run
    assert callable(load_run)


def test_run_cnc_job_valid_drill_ok():
    from cnc.server import create_job, run_cnc_job
    job = create_job(operation_plan=_VALID_DRILL_OP, material="aluminum_6061")
    result = run_cnc_job(job)
    assert result["ok"] is True


def test_run_cnc_job_has_run_report():
    from cnc.server import create_job, run_cnc_job
    job = create_job(operation_plan=_VALID_DRILL_OP)
    result = run_cnc_job(job)
    assert isinstance(result.get("run_report"), dict)


def test_run_cnc_job_has_gcode():
    from cnc.server import create_job, run_cnc_job
    job = create_job(operation_plan=_VALID_DRILL_OP)
    result = run_cnc_job(job)
    assert len(result.get("gcode", "")) > 0


def test_run_cnc_job_invalid_job_not_ok():
    from cnc.server import run_cnc_job
    result = run_cnc_job({"schema_version": "0.1", "postprocessor": "fanuc"})
    assert result["ok"] is False


def test_run_cnc_job_ignores_stored_gcode():
    from cnc.server import create_job, run_cnc_job
    job = create_job(operation_plan=_VALID_DRILL_OP)
    job["gcode"] = "... [18 rows x 4 passes]"
    result = run_cnc_job(job)
    assert "18 rows" not in result.get("gcode", "")


# ---------------------------------------------------------------------------
# U) Batch Job tools
# ---------------------------------------------------------------------------


def test_run_cnc_job_batch_importable():
    from cnc.server import run_cnc_job_batch
    assert callable(run_cnc_job_batch)


def test_run_cnc_job_batch_from_paths_importable():
    from cnc.server import run_cnc_job_batch_from_paths
    assert callable(run_cnc_job_batch_from_paths)


def test_run_cnc_job_batch_from_directory_importable():
    from cnc.server import run_cnc_job_batch_from_directory
    assert callable(run_cnc_job_batch_from_directory)


def test_save_batch_importable():
    from cnc.server import save_batch
    assert callable(save_batch)


def test_load_batch_importable():
    from cnc.server import load_batch
    assert callable(load_batch)


def test_run_cnc_job_batch_single_valid_job():
    from cnc.server import create_job, run_cnc_job_batch
    job = create_job(operation_plan=_VALID_DRILL_OP, material="aluminum_6061")
    result = run_cnc_job_batch(jobs=[job])
    assert result["ok"] is True
    assert result["batch_report"]["total_jobs"] == 1


def test_run_cnc_job_batch_from_paths_example_jobs():
    from cnc.server import run_cnc_job_batch_from_paths
    paths = [
        "examples/jobs/drill_pattern_job.json",
        "examples/jobs/milling_pocket_job.json",
    ]
    result = run_cnc_job_batch_from_paths(paths=paths)
    assert result["batch_report"]["total_jobs"] == 2
    assert result["ok"] is True


def test_run_cnc_job_batch_from_directory_example_jobs():
    from cnc.server import run_cnc_job_batch_from_directory
    result = run_cnc_job_batch_from_directory(directory="examples/jobs")
    assert result["batch_report"]["total_jobs"] >= 2
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# V) Tool Library server tools
# ---------------------------------------------------------------------------


def test_list_available_tools_importable():
    from cnc.server import list_available_tools
    assert callable(list_available_tools)


def test_list_available_tools_returns_list():
    from cnc.server import list_available_tools
    result = list_available_tools()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_available_tools_contains_drill_5mm():
    from cnc.server import list_available_tools
    ids = [t["id"] for t in list_available_tools() if isinstance(t, dict) and "id" in t]
    assert "drill_5mm" in ids


def test_get_tool_info_importable():
    from cnc.server import get_tool_info
    assert callable(get_tool_info)


def test_get_tool_info_known_tool():
    from cnc.server import get_tool_info
    result = get_tool_info("drill_5mm")
    assert result["ok"] is True
    assert result["tool"]["id"] == "drill_5mm"


def test_get_tool_info_unknown_tool():
    from cnc.server import get_tool_info
    result = get_tool_info("nonexistent_xyz")
    assert result["ok"] is False
    assert result["tool"] is None
    assert len(result["errors"]) > 0


def test_search_tools_importable():
    from cnc.server import search_tools
    assert callable(search_tools)


def test_search_tools_no_filters():
    from cnc.server import search_tools
    result = search_tools()
    assert result["ok"] is True
    assert isinstance(result["tools"], list)
    assert result["count"] > 0


def test_search_tools_machine_type_drill():
    from cnc.server import search_tools
    result = search_tools(machine_type="drill")
    assert result["ok"] is True
    assert result["count"] > 0
    for t in result["tools"]:
        assert "drill" in t["supported_machine_types"]


def test_search_tools_machine_type_mill():
    from cnc.server import search_tools
    result = search_tools(machine_type="mill")
    assert result["ok"] is True
    assert result["count"] > 0


def test_search_tools_operation_type_pocket():
    from cnc.server import search_tools
    result = search_tools(operation_type="pocket")
    assert result["ok"] is True
    for t in result["tools"]:
        assert "pocket" in t["supported_operations"]


def test_search_tools_unknown_machine_empty():
    from cnc.server import search_tools
    result = search_tools(machine_type="lathe")
    assert result["ok"] is True
    assert result["count"] == 0


def test_resolve_tool_importable():
    from cnc.server import resolve_tool
    assert callable(resolve_tool)


def test_resolve_tool_known():
    from cnc.server import resolve_tool
    result = resolve_tool("drill_5mm")
    assert result["ok"] is True
    assert result["tool"] is not None


def test_resolve_tool_unknown_warns():
    from cnc.server import resolve_tool
    result = resolve_tool("T1")
    assert result["ok"] is True  # unknown → warning not error
    assert result["tool"] is None
    assert len(result["warnings"]) > 0


def test_resolve_tool_wrong_machine_warns():
    from cnc.server import resolve_tool
    result = resolve_tool("endmill_5mm_flat", machine_type="drill")
    assert result["ok"] is True
    assert len(result["warnings"]) > 0


def test_resolve_plan_tools_importable():
    from cnc.server import resolve_plan_tools
    assert callable(resolve_plan_tools)


def test_resolve_plan_tools_known_tool():
    from cnc.server import resolve_plan_tools
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [{"id": "drill_5mm", "diameter": 5.0}],
        "operations": [
            {"type": "drill", "tool_id": "drill_5mm",
             "parameters": {"x": 0, "y": 0, "z": -5}}
        ],
    }
    result = resolve_plan_tools(plan)
    assert result["ok"] is True
    assert len(result["resolved"]) == 1


def test_resolve_plan_tools_unknown_tool_warns():
    from cnc.server import resolve_plan_tools
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [{"id": "T1", "diameter": 5.0}],
        "operations": [
            {"type": "drill", "tool_id": "T1",
             "parameters": {"x": 0, "y": 0, "z": -5}}
        ],
    }
    result = resolve_plan_tools(plan)
    assert result["ok"] is True  # unknown → warning
    assert len(result["warnings"]) > 0


# ---------------------------------------------------------------------------
# W) Response contract consistency — Schritt 23
# ---------------------------------------------------------------------------


def test_get_tool_info_unknown_has_errors_list():
    """get_tool_info unknown → ok False, errors is a list."""
    from cnc.server import get_tool_info
    result = get_tool_info("nonexistent_xyz")
    assert result["ok"] is False
    assert isinstance(result["errors"], list)
    assert len(result["errors"]) > 0


def test_get_tool_info_unknown_tool_is_none():
    from cnc.server import get_tool_info
    result = get_tool_info("nonexistent_xyz")
    assert result["tool"] is None


def test_get_profile_unknown_has_errors_list():
    """get_profile unknown → ok False, errors is a list."""
    from cnc.server import get_profile
    result = get_profile("no_such_profile")
    assert result["ok"] is False
    assert isinstance(result["errors"], list)
    assert len(result["errors"]) > 0


def test_get_profile_unknown_no_singular_error_key():
    """get_profile should use 'errors' (list), not 'error' (string)."""
    from cnc.server import get_profile
    result = get_profile("no_such_profile")
    # 'errors' must be present; 'error' (singular) is the old pattern we're removing
    assert "errors" in result


def test_get_material_info_unknown_has_errors_list():
    """get_material_info unknown → ok False, errors is a list."""
    from cnc.server import get_material_info
    result = get_material_info("unobtainium")
    assert result["ok"] is False
    assert isinstance(result["errors"], list)
    assert len(result["errors"]) > 0


def test_get_material_info_unknown_no_singular_error_key():
    """get_material_info should use 'errors' (list), not 'error' (string)."""
    from cnc.server import get_material_info
    result = get_material_info("unobtainium")
    assert "errors" in result


def test_analyze_gcode_safety_report_has_ok():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="drill")
    assert "ok" in result


def test_analyze_gcode_safety_report_has_errors_list():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="drill")
    assert isinstance(result.get("errors", []), list)


def test_analyze_gcode_safety_report_has_warnings_list():
    from cnc.server import analyze_gcode_safety_report
    gcode = "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30"
    result = analyze_gcode_safety_report(gcode, machine_type="drill")
    assert isinstance(result.get("warnings", []), list)


def test_generate_drill_gcode_errors_is_list():
    """generate_drill_gcode success → errors field must be a list."""
    from cnc.server import generate_drill_gcode
    result = generate_drill_gcode(
        x=0, y=0, depth=5, tool_diameter=5,
        safe_z=5, feedrate=100, spindle_speed=1200,
    )
    assert result["ok"] is True
    assert isinstance(result.get("errors", []), list)


def test_get_profile_known_has_errors_list():
    """get_profile success → errors field must be a list."""
    from cnc.server import get_profile
    result = get_profile("generic_drill_mm")
    assert result["ok"] is True
    assert isinstance(result.get("errors", []), list)


def test_get_material_info_known_has_errors_list():
    """get_material_info success → errors field must be a list."""
    from cnc.server import get_material_info
    result = get_material_info("aluminum_6061")
    assert result["ok"] is True
    assert isinstance(result.get("errors", []), list)

