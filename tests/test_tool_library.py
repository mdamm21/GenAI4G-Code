"""Tests for cnc/tools/tool_library.py — no LLM, no API key required."""

from __future__ import annotations

import pytest

from cnc.tools.tool_library import (
    find_tools,
    get_tool,
    list_tools,
    resolve_operation_plan_tools,
    resolve_tool_id,
)


# ---------------------------------------------------------------------------
# A) list_tools
# ---------------------------------------------------------------------------


def test_list_tools_returns_list():
    result = list_tools()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_tools_contains_drill_5mm():
    ids = [t["id"] for t in list_tools()]
    assert "drill_5mm" in ids


def test_list_tools_contains_endmill_5mm_flat():
    ids = [t["id"] for t in list_tools()]
    assert "endmill_5mm_flat" in ids


def test_list_tools_returns_copies():
    tools1 = list_tools()
    tools1[0]["name"] = "MUTATED"
    tools2 = list_tools()
    assert tools2[0]["name"] != "MUTATED"


def test_list_tools_has_required_fields():
    for tool in list_tools():
        assert "id" in tool
        assert "name" in tool
        assert "tool_type" in tool
        assert "supported_machine_types" in tool
        assert "supported_operations" in tool


# ---------------------------------------------------------------------------
# B) get_tool
# ---------------------------------------------------------------------------


def test_get_tool_returns_drill_5mm():
    tool = get_tool("drill_5mm")
    assert tool is not None
    assert tool["id"] == "drill_5mm"


def test_get_tool_returns_none_for_unknown():
    assert get_tool("nonexistent_tool_xyz") is None


def test_get_tool_returns_copy():
    tool = get_tool("drill_5mm")
    tool["name"] = "MUTATED"
    tool2 = get_tool("drill_5mm")
    assert tool2["name"] != "MUTATED"


def test_get_tool_drill_3mm():
    tool = get_tool("drill_3mm")
    assert tool is not None
    assert tool["diameter"] == 3.0


def test_get_tool_endmill_3mm_flat():
    tool = get_tool("endmill_3mm_flat")
    assert tool is not None
    assert tool["tool_type"] == "end_mill"


def test_get_tool_drill_5mm_supports_drill_machine():
    tool = get_tool("drill_5mm")
    assert "drill" in tool["supported_machine_types"]


def test_get_tool_endmill_supports_mill_machine():
    tool = get_tool("endmill_5mm_flat")
    assert "mill" in tool["supported_machine_types"]


# ---------------------------------------------------------------------------
# C) find_tools — no filters
# ---------------------------------------------------------------------------


def test_find_tools_no_filters_returns_all():
    all_tools = list_tools()
    found = find_tools()
    assert len(found) == len(all_tools)


# ---------------------------------------------------------------------------
# D) find_tools — machine_type filter
# ---------------------------------------------------------------------------


def test_find_tools_machine_type_drill():
    tools = find_tools(machine_type="drill")
    assert len(tools) > 0
    for t in tools:
        assert "drill" in t["supported_machine_types"]


def test_find_tools_machine_type_mill():
    tools = find_tools(machine_type="mill")
    assert len(tools) > 0
    for t in tools:
        assert "mill" in t["supported_machine_types"]


def test_find_tools_machine_type_lathe_empty():
    # No lathe tools in builtin registry
    tools = find_tools(machine_type="lathe")
    assert tools == []


# ---------------------------------------------------------------------------
# E) find_tools — operation_type filter
# ---------------------------------------------------------------------------


def test_find_tools_operation_drill():
    tools = find_tools(operation_type="drill")
    assert len(tools) > 0
    for t in tools:
        assert "drill" in t["supported_operations"]


def test_find_tools_operation_pocket():
    tools = find_tools(operation_type="pocket")
    assert len(tools) > 0
    for t in tools:
        assert "pocket" in t["supported_operations"]


def test_find_tools_operation_unknown_empty():
    tools = find_tools(operation_type="laser_cut_xyz")
    assert tools == []


# ---------------------------------------------------------------------------
# F) find_tools — tool_type filter
# ---------------------------------------------------------------------------


def test_find_tools_tool_type_drill():
    tools = find_tools(tool_type="drill")
    assert len(tools) > 0
    for t in tools:
        assert t["tool_type"] == "drill"


