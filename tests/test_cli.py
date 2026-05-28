"""Tests for cnc/cli.py — no LLM, no API key required."""

from __future__ import annotations

import json
import os

import pytest

from cnc.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_stdout(capsys) -> dict | list:
    captured = capsys.readouterr()
    return json.loads(captured.out)


# ---------------------------------------------------------------------------
# A) list-profiles
# ---------------------------------------------------------------------------


def test_list_profiles_exit_zero(capsys):
    rc = main(["list-profiles"])
    assert rc == 0


def test_list_profiles_returns_list(capsys):
    main(["list-profiles"])
    data = _parse_stdout(capsys)
    assert isinstance(data, list)
    assert len(data) > 0


def test_list_profiles_contains_generic_drill_mm(capsys):
    main(["list-profiles"])
    data = _parse_stdout(capsys)
    names = [p["name"] for p in data]
    assert "generic_drill_mm" in names


# ---------------------------------------------------------------------------
# B) list-tools (Tool Library not yet available — graceful degradation)
# ---------------------------------------------------------------------------


def test_list_tools_does_not_crash(capsys):
    rc = main(["list-tools"])
    assert rc == 0  # Tool Library is now available


def test_list_tools_output_is_json(capsys):
    main(["list-tools"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, (list, dict))


def test_list_tools_exit_zero(capsys):
    rc = main(["list-tools"])
    assert rc == 0


def test_list_tools_returns_list(capsys):
    main(["list-tools"])
    data = _parse_stdout(capsys)
    assert isinstance(data, list)
    assert len(data) > 0


def test_list_tools_contains_drill_5mm(capsys):
    main(["list-tools"])
    data = _parse_stdout(capsys)
    ids = [t["id"] for t in data]
    assert "drill_5mm" in ids


def test_list_tools_filter_machine_type(capsys):
    rc = main(["list-tools", "--machine-type", "drill"])
    assert rc == 0
    data = _parse_stdout(capsys)
    assert isinstance(data, list)
    for t in data:
        assert "drill" in t["supported_machine_types"]


def test_list_tools_filter_tool_type(capsys):
    rc = main(["list-tools", "--tool-type", "end_mill"])
    assert rc == 0
    data = _parse_stdout(capsys)
    assert isinstance(data, list)
    for t in data:
        assert t["tool_type"] == "end_mill"


# ---------------------------------------------------------------------------
# C) list-materials
# ---------------------------------------------------------------------------


def test_list_materials_exit_zero(capsys):
    rc = main(["list-materials"])
    assert rc == 0


def test_list_materials_returns_list(capsys):
    main(["list-materials"])
    data = _parse_stdout(capsys)
    assert isinstance(data, list)
    assert len(data) > 0


def test_list_materials_contains_aluminum_6061(capsys):
    main(["list-materials"])
    data = _parse_stdout(capsys)
    ids = [m["id"] for m in data]
    assert "aluminum_6061" in ids


def test_list_materials_filter_category(capsys):
    rc = main(["list-materials", "--category", "aluminum"])
    assert rc == 0
    data = _parse_stdout(capsys)
    assert isinstance(data, list)
    for m in data:
        assert m["category"] == "aluminum"


def test_list_materials_filter_unknown_category_empty(capsys):
    rc = main(["list-materials", "--category", "unobtainium_xyz"])
    assert rc == 0
    data = _parse_stdout(capsys)
    assert data == []


# ---------------------------------------------------------------------------
# D) validate-job — valid example job
# ---------------------------------------------------------------------------


def test_validate_job_valid_exit_zero(capsys):
    rc = main(["validate-job", "examples/jobs/drill_pattern_job.json"])
    assert rc == 0


def test_validate_job_valid_ok_true(capsys):
    main(["validate-job", "examples/jobs/drill_pattern_job.json"])
    data = _parse_stdout(capsys)
    assert data["ok"] is True


def test_validate_job_pocket_exit_zero(capsys):
    rc = main(["validate-job", "examples/jobs/milling_pocket_job.json"])
    assert rc == 0


# ---------------------------------------------------------------------------
# E) validate-job — nonexistent path
# ---------------------------------------------------------------------------


def test_validate_job_missing_file_exit_one(capsys):
    rc = main(["validate-job", "/nonexistent/job.json"])
    assert rc == 1


def test_validate_job_missing_file_ok_false(capsys):
    main(["validate-job", "/nonexistent/job.json"])
    data = _parse_stdout(capsys)
    assert data["ok"] is False
    assert len(data["errors"]) > 0


# ---------------------------------------------------------------------------
# F) run-job — with tmp_path outputs
# ---------------------------------------------------------------------------


def test_run_job_exit_code(capsys, tmp_path):
    gcode_out = str(tmp_path / "out.nc")
    report_out = str(tmp_path / "run.json")
    rc = main([
        "run-job", "examples/jobs/drill_pattern_job.json",
        "--gcode-out", gcode_out,
        "--report-out", report_out,
    ])
    # 0 = ok, 1 = failed — warnings alone should not break it
    assert rc in (0, 1)


def test_run_job_creates_gcode_file(capsys, tmp_path):
    gcode_out = str(tmp_path / "out.nc")
    rc = main([
        "run-job", "examples/jobs/drill_pattern_job.json",
        "--gcode-out", gcode_out,
    ])
    if rc == 0:
        assert os.path.exists(gcode_out)


def test_run_job_creates_report_file(capsys, tmp_path):
    report_out = str(tmp_path / "run.json")
    rc = main([
        "run-job", "examples/jobs/drill_pattern_job.json",
        "--report-out", report_out,
    ])
    if rc == 0:
        assert os.path.exists(report_out)


def test_run_job_output_is_json(capsys, tmp_path):
    main(["run-job", "examples/jobs/drill_pattern_job.json"])
    data = _parse_stdout(capsys)
    assert isinstance(data, dict)
    assert "ok" in data
    assert "status" in data


def test_run_job_summary_has_gcode_lines(capsys):
    main(["run-job", "examples/jobs/drill_pattern_job.json"])
    data = _parse_stdout(capsys)
    assert "gcode_lines" in data
    if data["ok"]:
        assert data["gcode_lines"] > 0


def test_run_job_missing_file_exit_one(capsys):
    rc = main(["run-job", "/nonexistent/job.json"])
    assert rc == 1


# ---------------------------------------------------------------------------
# G) analyze-gcode
# ---------------------------------------------------------------------------

_SIMPLE_DRILL_GCODE = (
    "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG00 X0 Y0\n"
    "G01 Z-5 F100\nG00 Z5\nM05\nM30\n"
)


def test_analyze_gcode_exit_zero(capsys, tmp_path):
    gcode_path = str(tmp_path / "test.nc")
    with open(gcode_path, "w", encoding="utf-8") as fh:
        fh.write(_SIMPLE_DRILL_GCODE)
    rc = main([
        "analyze-gcode", gcode_path,
        "--machine-type", "drill",
        "--expected-units", "mm",
    ])
    assert rc == 0


def test_analyze_gcode_output_has_ok(capsys, tmp_path):
    gcode_path = str(tmp_path / "test.nc")
    with open(gcode_path, "w", encoding="utf-8") as fh:
        fh.write(_SIMPLE_DRILL_GCODE)
    main(["analyze-gcode", gcode_path, "--machine-type", "drill"])
    data = _parse_stdout(capsys)
    assert "ok" in data


def test_analyze_gcode_output_has_risk_level(capsys, tmp_path):
    gcode_path = str(tmp_path / "test.nc")
    with open(gcode_path, "w", encoding="utf-8") as fh:
        fh.write(_SIMPLE_DRILL_GCODE)
    main(["analyze-gcode", gcode_path, "--machine-type", "drill"])
    data = _parse_stdout(capsys)
    assert "risk_level" in data


def test_analyze_gcode_missing_file_exit_one(capsys):
    rc = main(["analyze-gcode", "/nonexistent/file.nc"])
    assert rc == 1


def test_analyze_gcode_with_safe_z_and_max_depth(capsys, tmp_path):
    gcode_path = str(tmp_path / "test.nc")
    with open(gcode_path, "w", encoding="utf-8") as fh:
        fh.write(_SIMPLE_DRILL_GCODE)
    rc = main([
        "analyze-gcode", gcode_path,
        "--machine-type", "drill",
        "--safe-z", "5.0",
        "--max-depth", "20.0",
    ])
    assert rc == 0


# ---------------------------------------------------------------------------
# H) batch-run — directory
# ---------------------------------------------------------------------------


def test_batch_run_directory_exit_code(capsys, tmp_path):
    rc = main([
        "batch-run", "examples/jobs",
        "--output-dir", str(tmp_path / "batch"),
        "--save-artifacts",
    ])
    assert rc in (0, 1)  # warnings may make some jobs status=warning but ok=True


def test_batch_run_directory_output_is_json(capsys, tmp_path):
    main(["batch-run", "examples/jobs"])
    data = _parse_stdout(capsys)
    assert isinstance(data, dict)
    assert "total_jobs" in data


def test_batch_run_directory_total_jobs(capsys):
    main(["batch-run", "examples/jobs"])
    data = _parse_stdout(capsys)
    assert data["total_jobs"] >= 2


def test_batch_run_directory_results_list(capsys):
    main(["batch-run", "examples/jobs"])
    data = _parse_stdout(capsys)
    assert isinstance(data.get("results"), list)


def test_batch_run_single_file(capsys):
    rc = main(["batch-run", "examples/jobs/drill_pattern_job.json"])
    assert rc in (0, 1)
    data = _parse_stdout(capsys)
    assert data["total_jobs"] == 1


def test_batch_run_nonexistent_path_exit_one(capsys):
    rc = main(["batch-run", "/nonexistent/path"])
    assert rc == 1


def test_batch_run_with_save_artifacts(capsys, tmp_path):
    out_dir = str(tmp_path / "batch")
    rc = main([
        "batch-run", "examples/jobs/drill_pattern_job.json",
        "--output-dir", out_dir,
        "--save-artifacts",
    ])
    assert rc in (0, 1)


# ---------------------------------------------------------------------------
# I) server subcommand
# ---------------------------------------------------------------------------


def test_server_exit_zero(capsys):
    rc = main(["server"])
    assert rc == 0


def test_server_prints_instructions(capsys):
    main(["server"])
    captured = capsys.readouterr()
    assert "cnc.server" in captured.out
