"""Tests for cnc/tools/job_runs.py — no LLM, no API key required."""

from __future__ import annotations

import json
import os

import pytest

from cnc.tools.job_io import create_job_spec
from cnc.tools.job_runs import (
    create_run_id,
    load_run_report,
    run_job,
    save_run_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _drill_op_plan(material: str | None = "aluminum_6061") -> dict:
    plan: dict = {
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
    if material:
        plan["material"] = material
    return plan


def _valid_drill_job() -> dict:
    return create_job_spec(
        operation_plan=_drill_op_plan(),
        name="Test drill",
        material="aluminum_6061",
        postprocessor="fanuc",
    )


# ---------------------------------------------------------------------------
# create_run_id
# ---------------------------------------------------------------------------


def test_create_run_id_returns_string():
    assert isinstance(create_run_id(), str)


def test_create_run_id_starts_with_run():
    assert create_run_id().startswith("run_")


def test_create_run_id_unique():
    assert create_run_id() != create_run_id()


def test_create_run_id_custom_prefix():
    rid = create_run_id(prefix="job")
    assert rid.startswith("job_")


# ---------------------------------------------------------------------------
# A) run_job — valid drill job
# ---------------------------------------------------------------------------


def test_run_job_valid_drill_ok():
    result = run_job(_valid_drill_job())
    assert result["ok"] is True


def test_run_job_valid_drill_run_report_present():
    result = run_job(_valid_drill_job())
    assert isinstance(result["run_report"], dict)


def test_run_job_valid_drill_status():
    result = run_job(_valid_drill_job())
    assert result["run_report"]["status"] in ("ok", "warning")


def test_run_job_valid_drill_gcode_nonempty():
    result = run_job(_valid_drill_job())
    assert len(result["gcode"]) > 0


def test_run_job_valid_drill_gcode_has_motion():
    result = run_job(_valid_drill_job())
    gcode = result["gcode"]
    assert "G21" in gcode or "G90" in gcode


def test_run_job_run_report_has_run_id():
    result = run_job(_valid_drill_job())
    assert result["run_report"].get("run_id", "").startswith("run_")


def test_run_job_run_report_has_created_at():
    result = run_job(_valid_drill_job())
    assert result["run_report"].get("created_at")


def test_run_job_run_report_schema_version():
    result = run_job(_valid_drill_job())
    assert result["run_report"]["schema_version"] == "0.1"


def test_run_job_run_report_has_required_keys():
    result = run_job(_valid_drill_job())
    rr = result["run_report"]
    for key in (
        "schema_version", "run_id", "created_at", "status",
        "job", "postprocessor", "gcode", "warnings", "errors", "artifacts",
    ):
        assert key in rr, f"Missing key: {key!r}"


def test_run_job_result_has_required_keys():
    result = run_job(_valid_drill_job())
    for key in ("ok", "run_report", "gcode", "warnings", "errors", "artifacts"):
        assert key in result, f"Missing key: {key!r}"


# ---------------------------------------------------------------------------
# B) run_job — invalid job (no operation_plan)
# ---------------------------------------------------------------------------


def test_run_job_invalid_no_op_plan_not_ok():
    job = {"schema_version": "0.1", "postprocessor": "fanuc"}
    result = run_job(job)
    assert result["ok"] is False


def test_run_job_invalid_no_op_plan_status_failed():
    job = {"schema_version": "0.1", "postprocessor": "fanuc"}
    result = run_job(job)
    assert result["run_report"]["status"] == "failed"


def test_run_job_invalid_no_op_plan_errors_nonempty():
    job = {"schema_version": "0.1", "postprocessor": "fanuc"}
    result = run_job(job)
    assert len(result["errors"]) > 0


def test_run_job_invalid_no_op_plan_gcode_empty():
    job = {"schema_version": "0.1", "postprocessor": "fanuc"}
    result = run_job(job)
    assert result["gcode"] == ""


def test_run_job_non_dict_not_ok():
    result = run_job("not a dict")
    assert result["ok"] is False
    assert result["gcode"] == ""


# ---------------------------------------------------------------------------
# C) run_job — ignores stored gcode in job
# ---------------------------------------------------------------------------


def test_run_job_ignores_stored_gcode():
    job = _valid_drill_job()
    job["gcode"] = "... [18 rows x 4 passes] -- abbreviated by LLM"
    result = run_job(job)
    assert "18 rows" not in result["gcode"]


def test_run_job_stored_gcode_result_is_deterministic():
    job = _valid_drill_job()
    job["gcode"] = "G21"
    result = run_job(job)
    assert result["ok"] is True
    assert len(result["gcode"]) > 5  # real G-code, not just "G21"


def test_run_job_stored_gcode_warning_or_ok():
    """Stored gcode triggers a warning (from job_spec_to_gcode) but run still ok."""
    job = _valid_drill_job()
    job["gcode"] = "... [18 rows x 4 passes]"
    result = run_job(job)
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# D) run_job — save G-code and report to tmp_path
# ---------------------------------------------------------------------------


def test_run_job_saves_gcode_file(tmp_path):
    gcode_path = str(tmp_path / "out.nc")
    result = run_job(_valid_drill_job(), save_gcode_path=gcode_path)
    assert os.path.exists(gcode_path)
    assert result["ok"] is True


def test_run_job_saves_report_file(tmp_path):
    report_path = str(tmp_path / "run.json")
    result = run_job(_valid_drill_job(), save_report_path=report_path)
    assert os.path.exists(report_path)


def test_run_job_gcode_file_content(tmp_path):
    gcode_path = str(tmp_path / "out.nc")
    run_job(_valid_drill_job(), save_gcode_path=gcode_path)
    with open(gcode_path, encoding="utf-8") as fh:
        content = fh.read()
    assert len(content) > 0


def test_run_job_report_file_valid_json(tmp_path):
    report_path = str(tmp_path / "run.json")
    run_job(_valid_drill_job(), save_report_path=report_path)
    with open(report_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict)


def test_run_job_artifacts_contain_gcode(tmp_path):
    gcode_path = str(tmp_path / "out.nc")
    result = run_job(_valid_drill_job(), save_gcode_path=gcode_path)
    kinds = [a["kind"] for a in result["artifacts"]]
    assert "gcode" in kinds


def test_run_job_artifacts_contain_run_report(tmp_path):
    report_path = str(tmp_path / "run.json")
    result = run_job(_valid_drill_job(), save_report_path=report_path)
    kinds = [a["kind"] for a in result["artifacts"]]
    assert "run_report" in kinds


def test_run_job_artifacts_both_paths(tmp_path):
    gcode_path = str(tmp_path / "out.nc")
    report_path = str(tmp_path / "run.json")
    result = run_job(
        _valid_drill_job(),
        save_gcode_path=gcode_path,
        save_report_path=report_path,
    )
    kinds = [a["kind"] for a in result["artifacts"]]
    assert "gcode" in kinds
    assert "run_report" in kinds


def test_run_job_gcode_artifact_has_preview(tmp_path):
    gcode_path = str(tmp_path / "out.nc")
    result = run_job(_valid_drill_job(), save_gcode_path=gcode_path)
    gcode_artifacts = [a for a in result["artifacts"] if a["kind"] == "gcode"]
    assert len(gcode_artifacts) == 1
    assert gcode_artifacts[0]["content_preview"] is not None


# ---------------------------------------------------------------------------
# E) save_run_report / load_run_report — roundtrip
# ---------------------------------------------------------------------------


def test_save_run_report_ok(tmp_path):
    job = _valid_drill_job()
    result = run_job(job)
    rr = result["run_report"]
    save_result = save_run_report(rr, str(tmp_path / "report.json"))
    assert save_result["ok"] is True


def test_load_run_report_ok(tmp_path):
    job = _valid_drill_job()
    result = run_job(job)
    path = str(tmp_path / "report.json")
    save_run_report(result["run_report"], path)
    load_result = load_run_report(path)
    assert load_result["ok"] is True


def test_save_load_run_id_preserved(tmp_path):
    result = run_job(_valid_drill_job())
    run_id = result["run_report"]["run_id"]
    path = str(tmp_path / "report.json")
    save_run_report(result["run_report"], path)
    loaded = load_run_report(path)
    assert loaded["run_report"]["run_id"] == run_id


def test_save_load_status_preserved(tmp_path):
    result = run_job(_valid_drill_job())
    status = result["run_report"]["status"]
    path = str(tmp_path / "report.json")
    save_run_report(result["run_report"], path)
    loaded = load_run_report(path)
    assert loaded["run_report"]["status"] == status


def test_save_load_schema_version_preserved(tmp_path):
    result = run_job(_valid_drill_job())
    path = str(tmp_path / "report.json")
    save_run_report(result["run_report"], path)
    loaded = load_run_report(path)
    assert loaded["run_report"]["schema_version"] == "0.1"


# ---------------------------------------------------------------------------
# F) load_run_report — file not found
# ---------------------------------------------------------------------------


def test_load_run_report_missing_not_ok():
    result = load_run_report("/nonexistent/path/that/does_not_exist.json")
    assert result["ok"] is False


def test_load_run_report_missing_has_error():
    result = load_run_report("/nonexistent/path/that/does_not_exist.json")
    assert len(result["errors"]) > 0


def test_load_run_report_missing_run_report_is_none():
    result = load_run_report("/nonexistent/path/that/does_not_exist.json")
    assert result["run_report"] is None


# ---------------------------------------------------------------------------
# G) load_run_report — invalid JSON
# ---------------------------------------------------------------------------


def test_load_run_report_invalid_json_not_ok(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ not valid json }")
    result = load_run_report(path)
    assert result["ok"] is False


def test_load_run_report_invalid_json_has_error(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("not json")
    result = load_run_report(path)
    assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# H) save_run_report — non-dict input
# ---------------------------------------------------------------------------


def test_save_run_report_non_dict_not_ok(tmp_path):
    result = save_run_report("not a dict", str(tmp_path / "x.json"))
    assert result["ok"] is False
