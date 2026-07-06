"""Tests for cnc/tools/operation_plan_tools.py — normalization and tool reference handling."""

import pytest
from cnc.tools.operation_plan_tools import (
    normalize_operation_plan,
    normalize_tool_references,
    get_plan_local_tool_ids,
)


# ---------------------------------------------------------------------------
# A) normalize_tool_references — basic
# ---------------------------------------------------------------------------


def test_normalize_assigns_plan_local_id():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [
            {
                "tool_number": 1,
                "description": "8.5mm HSS twist drill",
                "diameter_mm": 8.5,
                "type": "drill",
            }
        ],
        "operations": [
            {"tool_number": 1, "type": "drill", "feedrate_mmpm": 80,
             "parameters": {"x": 0, "y": 0, "z": -18}},
        ],
        "warnings": [],
    }

    result = normalize_tool_references(plan)

    assert result["tools"][0]["id"] == "T1"
    assert result["operations"][0]["tool_id"] == "T1"


def test_normalize_preserves_real_tool_id():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [
            {
                "id": "drill_5mm",
                "tool_number": 1,
                "description": "5mm drill",
                "diameter_mm": 5.0,
                "type": "drill",
            }
        ],
        "operations": [
            {"tool_id": "drill_5mm", "tool_number": 1, "type": "drill",
             "feedrate_mmpm": 150, "parameters": {"x": 0, "y": 0, "z": -10}},
        ],
        "warnings": [],
    }

    result = normalize_tool_references(plan)

    assert result["tools"][0]["id"] == "drill_5mm"
    # Operation already has a real tool_id, should keep it
    assert result["operations"][0]["tool_id"] == "drill_5mm"


def test_normalize_bare_numeric_id():
    """A tool with id='1' should be normalized to 'T1'."""
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [
            {"id": "1", "description": "Test", "diameter_mm": 5.0, "type": "drill"}
        ],
        "operations": [
            {"tool_id": "1", "type": "drill", "feedrate_mmpm": 80,
             "parameters": {"x": 0, "y": 0, "z": -5}},
        ],
        "warnings": [],
    }

    result = normalize_tool_references(plan)

    assert result["tools"][0]["id"] == "T1"
    assert result["operations"][0]["tool_id"] == "T1"


# ---------------------------------------------------------------------------
# B) get_plan_local_tool_ids
# ---------------------------------------------------------------------------


def test_get_plan_local_tool_ids():
    plan = {
        "tools": [
            {"id": "T1", "tool_number": 1},
            {"id": "drill_5mm", "tool_number": 2},
        ],
    }

    ids = get_plan_local_tool_ids(plan)
    assert "T1" in ids
    assert "drill_5mm" in ids


def test_get_plan_local_tool_ids_empty():
    assert get_plan_local_tool_ids({}) == set()
    assert get_plan_local_tool_ids(None) == set()


# ---------------------------------------------------------------------------
# C) Tool resolution after normalization — no false unknown warnings
# ---------------------------------------------------------------------------


def test_normalized_plan_no_unknown_tool_warning():
    """After normalization, plan-local T1 should not trigger unknown tool warning."""
    from cnc.tools.validation_tools import validate_operation_plan

    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [
            {
                "tool_number": 1,
                "description": "8.5mm HSS twist drill",
                "diameter_mm": 8.5,
                "type": "drill",
            }
        ],
        "operations": [
            {"tool_number": 1, "type": "drill", "feedrate_mmpm": 80,
             "spindle_rpm": 1200, "parameters": {"x": 0, "y": 0, "z": -18}},
        ],
        "warnings": [],
    }

    plan = normalize_tool_references(plan)
    val = validate_operation_plan(plan)

    # No "not in the built-in tool library" warning for T1
    unknown_warnings = [w for w in val["warnings"] if "not in the built-in tool library" in w]
    assert unknown_warnings == [], f"Unexpected unknown tool warnings: {unknown_warnings}"


# ---------------------------------------------------------------------------
# D) Multiple tools
# ---------------------------------------------------------------------------


def test_normalize_multiple_tools():
    plan = {
        "machine_type": "mill",
        "units": "mm",
        "safe_z": 10.0,
        "tools": [
            {"tool_number": 1, "description": "5mm drill", "type": "drill", "diameter_mm": 5.0},
            {"tool_number": 2, "description": "10mm end mill", "type": "end_mill", "diameter_mm": 10.0},
        ],
        "operations": [
            {"tool_number": 1, "type": "drill", "feedrate_mmpm": 80,
             "parameters": {"x": 0, "y": 0, "z": -10}},
            {"tool_number": 2, "type": "pocket", "feedrate_mmpm": 200,
             "parameters": {"origin_x": 0, "origin_y": 0}},
        ],
        "warnings": [],
    }

    result = normalize_tool_references(plan)

    assert result["tools"][0]["id"] == "T1"
    assert result["tools"][1]["id"] == "T2"
    assert result["operations"][0]["tool_id"] == "T1"
    assert result["operations"][1]["tool_id"] == "T2"
