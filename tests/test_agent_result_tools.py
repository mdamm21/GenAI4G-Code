"""Tests for cnc/tools/agent_result_tools.py — OperationPlan extraction and normalization."""

import json
import pytest

from cnc.tools.agent_result_tools import (
    is_operation_plan_like,
    extract_operation_plan_from_agent_result,
    normalize_agent_operation_plan,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_DRILL_PLAN = {
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

MINIMAL_MILL_PLAN = {
    "machine_type": "mill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"tool_number": 1, "description": "5mm end mill", "diameter_mm": 5}],
    "operations": [
        {
            "type": "pocket",
            "name": "pocket 1",
            "tool_number": 1,
            "feedrate_mmpm": 150,
            "parameters": {
                "origin_x": 0, "origin_y": 0, "width": 20, "height": 10,
                "target_z": -3.0, "step_down": 1.0, "step_over": 2.0,
            },
        }
    ],
    "assumptions": [],
    "warnings": [],
    "missing_info": [],
}


# ---------------------------------------------------------------------------
# A) is_operation_plan_like
# ---------------------------------------------------------------------------


def test_is_operation_plan_like_with_machine_type():
    assert is_operation_plan_like({"machine_type": "drill"}) is True


def test_is_operation_plan_like_with_operations():
    assert is_operation_plan_like({"operations": []}) is True


def test_is_operation_plan_like_with_missing_info():
    assert is_operation_plan_like({"missing_info": ["depth not specified"]}) is True


def test_is_operation_plan_like_full_plan():
    assert is_operation_plan_like(MINIMAL_DRILL_PLAN) is True


def test_is_operation_plan_like_empty_dict():
    assert is_operation_plan_like({}) is False


def test_is_operation_plan_like_non_dict_string():
    assert is_operation_plan_like("G21 G90 M30") is False


def test_is_operation_plan_like_non_dict_list():
    assert is_operation_plan_like([{"machine_type": "drill"}]) is False


def test_is_operation_plan_like_none():
    assert is_operation_plan_like(None) is False


def test_is_operation_plan_like_unrelated_dict():
    assert is_operation_plan_like({"gcode": "G21", "ok": True}) is False


# ---------------------------------------------------------------------------
# B) extract — direct dict
# ---------------------------------------------------------------------------


def test_extract_direct_operation_plan_dict():
    result = extract_operation_plan_from_agent_result(MINIMAL_DRILL_PLAN)
    assert result is MINIMAL_DRILL_PLAN


def test_extract_direct_dict_returns_dict():
    result = extract_operation_plan_from_agent_result({"machine_type": "drill"})
    assert isinstance(result, dict)
    assert result.get("machine_type") == "drill"


def test_extract_with_only_operations_key():
    result = extract_operation_plan_from_agent_result({"operations": []})
    assert is_operation_plan_like(result)


def test_extract_with_only_missing_info_key():
    result = extract_operation_plan_from_agent_result({"missing_info": ["depth?"]})
    assert is_operation_plan_like(result)


# ---------------------------------------------------------------------------
# C) extract — {"operation_plan": plan}
# ---------------------------------------------------------------------------


def test_extract_from_operation_plan_key():
    wrapped = {"operation_plan": MINIMAL_DRILL_PLAN, "gcode": "", "assumptions": []}
    result = extract_operation_plan_from_agent_result(wrapped)
    assert is_operation_plan_like(result)
    assert result.get("machine_type") == "drill"


def test_extract_from_operation_plan_key_unwraps():
    wrapped = {"operation_plan": {"machine_type": "mill", "operations": []}}
    result = extract_operation_plan_from_agent_result(wrapped)
    assert result.get("machine_type") == "mill"


def test_extract_from_operation_plan_as_json_string():
    plan_str = json.dumps(MINIMAL_DRILL_PLAN)
    wrapped = {"operation_plan": plan_str}
    result = extract_operation_plan_from_agent_result(wrapped)
    assert is_operation_plan_like(result)


# ---------------------------------------------------------------------------
# D) extract — JSON string
# ---------------------------------------------------------------------------


def test_extract_from_plain_json_string():
    plan_str = json.dumps(MINIMAL_DRILL_PLAN)
    result = extract_operation_plan_from_agent_result(plan_str)
    assert is_operation_plan_like(result)
    assert result.get("machine_type") == "drill"


def test_extract_from_json_with_prose_before():
    plan_str = "Here is the plan:\n" + json.dumps(MINIMAL_DRILL_PLAN)
    result = extract_operation_plan_from_agent_result(plan_str)
    assert is_operation_plan_like(result)


def test_extract_from_markdown_fenced_json():
    plan_str = "```json\n" + json.dumps(MINIMAL_DRILL_PLAN) + "\n```"
    result = extract_operation_plan_from_agent_result(plan_str)
    assert is_operation_plan_like(result)


# ---------------------------------------------------------------------------
# E) unstructured output → error dict
# ---------------------------------------------------------------------------


def test_extract_from_plain_prose_returns_error():
    result = extract_operation_plan_from_agent_result("I cannot generate G-code for this.")
    assert result.get("ok") is False
    assert result.get("errors")
    assert "operation_plan" in result
    assert result["operation_plan"] is None


def test_extract_from_empty_dict_returns_error():
    result = extract_operation_plan_from_agent_result({})
    assert result.get("ok") is False


def test_extract_from_none_returns_error():
    result = extract_operation_plan_from_agent_result(None)
    assert result.get("ok") is False
    assert result.get("errors")


def test_extract_from_integer_returns_error():
    result = extract_operation_plan_from_agent_result(42)
    assert result.get("ok") is False


def test_extract_error_has_raw_output_preview():
    result = extract_operation_plan_from_agent_result("just text")
    assert "raw_output_preview" in result


def test_extract_unstructured_error_message():
    result = extract_operation_plan_from_agent_result("just text")
    errors_text = " ".join(result.get("errors", [])).lower()
    assert "unstructured" in errors_text or "operation" in errors_text


# ---------------------------------------------------------------------------
# F) extract — messages list
# ---------------------------------------------------------------------------


def test_extract_from_messages_list():
    messages = [
        {"role": "user", "content": "drill a hole"},
        {"role": "assistant", "content": json.dumps(MINIMAL_DRILL_PLAN)},
    ]
    result = extract_operation_plan_from_agent_result({"messages": messages})
    assert is_operation_plan_like(result)


def test_extract_from_messages_content_blocks():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": json.dumps(MINIMAL_MILL_PLAN)},
            ],
        }
    ]
    result = extract_operation_plan_from_agent_result({"messages": messages})
    assert is_operation_plan_like(result)


