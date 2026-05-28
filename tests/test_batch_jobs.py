"""Tests for cnc/tools/batch_jobs.py — no LLM, no API key required."""

from __future__ import annotations

import json
import os

import pytest

from cnc.tools.batch_jobs import (
    _safe_filename,
    create_batch_id,
    load_batch_report,
    run_job_batch,
    run_job_batch_from_directory,
    run_job_batch_from_paths,
    save_batch_report,
)
from cnc.tools.job_io import create_job_spec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _drill_op_plan() -> dict:
    return {
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


def _pocket_op_plan() -> dict:
    return {
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


def _valid_drill_job(name: str = "Drill job") -> dict:
    return create_job_spec(
        _drill_op_plan(),
        name=name,
        material="aluminum_6061",
        postprocessor="fanuc",
    )


def _valid_pocket_job(name: str = "Pocket job") -> dict:
    return create_job_spec(
        _pocket_op_plan(),
        name=name,
        material="aluminum_6061",
        postprocessor="fanuc",
    )


def _invalid_job() -> dict:
    return {"schema_version": "0.1", "postprocessor": "fanuc"}  # missing operation_plan


# ---------------------------------------------------------------------------
# create_batch_id
# ---------------------------------------------------------------------------


def test_create_batch_id_returns_string():
    assert isinstance(create_batch_id(), str)


def test_create_batch_id_starts_with_batch():
    assert create_batch_id().startswith("batch_")


def test_create_batch_id_unique():
    assert create_batch_id() != create_batch_id()


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------


def test_safe_filename_lowercase():
    assert _safe_filename("My Job", "fallback") == "my_job"


def test_safe_filename_spaces_to_underscores():
    assert _safe_filename("drill hole", "x") == "drill_hole"


def test_safe_filename_strips_special_chars():
    result = _safe_filename("job@#2!", "x")
    assert "@" not in result and "#" not in result


def test_safe_filename_none_returns_fallback():
    assert _safe_filename(None, "fallback") == "fallback"


def test_safe_filename_empty_returns_fallback():
    assert _safe_filename("", "fallback") == "fallback"


def test_safe_filename_truncates_to_80():
    long = "a" * 200
    assert len(_safe_filename(long, "x")) <= 80


# ---------------------------------------------------------------------------
# A) run_job_batch — two valid jobs
# ---------------------------------------------------------------------------


def test_run_job_batch_two_valid_total():
    jobs = [_valid_drill_job(), _valid_pocket_job()]
    result = run_job_batch(jobs)
    assert result["batch_report"]["total_jobs"] == 2


def test_run_job_batch_two_valid_failed_zero():
    jobs = [_valid_drill_job(), _valid_pocket_job()]
    result = run_job_batch(jobs)
    assert result["batch_report"]["failed_count"] == 0


def test_run_job_batch_two_valid_results_length():
    jobs = [_valid_drill_job(), _valid_pocket_job()]
    result = run_job_batch(jobs)
    assert len(result["batch_report"]["results"]) == 2


def test_run_job_batch_two_valid_ok():
    jobs = [_valid_drill_job(), _valid_pocket_job()]
    result = run_job_batch(jobs)
    assert result["ok"] is True


def test_run_job_batch_two_valid_status():
    jobs = [_valid_drill_job(), _valid_pocket_job()]
    result = run_job_batch(jobs)
    assert result["batch_report"]["status"] in ("ok", "warning")


def test_run_job_batch_has_required_keys():
    result = run_job_batch([_valid_drill_job()])
    assert "ok" in result
    assert "batch_report" in result
    assert "warnings" in result
    assert "errors" in result


def test_run_job_batch_report_has_required_keys():
    result = run_job_batch([_valid_drill_job()])
    br = result["batch_report"]
    for key in (
        "schema_version", "batch_id", "created_at", "status",
        "total_jobs", "ok_count", "warning_count", "failed_count", "results",
    ):
        assert key in br, f"Missing batch_report key: {key!r}"


def test_run_job_batch_schema_version():
    result = run_job_batch([_valid_drill_job()])
    assert result["batch_report"]["schema_version"] == "0.1"


def test_run_job_batch_batch_id_set():
    result = run_job_batch([_valid_drill_job()])
    assert result["batch_report"]["batch_id"].startswith("batch_")


def test_run_job_batch_result_entries_have_run_id():
    result = run_job_batch([_valid_drill_job()])
    entry = result["batch_report"]["results"][0]
    assert entry.get("run_id") is not None


# ---------------------------------------------------------------------------
# B) run_job_batch — one valid, one invalid
# ---------------------------------------------------------------------------


def test_run_job_batch_mixed_total():
    jobs = [_valid_drill_job(), _invalid_job()]
    result = run_job_batch(jobs)
    assert result["batch_report"]["total_jobs"] == 2


def test_run_job_batch_mixed_failed_count():
    jobs = [_valid_drill_job(), _invalid_job()]
    result = run_job_batch(jobs)
    assert result["batch_report"]["failed_count"] >= 1


def test_run_job_batch_mixed_ok_false():
    jobs = [_valid_drill_job(), _invalid_job()]
    result = run_job_batch(jobs)
    assert result["ok"] is False


def test_run_job_batch_mixed_status():
    jobs = [_valid_drill_job(), _invalid_job()]
    result = run_job_batch(jobs)
    assert result["batch_report"]["status"] in ("mixed", "failed")


def test_run_job_batch_invalid_entry_has_errors():
    jobs = [_valid_drill_job(), _invalid_job()]
    result = run_job_batch(jobs)
    invalid_entry = result["batch_report"]["results"][1]
    assert invalid_entry["status"] == "failed"
    assert len(invalid_entry["errors"]) > 0


# ---------------------------------------------------------------------------
# C) run_job_batch — save_artifacts with tmp_path
# ---------------------------------------------------------------------------


def test_run_job_batch_save_artifacts_creates_files(tmp_path):
    jobs = [_valid_drill_job(name="drill test")]
    result = run_job_batch(
        jobs,
        output_dir=str(tmp_path / "batch_out"),
        save_artifacts=True,
    )
    assert result["ok"] is True
    entry = result["batch_report"]["results"][0]
    assert entry["gcode_path"] is not None
    assert os.path.exists(entry["gcode_path"])
    assert entry["report_path"] is not None
    assert os.path.exists(entry["report_path"])


def test_run_job_batch_save_artifacts_gcode_nonempty(tmp_path):
    result = run_job_batch(
        [_valid_drill_job()],
        output_dir=str(tmp_path / "out"),
        save_artifacts=True,
    )
    gcode_path = result["batch_report"]["results"][0]["gcode_path"]
    with open(gcode_path, encoding="utf-8") as fh:
        content = fh.read()
    assert len(content) > 0


def test_run_job_batch_save_artifacts_report_valid_json(tmp_path):
    result = run_job_batch(
        [_valid_drill_job()],
        output_dir=str(tmp_path / "out"),
        save_artifacts=True,
    )
    report_path = result["batch_report"]["results"][0]["report_path"]
    with open(report_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict)


def test_run_job_batch_no_artifacts_no_paths(tmp_path):
    """With save_artifacts=False, gcode_path and report_path must be None."""
    result = run_job_batch([_valid_drill_job()], save_artifacts=False)
    entry = result["batch_report"]["results"][0]
    assert entry["gcode_path"] is None
    assert entry["report_path"] is None


# ---------------------------------------------------------------------------
# D) run_job_batch_from_paths — example job files
# ---------------------------------------------------------------------------


def test_run_job_batch_from_paths_example_jobs():
    paths = [
        "examples/jobs/drill_pattern_job.json",
        "examples/jobs/milling_pocket_job.json",
    ]
    result = run_job_batch_from_paths(paths)
    assert result["batch_report"]["total_jobs"] == 2
    assert result["ok"] is True


def test_run_job_batch_from_paths_results_have_job_path():
    paths = [
        "examples/jobs/drill_pattern_job.json",
        "examples/jobs/milling_pocket_job.json",
    ]
    result = run_job_batch_from_paths(paths)
    for entry in result["batch_report"]["results"]:
        assert entry["job_path"] is not None


def test_run_job_batch_from_paths_preserves_order():
    paths = [
        "examples/jobs/drill_pattern_job.json",
        "examples/jobs/milling_pocket_job.json",
    ]
    result = run_job_batch_from_paths(paths)
    assert result["batch_report"]["results"][0]["job_index"] == 0
    assert result["batch_report"]["results"][1]["job_index"] == 1


def test_run_job_batch_from_paths_save_artifacts(tmp_path):
    paths = ["examples/jobs/drill_pattern_job.json"]
    result = run_job_batch_from_paths(
        paths,
        output_dir=str(tmp_path / "out"),
        save_artifacts=True,
    )
    assert result["ok"] is True
    entry = result["batch_report"]["results"][0]
    assert os.path.exists(entry["gcode_path"])


# ---------------------------------------------------------------------------
# E) run_job_batch_from_paths — nonexistent path
# ---------------------------------------------------------------------------


def test_run_job_batch_from_paths_nonexistent_failed():
    result = run_job_batch_from_paths(["/nonexistent/job.json"])
    assert result["batch_report"]["failed_count"] == 1


def test_run_job_batch_from_paths_nonexistent_ok_false():
    result = run_job_batch_from_paths(["/nonexistent/job.json"])
    assert result["ok"] is False


def test_run_job_batch_from_paths_nonexistent_has_error():
    result = run_job_batch_from_paths(["/nonexistent/job.json"])
    entry = result["batch_report"]["results"][0]
    assert len(entry["errors"]) > 0


# ---------------------------------------------------------------------------
# F) run_job_batch_from_directory — tmp_path with two JSON files
# ---------------------------------------------------------------------------


def _write_job(path: str, job: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=2)


def test_run_job_batch_from_directory_finds_both(tmp_path):
    _write_job(str(tmp_path / "job_a.json"), _valid_drill_job(name="Job A"))
    _write_job(str(tmp_path / "job_b.json"), _valid_pocket_job(name="Job B"))
    result = run_job_batch_from_directory(str(tmp_path))
    assert result["batch_report"]["total_jobs"] == 2


def test_run_job_batch_from_directory_ok(tmp_path):
    _write_job(str(tmp_path / "job_a.json"), _valid_drill_job())
    _write_job(str(tmp_path / "job_b.json"), _valid_pocket_job())
    result = run_job_batch_from_directory(str(tmp_path))
    assert result["ok"] is True


def test_run_job_batch_from_directory_sorted_order(tmp_path):
    _write_job(str(tmp_path / "b_job.json"), _valid_drill_job(name="B"))
    _write_job(str(tmp_path / "a_job.json"), _valid_drill_job(name="A"))
    result = run_job_batch_from_directory(str(tmp_path))
    paths = [e["job_path"] for e in result["batch_report"]["results"]]
    assert paths == sorted(paths)


def test_run_job_batch_from_directory_custom_pattern(tmp_path):
    _write_job(str(tmp_path / "job.json"), _valid_drill_job())
    (tmp_path / "readme.txt").write_text("not a job")
    result = run_job_batch_from_directory(str(tmp_path), pattern="*.json")
    assert result["batch_report"]["total_jobs"] == 1


# ---------------------------------------------------------------------------
# G) run_job_batch_from_directory — nonexistent directory
# ---------------------------------------------------------------------------


def test_run_job_batch_from_directory_nonexistent_not_ok():
    result = run_job_batch_from_directory("/nonexistent/dir/that/does_not_exist")
    assert result["ok"] is False


def test_run_job_batch_from_directory_nonexistent_has_error():
    result = run_job_batch_from_directory("/nonexistent/dir/that/does_not_exist")
    assert len(result["errors"]) > 0


def test_run_job_batch_from_directory_empty_dir_ok_false(tmp_path):
    """Empty directory (no matching files) returns ok=False."""
    result = run_job_batch_from_directory(str(tmp_path))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# H) save_batch_report / load_batch_report — roundtrip
# ---------------------------------------------------------------------------


def test_save_batch_report_ok(tmp_path):
    result = run_job_batch([_valid_drill_job()])
    br = result["batch_report"]
    save_result = save_batch_report(br, str(tmp_path / "batch.json"))
    assert save_result["ok"] is True


def test_load_batch_report_ok(tmp_path):
    result = run_job_batch([_valid_drill_job()])
    path = str(tmp_path / "batch.json")
    save_batch_report(result["batch_report"], path)
    load_result = load_batch_report(path)
    assert load_result["ok"] is True


def test_save_load_batch_id_preserved(tmp_path):
    result = run_job_batch([_valid_drill_job()])
    batch_id = result["batch_report"]["batch_id"]
    path = str(tmp_path / "batch.json")
    save_batch_report(result["batch_report"], path)
    loaded = load_batch_report(path)
    assert loaded["batch_report"]["batch_id"] == batch_id


def test_save_load_status_preserved(tmp_path):
    result = run_job_batch([_valid_drill_job()])
    status = result["batch_report"]["status"]
    path = str(tmp_path / "batch.json")
    save_batch_report(result["batch_report"], path)
    loaded = load_batch_report(path)
    assert loaded["batch_report"]["status"] == status


def test_save_load_total_jobs_preserved(tmp_path):
    jobs = [_valid_drill_job(), _valid_pocket_job()]
    result = run_job_batch(jobs)
    path = str(tmp_path / "batch.json")
    save_batch_report(result["batch_report"], path)
    loaded = load_batch_report(path)
    assert loaded["batch_report"]["total_jobs"] == 2


def test_load_batch_report_missing_not_ok():
    result = load_batch_report("/nonexistent/batch.json")
    assert result["ok"] is False
    assert len(result["errors"]) > 0


def test_load_batch_report_invalid_json_not_ok(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w") as fh:
        fh.write("not json")
    result = load_batch_report(path)
    assert result["ok"] is False


def test_save_batch_report_non_dict_not_ok(tmp_path):
    result = save_batch_report("not a dict", str(tmp_path / "x.json"))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# I) edge cases
# ---------------------------------------------------------------------------


def test_run_job_batch_empty_list():
    result = run_job_batch([])
    assert result["batch_report"]["total_jobs"] == 0
    assert result["ok"] is True  # 0 failed


def test_run_job_batch_non_list_not_ok():
    result = run_job_batch("not a list")
    assert result["ok"] is False


def test_run_job_batch_from_paths_empty_list():
    result = run_job_batch_from_paths([])
    assert result["batch_report"]["total_jobs"] == 0