def test_find_tools_tool_type_end_mill():
    tools = find_tools(tool_type="end_mill")
    assert len(tools) > 0
    for t in tools:
        assert t["tool_type"] == "end_mill"


def test_find_tools_combined_filter():
    tools = find_tools(machine_type="mill", tool_type="end_mill")
    assert len(tools) > 0
    for t in tools:
        assert "mill" in t["supported_machine_types"]
        assert t["tool_type"] == "end_mill"


# ---------------------------------------------------------------------------
# G) resolve_tool_id
# ---------------------------------------------------------------------------


def test_resolve_tool_id_known_tool_ok():
    result = resolve_tool_id("drill_5mm")
    assert result["ok"] is True
    assert result["tool"] is not None
    assert result["tool"]["id"] == "drill_5mm"


def test_resolve_tool_id_unknown_ok_with_warning():
    result = resolve_tool_id("T1")
    assert result["ok"] is True   # unknown is a warning, not error
    assert result["tool"] is None
    assert len(result["warnings"]) > 0


def test_resolve_tool_id_wrong_machine_warns():
    # endmill_5mm_flat only supports "mill", not "drill"
    result = resolve_tool_id("endmill_5mm_flat", machine_type="drill")
    assert result["ok"] is True
    assert any("machine" in w.lower() or "drill" in w for w in result["warnings"])


def test_resolve_tool_id_wrong_operation_warns():
    # drill_5mm does not support "facing"
    result = resolve_tool_id("drill_5mm", operation_type="facing")
    assert result["ok"] is True
    assert len(result["warnings"]) > 0


def test_resolve_tool_id_correct_machine_no_warning():
    result = resolve_tool_id("drill_5mm", machine_type="drill")
    assert result["ok"] is True
    assert result["tool"] is not None
    # No machine-type warning
    assert not any("machine" in w.lower() for w in result["warnings"])


def test_resolve_tool_id_correct_operation_no_warning():
    result = resolve_tool_id("drill_5mm", operation_type="drill")
    assert result["ok"] is True
    assert not any("operation" in w.lower() for w in result["warnings"])


def test_resolve_tool_id_units_mismatch_warns():
    result = resolve_tool_id("drill_5mm", units="inch")
    assert result["ok"] is True
    assert any("inch" in w or "units" in w.lower() for w in result["warnings"])


def test_resolve_tool_id_always_has_ok_errors_warnings():
    result = resolve_tool_id("whatever")
    assert "ok" in result
    assert "tool" in result
    assert "warnings" in result
    assert "errors" in result


# ---------------------------------------------------------------------------
# H) resolve_operation_plan_tools
# ---------------------------------------------------------------------------

_DRILL_PLAN_T1 = {
    "machine_type": "drill",
    "units": "mm",
    "safe_z": 5.0,
    "tools": [{"id": "T1", "diameter": 5.0}],
    "operations": [
        {"type": "drill", "tool_id": "T1", "parameters": {"x": 0, "y": 0, "z": -5}}
    ],
}

_DRILL_PLAN_KNOWN = {
    "machine_type": "drill",
    "units": "mm",
    "safe_z": 5.0,
    "tools": [{"id": "drill_5mm", "diameter": 5.0}],
    "operations": [
        {"type": "drill", "tool_id": "drill_5mm", "parameters": {"x": 0, "y": 0, "z": -5}}
    ],
}


def test_resolve_operation_plan_tools_ok_key_present():
    result = resolve_operation_plan_tools(_DRILL_PLAN_T1)
    assert "ok" in result
    assert "warnings" in result
    assert "errors" in result
    assert "resolved" in result


def test_resolve_operation_plan_tools_unknown_tool_is_warning():
    result = resolve_operation_plan_tools(_DRILL_PLAN_T1)
    assert result["ok"] is True  # unknown tool → warning, not error
    assert len(result["warnings"]) > 0


def test_resolve_operation_plan_tools_known_tool_resolves():
    result = resolve_operation_plan_tools(_DRILL_PLAN_KNOWN)
    assert result["ok"] is True
    assert len(result["resolved"]) == 1
    assert result["resolved"][0]["id"] == "drill_5mm"


def test_resolve_operation_plan_tools_non_dict_returns_error():
    result = resolve_operation_plan_tools("not a dict")
    assert result["ok"] is False
    assert len(result["errors"]) > 0