# ---------------------------------------------------------------------------
# G) normalize_agent_operation_plan
# ---------------------------------------------------------------------------


def test_normalize_adds_assumptions():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert "assumptions" in result
    assert isinstance(result["assumptions"], list)


def test_normalize_adds_warnings():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert "warnings" in result
    assert isinstance(result["warnings"], list)


def test_normalize_adds_missing_info():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert "missing_info" in result
    assert isinstance(result["missing_info"], list)


def test_normalize_adds_tools():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert "tools" in result
    assert isinstance(result["tools"], list)


def test_normalize_adds_operations():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert "operations" in result
    assert isinstance(result["operations"], list)


def test_normalize_does_not_invent_safe_z():
    plan = {"machine_type": "drill", "units": "mm"}
    result = normalize_agent_operation_plan(plan)
    assert "safe_z" not in result


def test_normalize_does_not_invent_feedrate():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert "feedrate" not in result
    assert "feedrate_mmpm" not in result


def test_normalize_does_not_invent_units():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert "units" not in result


def test_normalize_default_wcs_g54():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    assert result["work_coordinate_system"] == "G54"


def test_normalize_default_wcs_adds_warning():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan)
    warnings_text = " ".join(result["warnings"]).lower()
    assert "work_coordinate_system" in warnings_text or "wcs" in warnings_text or "g54" in warnings_text


def test_normalize_preserves_existing_wcs():
    plan = {"machine_type": "drill", "work_coordinate_system": "G55"}
    result = normalize_agent_operation_plan(plan)
    assert result["work_coordinate_system"] == "G55"
    # No wcs warning when already set
    warnings_text = " ".join(result["warnings"]).lower()
    assert "work_coordinate_system was not provided" not in warnings_text


def test_normalize_fills_machine_type_from_hint():
    plan = {"operations": []}  # no machine_type
    result = normalize_agent_operation_plan(plan, preferred_machine_type="mill")
    assert result["machine_type"] == "mill"


def test_normalize_does_not_override_existing_machine_type():
    plan = {"machine_type": "drill"}
    result = normalize_agent_operation_plan(plan, preferred_machine_type="mill")
    assert result["machine_type"] == "drill"


def test_normalize_does_not_mutate_input():
    plan = {"machine_type": "drill"}
    normalize_agent_operation_plan(plan)
    assert "assumptions" not in plan  # original dict unchanged


def test_normalize_preserves_safe_z_when_present():
    plan = {"machine_type": "drill", "safe_z": 10.0}
    result = normalize_agent_operation_plan(plan)
    assert result["safe_z"] == 10.0


def test_normalize_preserves_existing_warnings():
    plan = {"machine_type": "drill", "warnings": ["existing warning"]}
    result = normalize_agent_operation_plan(plan)
    assert "existing warning" in result["warnings"]


def test_normalize_preserves_existing_missing_info():
    plan = {"machine_type": "drill", "missing_info": ["depth not specified"]}
    result = normalize_agent_operation_plan(plan)
    assert "depth not specified" in result["missing_info"]
