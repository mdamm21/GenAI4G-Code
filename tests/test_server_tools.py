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
