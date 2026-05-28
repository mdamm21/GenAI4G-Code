"""Tests for cnc/tools/job_io.py — no LLM, no API key required."""

from __future__ import annotations

import json
import os

import pytest

from cnc.tools.job_io import (
    create_job_spec,
    job_spec_to_gcode,
    load_job_spec,
    save_job_spec,
    validate_job_spec,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _drill_operation_plan(material: str | None = None) -> dict:
    plan = {
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
        "assumptions": ["Tool T1 assumed."],
        "warnings": [],
        "missing_info": [],
    }
    if material:
        plan["material"] = material
    return plan


def _pocket_operation_plan(material: str | None = None) -> dict:
    plan = {
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
        "missing_info": [],
    }
    if material:
        plan["material"] = material
    return plan


def _valid_drill_job(material: str | None = "aluminum_6061") -> dict:
    return create_job_spec(
        operation_plan=_drill_operation_plan(material=material),
        name="Test drill job",
        machine_profile="generic_drill_mm",
        material=material,
        postprocessor="fanuc",
    )


# ---------------------------------------------------------------------------
# A) create_job_spec
# ---------------------------------------------------------------------------


def test_create_job_spec_returns_dict():
    job = create_job_spec(_drill_operation_plan())
    assert isinstance(job, dict)


def test_create_job_spec_schema_version():
    job = create_job_spec(_drill_operation_plan())
    assert job["schema_version"] == "0.1"


def test_create_job_spec_operation_plan_present():
    job = create_job_spec(_drill_operation_plan())
    assert "operation_plan" in job
    assert isinstance(job["operation_plan"], dict)


def test_create_job_spec_no_gcode_field():
    job = create_job_spec(_drill_operation_plan())
    assert "gcode" not in job
    assert "gcode" not in job.get("operation_plan", {})


def test_create_job_spec_gcode_stripped_from_op():
    """If operation_plan has a gcode field it must be stripped."""
    op = _drill_operation_plan()
    op["gcode"] = "G21\nM30"
    job = create_job_spec(op)
    assert "gcode" not in job.get("operation_plan", {})


def test_create_job_spec_gcode_stripped_warning():
    op = _drill_operation_plan()
    op["gcode"] = "G21\nM30"
    job = create_job_spec(op)
    warnings_text = " ".join(job.get("warnings", []))
    assert "gcode" in warnings_text.lower() or "stripped" in warnings_text.lower()


def test_create_job_spec_machine_type_from_op():
    job = create_job_spec(_drill_operation_plan())
    assert job["machine_type"] == "drill"


def test_create_job_spec_material_explicit_wins():
    op = _drill_operation_plan(material="mild_steel")
    job = create_job_spec(op, material="aluminum_6061")
    assert job["material"] == "aluminum_6061"


def test_create_job_spec_material_from_op_fallback():
    op = _drill_operation_plan(material="mild_steel")
    job = create_job_spec(op)
    assert job["material"] == "mild_steel"


def test_create_job_spec_tool_ids_from_op():
    job = create_job_spec(_drill_operation_plan())
    assert "T1" in job["tool_ids"]


def test_create_job_spec_tool_ids_explicit_wins():
    job = create_job_spec(_drill_operation_plan(), tool_ids=["my_tool"])
    assert job["tool_ids"] == ["my_tool"]


def test_create_job_spec_name_set():
    job = create_job_spec(_drill_operation_plan(), name="My Job")
    assert job["name"] == "My Job"


def test_create_job_spec_postprocessor_default():
    job = create_job_spec(_drill_operation_plan())
    assert job["postprocessor"] == "fanuc"


def test_create_job_spec_postprocessor_custom():
    job = create_job_spec(_drill_operation_plan(), postprocessor="grbl")
    assert job["postprocessor"] == "grbl"


def test_create_job_spec_assumptions_inherited():
    job = create_job_spec(_drill_operation_plan())
    assert "Tool T1 assumed." in job["assumptions"]


def test_create_job_spec_job_id_generated():
    job = create_job_spec(_drill_operation_plan())
    assert job.get("job_id") is not None
    assert len(job["job_id"]) > 0


def test_create_job_spec_no_mutation_of_input():
    op = _drill_operation_plan()
    original_ops = len(op["operations"])
    create_job_spec(op)
    assert len(op["operations"]) == original_ops


# ---------------------------------------------------------------------------
# B) validate_job_spec — valid drill job
# ---------------------------------------------------------------------------


def test_validate_job_spec_valid_drill_ok():
    result = validate_job_spec(_valid_drill_job())
    assert result["ok"] is True


def test_validate_job_spec_valid_drill_no_errors():
    result = validate_job_spec(_valid_drill_job())
    assert result["errors"] == []


def test_validate_job_spec_has_operation_plan_validation():
    result = validate_job_spec(_valid_drill_job())
    assert result["operation_plan_validation"] is not None


def test_validate_job_spec_has_guardrails():
    result = validate_job_spec(_valid_drill_job())
    assert result["guardrails"] is not None


def test_validate_job_spec_returns_job_when_ok():
    result = validate_job_spec(_valid_drill_job())
    assert isinstance(result.get("job"), dict)


def test_validate_job_spec_has_required_keys():
    result = validate_job_spec(_valid_drill_job())
    for key in ("ok", "errors", "warnings", "job", "operation_plan_validation", "guardrails"):
        assert key in result, f"Missing key: {key!r}"


# ---------------------------------------------------------------------------
# C) validate_job_spec — missing operation_plan
# ---------------------------------------------------------------------------


def test_validate_job_spec_missing_op_plan_not_ok():
    job = {
        "schema_version": "0.1",
        "machine_type": "drill",
        "postprocessor": "fanuc",
    }
    result = validate_job_spec(job)
    assert result["ok"] is False


def test_validate_job_spec_missing_op_plan_error_mentions_operation_plan():
    job = {
        "schema_version": "0.1",
        "machine_type": "drill",
        "postprocessor": "fanuc",
    }
    result = validate_job_spec(job)
    errors_text = " ".join(result["errors"]).lower()
    assert "operation_plan" in errors_text


# ---------------------------------------------------------------------------
# D) validate_job_spec — machine_type mismatch
# ---------------------------------------------------------------------------


def test_validate_job_spec_machine_type_mismatch_not_ok():
    job = {
        "schema_version": "0.1",
        "machine_type": "mill",
        "postprocessor": "fanuc",
        "operation_plan": _drill_operation_plan(),  # machine_type = "drill"
    }
    result = validate_job_spec(job)
    assert result["ok"] is False


def test_validate_job_spec_machine_type_mismatch_error_text():
    job = {
        "schema_version": "0.1",
        "machine_type": "mill",
        "postprocessor": "fanuc",
        "operation_plan": _drill_operation_plan(),
    }
    result = validate_job_spec(job)
    errors_text = " ".join(result["errors"]).lower()
    assert "mismatch" in errors_text or "machine_type" in errors_text


# ---------------------------------------------------------------------------
# E) job_spec_to_gcode — valid drill job
# ---------------------------------------------------------------------------


def test_job_spec_to_gcode_valid_drill_ok():
    result = job_spec_to_gcode(_valid_drill_job())
    assert result["ok"] is True


def test_job_spec_to_gcode_valid_drill_gcode_nonempty():
    result = job_spec_to_gcode(_valid_drill_job())
    assert len(result["gcode"]) > 0


def test_job_spec_to_gcode_fanuc_contains_m30():
    result = job_spec_to_gcode(_valid_drill_job())
    assert "M30" in result["gcode"] or "M2" in result["gcode"]


def test_job_spec_to_gcode_has_required_keys():
    result = job_spec_to_gcode(_valid_drill_job())
    for key in ("ok", "gcode", "job", "validation", "warnings", "errors", "postprocessor", "safety_report"):
        assert key in result, f"Missing key: {key!r}"


def test_job_spec_to_gcode_pocket_ok():
    job = create_job_spec(
        _pocket_operation_plan(material="aluminum_6061"),
        postprocessor="fanuc",
        material="aluminum_6061",
    )
    result = job_spec_to_gcode(job)
    assert result["ok"] is True
    assert len(result["gcode"]) > 0


# ---------------------------------------------------------------------------
# F) job_spec_to_gcode — ignores stored gcode field
# ---------------------------------------------------------------------------


def test_job_spec_to_gcode_ignores_stored_gcode():
    job = _valid_drill_job()
    job["gcode"] = "... [18 rows x 4 passes] -- abbreviated by LLM"
    result = job_spec_to_gcode(job)
    # The fake abbreviated gcode must not appear in the result.
    assert "18 rows" not in result["gcode"]


def test_job_spec_to_gcode_stored_gcode_warning():
    job = _valid_drill_job()
    job["gcode"] = "G21\nM30"
    result = job_spec_to_gcode(job)
    warnings_text = " ".join(result.get("warnings", [])).lower()
    assert "ignored" in warnings_text or "stored" in warnings_text or "gcode" in warnings_text


def test_job_spec_to_gcode_still_ok_with_stored_gcode():
    job = _valid_drill_job()
    job["gcode"] = "G21\nM30"
    result = job_spec_to_gcode(job)
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# G) save_job_spec / load_job_spec roundtrip
# ---------------------------------------------------------------------------


def test_save_job_spec_ok(tmp_path):
    job = _valid_drill_job()
    path = str(tmp_path / "test_job.json")
    result = save_job_spec(job, path)
    assert result["ok"] is True
    assert os.path.exists(path)


def test_load_job_spec_ok(tmp_path):
    job = _valid_drill_job()
    path = str(tmp_path / "test_job.json")
    save_job_spec(job, path)
    load_result = load_job_spec(path)
    assert load_result["ok"] is True


def test_save_load_roundtrip_schema_version(tmp_path):
    job = _valid_drill_job()
    path = str(tmp_path / "roundtrip.json")
    save_job_spec(job, path)
    loaded = load_job_spec(path)
    assert loaded["job"]["schema_version"] == "0.1"


def test_save_load_roundtrip_operation_plan(tmp_path):
    job = _valid_drill_job()
    path = str(tmp_path / "roundtrip.json")
    save_job_spec(job, path)
    loaded = load_job_spec(path)
    assert "operation_plan" in loaded["job"]
    assert loaded["job"]["operation_plan"]["machine_type"] == "drill"


def test_save_load_roundtrip_gcode_from_loaded_job(tmp_path):
    """A saved-and-reloaded job can still generate G-code."""
    job = _valid_drill_job()
    path = str(tmp_path / "roundtrip.json")
    save_job_spec(job, path)
    loaded = load_job_spec(path)
    gcode_result = job_spec_to_gcode(loaded["job"])
    assert gcode_result["ok"] is True
    assert len(gcode_result["gcode"]) > 0


def test_save_job_spec_produces_valid_json(tmp_path):
    job = _valid_drill_job()
    path = str(tmp_path / "valid_json.json")
    save_job_spec(job, path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# H) load_job_spec — file not found
# ---------------------------------------------------------------------------


def test_load_job_spec_missing_file_not_ok():
    result = load_job_spec("/nonexistent/path/that/does/not/exist.json")
    assert result["ok"] is False


def test_load_job_spec_missing_file_has_error():
    result = load_job_spec("/nonexistent/path/that/does/not/exist.json")
    assert len(result["errors"]) > 0


def test_load_job_spec_missing_file_job_is_none():
    result = load_job_spec("/nonexistent/path/that/does/not/exist.json")
    assert result["job"] is None


# ---------------------------------------------------------------------------
# I) load_job_spec — invalid JSON
# ---------------------------------------------------------------------------


def test_load_job_spec_invalid_json_not_ok(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json }")
    result = load_job_spec(path)
    assert result["ok"] is False


def test_load_job_spec_invalid_json_has_error(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json }")
    result = load_job_spec(path)
    assert len(result["errors"]) > 0


def test_load_job_spec_invalid_json_job_is_none(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("not json at all")
    result = load_job_spec(path)
    assert result["job"] is None


# ---------------------------------------------------------------------------
# J) non-dict input guards
# ---------------------------------------------------------------------------


def test_validate_job_spec_non_dict_not_ok():
    result = validate_job_spec("not a dict")
    assert result["ok"] is False
    assert result["errors"]


def test_job_spec_to_gcode_non_dict_not_ok():
    result = job_spec_to_gcode("not a dict")
    assert result["ok"] is False
    assert result["gcode"] == ""


def test_save_job_spec_non_dict_not_ok(tmp_path):
    path = str(tmp_path / "bad.json")
    result = save_job_spec("not a dict", path)
    assert result["ok"] is False
