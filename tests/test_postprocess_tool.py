"""Tests for cnc/tools/postprocess_tools.py — full validation + postprocess pipeline."""

import pytest
from cnc.tools.postprocess_tools import postprocess_operations
from cnc.tools.operation_plan_tools import normalize_operation_plan


# ---------------------------------------------------------------------------
# A) Full valid drill plan — happy path
# ---------------------------------------------------------------------------


def test_valid_drill_plan_ok(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="fanuc")
    assert result["ok"] is True


def test_valid_drill_plan_gcode_not_empty(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="fanuc")
    assert result["gcode"]


def test_valid_drill_plan_gcode_has_m30(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="fanuc")
    assert "M30" in result["gcode"]


def test_valid_drill_plan_no_errors(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="fanuc")
    assert result["errors"] == [] or result["errors"] is None or not result["errors"]


def test_valid_drill_result_has_all_keys(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="fanuc")
    for key in ("ok", "gcode", "errors", "warnings", "postprocessor", "validation"):
        assert key in result, f"Missing key: {key}"


def test_valid_drill_plan_postprocessor_name(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="fanuc")
    assert result["postprocessor"] == "fanuc"


def test_valid_drill_plan_validation_ok(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="fanuc")
    assert result["validation"]["ok"] is True


# ---------------------------------------------------------------------------
# B) Invalid plan — no operations
# ---------------------------------------------------------------------------


def test_empty_operations_not_ok():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [],
    }
    result = postprocess_operations(plan, postprocessor="fanuc")
    assert result["ok"] is False


def test_empty_operations_gcode_is_none_or_empty():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [],
    }
    result = postprocess_operations(plan, postprocessor="fanuc")
    assert not result.get("gcode")


def test_empty_operations_has_errors():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [],
    }
    result = postprocess_operations(plan, postprocessor="fanuc")
    assert result["errors"]


# ---------------------------------------------------------------------------
# C) Unknown postprocessor
# ---------------------------------------------------------------------------


def test_unknown_postprocessor_not_ok(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="unknown")
    assert result["ok"] is False


def test_unknown_postprocessor_error_message(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="unknown")
    errors_text = " ".join(result.get("errors", [])).lower()
    assert "unknown" in errors_text or "not supported" in errors_text


def test_unknown_postprocessor_no_gcode(normalized_drill_plan):
    result = postprocess_operations(normalized_drill_plan, postprocessor="unknown")
    assert not result.get("gcode")


# ---------------------------------------------------------------------------
# D) All supported postprocessors produce G-code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pp", ["fanuc", "grbl", "marlin", "linuxcnc"])
def test_all_postprocessors_run(normalized_drill_plan, pp):
    """Each postprocessor must run without crashing on a valid drill plan."""
    result = postprocess_operations(normalized_drill_plan, postprocessor=pp)
    # May have warnings (e.g. spindle checks differ per dialect) but must not crash
    assert isinstance(result, dict)
    assert "gcode" in result
    assert "ok" in result


# ---------------------------------------------------------------------------
# E) Drill-specific validation: missing feedrate blocks G-code
# ---------------------------------------------------------------------------


def test_drill_no_feedrate_blocked():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5,
        "operations": [
            {
                "type": "drill",
                "parameters": {"x": 0, "y": 0, "z": -5},
                # feedrate omitted
            }
        ],
    }
    result = postprocess_operations(plan, postprocessor="fanuc")
    assert result["ok"] is False
    assert not result.get("gcode")


def test_drill_missing_z_blocked():
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
    result = postprocess_operations(plan, postprocessor="fanuc")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# F) Milling regression
# ---------------------------------------------------------------------------


def test_milling_plan_still_works(valid_mill_plan):
    result = postprocess_operations(valid_mill_plan, postprocessor="fanuc")
    assert result["ok"] is True
    assert result["gcode"]
    assert "M30" in result["gcode"]
