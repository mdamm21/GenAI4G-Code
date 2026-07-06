"""Tests for cnc/cli_interaction.py — interactive CLI warning resolution."""

import pytest
from cnc.cli_interaction import resolve_issues_interactively


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_input(answers: list[str]):
    """Create a fake input function from a list of answers."""
    it = iter(answers)
    def fn(prompt: str) -> str:
        return next(it)
    return fn


def _capture_output():
    """Create an output function that captures all output."""
    lines: list[str] = []
    def fn(*args, **kwargs):
        lines.append(" ".join(str(a) for a in args))
    return fn, lines


def _make_result_with_unknown_tool() -> dict:
    return {
        "warnings": [
            "Operation 0 references tool_id='1' which is not in the built-in tool library.",
            "Operation 1 references tool_id='1' which is not in the built-in tool library.",
        ],
        "errors": [],
        "validation": {"ok": True, "warnings": [], "errors": []},
        "operation_plan": {
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
                {"tool_number": 1, "type": "drill", "feedrate_mmpm": 80,
                 "spindle_rpm": 1200, "parameters": {"x": 10, "y": 0, "z": -18}},
            ],
        },
    }


# ---------------------------------------------------------------------------
# A) UNKNOWN_TOOL_ID — choice 3 = transient custom tool
# ---------------------------------------------------------------------------


def test_unknown_tool_transient_custom():
    result = _make_result_with_unknown_tool()
    output_fn, lines = _capture_output()

    # Choice "3" = USE_TRANSIENT_CUSTOM_TOOL, then "1" = continue to G-code
    input_fn = _fake_input(["3", "1"])

    result = resolve_issues_interactively(
        result, prompt="Drill holes",
        input_fn=input_fn, output_fn=output_fn,
    )

    op = result["operation_plan"]
    assert op["tools"][0]["id"] == "custom_T1"
    assert op["tools"][0]["source"] == "operation_plan"


# ---------------------------------------------------------------------------
# B) Invalid input then valid
# ---------------------------------------------------------------------------


def test_invalid_then_valid_input():
    result = _make_result_with_unknown_tool()
    output_fn, lines = _capture_output()

    # "x" and "99" are invalid, then "1" = IGNORE_ONCE, then "1" = continue
    input_fn = _fake_input(["x", "99", "1", "1"])

    result = resolve_issues_interactively(
        result, prompt="Drill holes",
        input_fn=input_fn, output_fn=output_fn,
    )

    # Should have eventually processed successfully
    assert "resolution_log" in result
    # Check that invalid input messages were printed
    output_text = " ".join(lines)
    assert "Invalid" in output_text


# ---------------------------------------------------------------------------
# C) Abort
# ---------------------------------------------------------------------------


def test_abort():
    result = _make_result_with_unknown_tool()
    output_fn, lines = _capture_output()

    # Choice "5" = Abort
    input_fn = _fake_input(["5"])

    result = resolve_issues_interactively(
        result, prompt="Drill holes",
        input_fn=input_fn, output_fn=output_fn,
    )

    assert result.get("aborted") is True


# ---------------------------------------------------------------------------
# D) No actionable issues
# ---------------------------------------------------------------------------


def test_no_actionable_issues():
    result = {
        "warnings": [],
        "errors": [],
        "operation_plan": {
            "machine_type": "drill", "units": "mm", "safe_z": 5.0,
            "tools": [], "operations": [],
        },
    }
    output_fn, lines = _capture_output()
    input_fn = _fake_input([])

    result = resolve_issues_interactively(
        result, input_fn=input_fn, output_fn=output_fn,
    )

    output_text = " ".join(lines)
    assert "No actionable issues" in output_text or "no actionable" in output_text.lower()


# ---------------------------------------------------------------------------
# E) Ignore once
# ---------------------------------------------------------------------------


def test_ignore_once():
    result = _make_result_with_unknown_tool()
    output_fn, lines = _capture_output()

    # Choice "1" = IGNORE_ONCE, then "1" = continue
    input_fn = _fake_input(["1", "1"])

    result = resolve_issues_interactively(
        result, prompt="Drill holes",
        input_fn=input_fn, output_fn=output_fn,
    )

    assert "resolution_log" in result
    log = result["resolution_log"]
    assert any(e["action"] == "IGNORE_ONCE" for e in log)
