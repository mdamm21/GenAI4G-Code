"""Tests for cnc/tools/validation_tools.py — OperationPlan structural validation."""

import pytest
from cnc.tools.validation_tools import validate_operation_plan
from cnc.tools.operation_plan_tools import normalize_operation_plan


# ---------------------------------------------------------------------------
# A) Fully-specified drill plan (via fixture)
# ---------------------------------------------------------------------------


def test_valid_drill_plan_ok(valid_drill_plan):
    normalized = normalize_operation_plan(valid_drill_plan)
    result = validate_operation_plan(normalized)
    assert result["ok"] is True
    assert result["errors"] == []


def test_valid_drill_plan_result_has_required_keys(valid_drill_plan):
    result = validate_operation_plan(valid_drill_plan)
    assert "ok" in result
    assert "errors" in result
    assert "warnings" in result


# ---------------------------------------------------------------------------
# B) Drill plan without safe_z
# ---------------------------------------------------------------------------


def test_missing_safe_z_is_error():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        # safe_z intentionally omitted
        "operations": [
            {
                "type": "drill",
                "parameters": {"x": 0, "y": 0, "z": -5},
                "feedrate": 100,
            }
        ],
    }
    result = validate_operation_plan(plan)
    assert result["ok"] is False
    errors_text = " ".join(result["errors"]).lower()
    assert "safe_z" in errors_text


# ---------------------------------------------------------------------------
# C) Drill plan without x/y/z parameters
# ---------------------------------------------------------------------------


def test_missing_x_is_error():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [
            {
                "type": "drill",
                "parameters": {"y": 0, "z": -5},  # x missing
                "feedrate": 100,
            }
        ],
    }
    result = validate_operation_plan(plan)
    assert result["ok"] is False
    assert any("'x'" in e or "x" in e.lower() for e in result["errors"])


def test_missing_y_is_error():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [
            {
                "type": "drill",
                "parameters": {"x": 0, "z": -5},  # y missing
                "feedrate": 100,
            }
        ],
    }
    result = validate_operation_plan(plan)
    assert result["ok"] is False
    assert any("'y'" in e or " y" in e.lower() for e in result["errors"])


def test_missing_z_is_error():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [
            {
                "type": "drill",
                "parameters": {"x": 0, "y": 0},  # z missing
                "feedrate": 100,
            }
        ],
    }
    result = validate_operation_plan(plan)
    assert result["ok"] is False
    assert any("'z'" in e or " z" in e.lower() for e in result["errors"])


def test_missing_all_xyz_produces_three_errors():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [
            {
                "type": "drill",
                "parameters": {},  # no x, y, z
                "feedrate": 100,
            }
        ],
    }
    result = validate_operation_plan(plan)
    assert result["ok"] is False
    # At least x, y, z missing — could be 3 separate errors
    assert len(result["errors"]) >= 3


# ---------------------------------------------------------------------------
# D) Drill plan without feedrate
# ---------------------------------------------------------------------------


def test_missing_feedrate_is_error_for_drill():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [
            {
                "type": "drill",
                "parameters": {"x": 0, "y": 0, "z": -5},
                # feedrate intentionally omitted
            }
        ],
    }
    result = validate_operation_plan(plan)
    assert result["ok"] is False
    errors_text = " ".join(result["errors"]).lower()
    assert "feedrate" in errors_text


# ---------------------------------------------------------------------------
# E) Missing spindle_speed is a warning only
# ---------------------------------------------------------------------------


def test_missing_spindle_speed_is_warning_not_error(valid_drill_plan):
    plan = normalize_operation_plan(valid_drill_plan)
    for op in plan["operations"]:
        op.pop("spindle_rpm", None)
        op.pop("spindle_speed", None)
    result = validate_operation_plan(plan)
    # ok can be True (spindle is a warning, not an error)
    assert "warnings" in result
    warnings_text = " ".join(result["warnings"]).lower()
    assert "spindle" in warnings_text


# ---------------------------------------------------------------------------
# F) Empty plan
# ---------------------------------------------------------------------------


def test_empty_plan_not_ok():
    result = validate_operation_plan({})
    assert result["ok"] is False
    assert result["errors"]


def test_none_plan_not_ok():
    result = validate_operation_plan(None)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# G) Milling plan regression — must still pass
# ---------------------------------------------------------------------------


def test_mill_plan_still_validates(valid_mill_plan):
    result = validate_operation_plan(valid_mill_plan)
    assert result["ok"] is True
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# H) normalize_operation_plan
# ---------------------------------------------------------------------------


def test_normalize_maps_tool_id_to_tool_number(valid_drill_plan):
    normalized = normalize_operation_plan(valid_drill_plan)
    for t in normalized["tools"]:
        assert "tool_number" in t
        assert isinstance(t["tool_number"], int)


def test_normalize_maps_diameter_to_diameter_mm(valid_drill_plan):
    normalized = normalize_operation_plan(valid_drill_plan)
    for t in normalized["tools"]:
        assert "diameter_mm" in t


def test_normalize_maps_feedrate_to_feedrate_mmpm(valid_drill_plan):
    normalized = normalize_operation_plan(valid_drill_plan)
    for op in normalized["operations"]:
        assert "feedrate_mmpm" in op


def test_normalize_maps_tool_id_in_operations(valid_drill_plan):
    normalized = normalize_operation_plan(valid_drill_plan)
    for op in normalized["operations"]:
        assert "tool_number" in op


def test_normalize_non_dict_returns_safe_dict():
    result = normalize_operation_plan("not a dict")
    assert isinstance(result, dict)
    assert result["tools"] == []
    assert result["operations"] == []
    assert result["warnings"]
