"""Tests for cnc/tools/gcode_pipeline.py — deterministic G-code regeneration.

All tests run without an LLM or API key.
"""

from __future__ import annotations

import pytest

from cnc.tools.gcode_pipeline import regenerate_gcode_from_operation_plan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_drill_plan() -> dict:
    return {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5,
        "tools": [
            {
                "id": "T1",
                "name": "5mm drill",
                "diameter": 5,
                "units": "mm",
                "spindle_speed": 1200,
                "feedrate": 100,
            }
        ],
        "operations": [
            {
                "type": "drill",
                "description": "Drill one hole at X0 Y0 to Z-5",
                "tool_id": "T1",
                "parameters": {"x": 0, "y": 0, "z": -5},
                "feedrate": 100,
                "spindle_speed": 1200,
            }
        ],
        "assumptions": [],
        "warnings": [],
    }


@pytest.fixture
def another_valid_drill_plan() -> dict:
    return {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5,
        "tools": [
            {
                "id": "T1",
                "name": "8mm drill",
                "diameter": 8,
                "units": "mm",
                "spindle_speed": 800,
                "feedrate": 80,
            }
        ],
        "operations": [
            {
                "type": "drill",
                "description": "Drill one hole at X10 Y10 to Z-8",
                "tool_id": "T1",
                "parameters": {"x": 10, "y": 10, "z": -8},
                "feedrate": 80,
                "spindle_speed": 800,
            }
        ],
        "assumptions": [],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# A) Agent G-code is discarded and replaced with deterministic output
# ---------------------------------------------------------------------------

def test_agent_gcode_discarded(valid_drill_plan):
    """Abbreviated agent gcode must be replaced by deterministic output."""
    result = regenerate_gcode_from_operation_plan({
        "ok": True,
        "machine_type": "drill",
        "operation_plan": valid_drill_plan,
        "gcode": "G21\n... [18 rows x 4 passes]\nM30",
        "warnings": [],
        "errors": [],
    })

    gcode = result["gcode"]
    assert "[18 rows" not in gcode, "Abbreviated placeholder must not appear in final G-code"
    assert gcode.strip(), "G-code must not be empty"
    # Must contain a units declaration
    assert "G21" in gcode or "G20" in gcode, "G-code must declare units"
    # Must contain a program end
    assert "M30" in gcode or "M2" in gcode, "G-code must have program end"


def test_agent_gcode_discard_warning(valid_drill_plan):
    """A warning must be added when agent gcode was discarded."""
    result = regenerate_gcode_from_operation_plan({
        "operation_plan": valid_drill_plan,
        "gcode": "G21\n... [18 rows x 4 passes]\nM30",
    })
    warnings_text = " ".join(result.get("warnings", []))
    assert "discarded" in warnings_text.lower() or "regenerated" in warnings_text.lower()


def test_result_ok_when_gcode_generated(valid_drill_plan):
    """ok must be True when G-code is successfully generated."""
    result = regenerate_gcode_from_operation_plan({
        "operation_plan": valid_drill_plan,
        "gcode": "abbreviated",
    })
    assert result.get("ok") is True
    assert result["gcode"]


# ---------------------------------------------------------------------------
# B) operation_plan as list with one item
# ---------------------------------------------------------------------------

def test_plan_list_single_item(valid_drill_plan):
    """Single-item list must be unwrapped to the plan dict."""
    result = regenerate_gcode_from_operation_plan({
        "operation_plan": [valid_drill_plan],
        "gcode": "abbreviated",
    })
    assert isinstance(result["operation_plan"], dict)
    assert result["gcode"].strip(), "G-code must be generated"
    warnings_text = " ".join(result.get("warnings", []))
    assert "list" in warnings_text.lower(), "Warning must mention list format"


def test_plan_list_single_item_gcode_correct(valid_drill_plan):
    """G-code from unwrapped single-item list must be deterministic."""
    result = regenerate_gcode_from_operation_plan({
        "operation_plan": [valid_drill_plan],
    })
    assert "abbreviated" not in result["gcode"]
    assert "G21" in result["gcode"] or "G20" in result["gcode"]


# ---------------------------------------------------------------------------
# C) operation_plan as list with multiple items
# ---------------------------------------------------------------------------

def test_plan_list_multiple_allow_first(valid_drill_plan, another_valid_drill_plan):
    """With allow_plan_list_first_item=True, use first plan and warn."""
    result = regenerate_gcode_from_operation_plan(
        {"operation_plan": [valid_drill_plan, another_valid_drill_plan]},
        allow_plan_list_first_item=True,
    )
    assert isinstance(result["operation_plan"], dict)
    assert result["gcode"].strip()
    warnings_text = " ".join(result.get("warnings", []))
    assert "multiple" in warnings_text.lower() or "first" in warnings_text.lower()


def test_plan_list_multiple_disallow_first(valid_drill_plan, another_valid_drill_plan):
    """With allow_plan_list_first_item=False, return error instead of gcode."""
    result = regenerate_gcode_from_operation_plan(
        {"operation_plan": [valid_drill_plan, another_valid_drill_plan]},
        allow_plan_list_first_item=False,
    )
    assert result["gcode"] == ""
    assert result.get("ok") is False
    errors_text = " ".join(result.get("errors", []))
    assert "multiple" in errors_text.lower() or "allow_plan_list_first_item" in errors_text


def test_plan_list_empty():
    """Empty list must return an error."""
    result = regenerate_gcode_from_operation_plan({"operation_plan": []})
    assert result["gcode"] == ""
    assert result.get("ok") is False
    assert result.get("errors")


# ---------------------------------------------------------------------------
# D) Invalid OperationPlan — validation errors → gcode stays empty
# ---------------------------------------------------------------------------

def test_invalid_plan_gcode_empty():
    """Invalid plan must result in empty gcode — old agent gcode must not be kept."""
    invalid_plan = {
        "machine_type": "drill",
        "units": "mm",
        "operations": [],   # no safe_z, no operations
    }
    result = regenerate_gcode_from_operation_plan({
        "operation_plan": invalid_plan,
        "gcode": "G21\nG90\nM30",
    })
    assert result["gcode"] == "", "Agent gcode must not survive a failed validation"
    assert result.get("ok") is False


def test_invalid_plan_has_validation_errors():
    """Validation errors must be present in the result."""
    invalid_plan = {"machine_type": "drill", "units": "mm", "operations": []}
    result = regenerate_gcode_from_operation_plan({"operation_plan": invalid_plan})
    val = result.get("validation", {})
    assert val.get("errors"), "validation.errors must be non-empty"


# ---------------------------------------------------------------------------
# E) No operation_plan — no fake G-code generated
# ---------------------------------------------------------------------------

def test_no_operation_plan_no_exception():
    """Missing operation_plan must not raise and must not invent G-code."""
    result = regenerate_gcode_from_operation_plan({"gcode": "G21\nG90\nM30"})
    # No exception
    assert isinstance(result, dict)


def test_no_operation_plan_warning():
    """A warning must be added when operation_plan is absent."""
    result = regenerate_gcode_from_operation_plan({"gcode": "G21\nG90\nM30"})
    warnings_text = " ".join(result.get("warnings", []))
    assert "operation_plan" in warnings_text.lower() or "skipped" in warnings_text.lower()


def test_no_operation_plan_gcode_unchanged():
    """Without an operation_plan, existing gcode must be left as-is (no pipeline)."""
    original_gcode = "G21\nG90\nM30"
    result = regenerate_gcode_from_operation_plan({"gcode": original_gcode})
    assert result.get("gcode") == original_gcode


# ---------------------------------------------------------------------------
# F) Postprocessor selection from result is respected
# ---------------------------------------------------------------------------

def test_postprocessor_from_result_key(valid_drill_plan):
    """result["postprocessor"] must override the default."""
    result = regenerate_gcode_from_operation_plan(
        {"postprocessor": "grbl", "operation_plan": valid_drill_plan},
        default_postprocessor="fanuc",
    )
    assert result.get("postprocessor") == "grbl"
    assert result["gcode"].strip(), "G-code must be generated for grbl"


def test_grbl_gcode_no_percent(valid_drill_plan):
    """GRBL output must not contain Fanuc-style % delimiters."""
    result = regenerate_gcode_from_operation_plan(
        {"postprocessor": "grbl", "operation_plan": valid_drill_plan},
        default_postprocessor="fanuc",
    )
    # Fanuc uses % block delimiters; GRBL does not
    assert "%" not in result["gcode"], "GRBL output must not contain % delimiters"


def test_default_postprocessor_used_when_none_specified(valid_drill_plan):
    """default_postprocessor must be used when no postprocessor is set."""
    result = regenerate_gcode_from_operation_plan(
        {"operation_plan": valid_drill_plan},
        default_postprocessor="linuxcnc",
    )
    assert result.get("postprocessor") == "linuxcnc"
    assert result["gcode"].strip()


# ---------------------------------------------------------------------------
# G) Non-dict result input
# ---------------------------------------------------------------------------

def test_non_dict_result_returns_error():
    """Passing a non-dict result must return a structured error dict."""
    result = regenerate_gcode_from_operation_plan("not a dict")
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("errors")


def test_non_dict_operation_plan():
    """A non-dict operation_plan (e.g. a string) must return error, not gcode."""
    result = regenerate_gcode_from_operation_plan({"operation_plan": "some string"})
    assert result["gcode"] == ""
    assert result.get("ok") is False


# ---------------------------------------------------------------------------
# H) postprocessor from operation_plan is respected
# ---------------------------------------------------------------------------

def test_postprocessor_from_operation_plan(valid_drill_plan):
    """operation_plan["postprocessor"] must be used when result has none."""
    plan_with_pp = dict(valid_drill_plan, postprocessor="grbl")
    result = regenerate_gcode_from_operation_plan(
        {"operation_plan": plan_with_pp},
        default_postprocessor="fanuc",
    )
    assert result.get("postprocessor") == "grbl"


# ---------------------------------------------------------------------------
# I) Warnings and errors merge correctly
# ---------------------------------------------------------------------------

def test_existing_warnings_preserved(valid_drill_plan):
    """Warnings present in the input result must be preserved."""
    result = regenerate_gcode_from_operation_plan({
        "operation_plan": valid_drill_plan,
        "warnings": ["pre-existing warning"],
    })
    assert "pre-existing warning" in result.get("warnings", [])


def test_no_unexpected_exceptions(valid_drill_plan):
    """Pipeline must never raise — always returns a dict."""
    for bad_input in [None, 42, [], "string", {"operation_plan": None}]:
        out = regenerate_gcode_from_operation_plan(bad_input)
        assert isinstance(out, dict), f"Expected dict for input {bad_input!r}"
