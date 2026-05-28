"""Batch job tools — run multiple CNCJobSpecs and produce a batch report.

Each job is processed via ``run_job`` from ``cnc.tools.job_runs``.
No LLMs are called. G-code is always regenerated deterministically.
Stored ``gcode`` fields in jobs are ignored.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from cnc.schemas.batch_report import utc_now_iso
from cnc.tools.job_io import load_job_spec
from cnc.tools.job_runs import run_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_batch_id(prefix: str = "batch") -> str:
    """Return a unique batch ID like ``batch_<uuid4>``."""
    return f"{prefix}_{uuid.uuid4()}"


def _safe_filename(value: str | None, fallback: str) -> str:
    """Produce a filesystem-safe filename stem from *value*.

    Rules:
    - lowercase
    - spaces → ``_``
    - keep only a-z, 0-9, ``_``, ``-``, ``.``
    - truncate to 80 characters
    - use *fallback* when the cleaned string is empty
    """
    if not value:
        return fallback[:80]
    cleaned = value.lower().replace(" ", "_")
    cleaned = re.sub(r"[^a-z0-9_\-.]", "", cleaned)
    cleaned = cleaned[:80]
    return cleaned if cleaned else fallback[:80]


def _derive_batch_status(ok_count: int, warning_count: int, failed_count: int) -> str:
    total = ok_count + warning_count + failed_count
    if total == 0:
        return "ok"
    if failed_count == total:
        return "failed"
    if failed_count > 0:
        return "mixed"
    if warning_count > 0:
        return "warning"
    return "ok"


def _extract_artifact_paths(artifacts: list[dict]) -> tuple[str | None, str | None]:
    """Return (gcode_path, report_path) from a list of run artifacts."""
    gcode_path: str | None = None
    report_path: str | None = None
    for art in artifacts:
        if art.get("kind") == "gcode":
            gcode_path = art.get("path")
        elif art.get("kind") == "run_report":
            report_path = art.get("path")
    return gcode_path, report_path


# ---------------------------------------------------------------------------
# run_job_batch
# ---------------------------------------------------------------------------

def run_job_batch(
    jobs: list[dict],
    output_dir: str | None = None,
    save_artifacts: bool = False,
    batch_name: str | None = None,
) -> dict:
    """Run a list of CNCJobSpec dicts through the full deterministic pipeline.

    Parameters
    ----------
    jobs:           List of CNCJobSpec dicts.
    output_dir:     Root directory for saved artifacts.  Required when
                    ``save_artifacts=True``.  Defaults to
                    ``outputs/batches/<batch_id>``.
    save_artifacts: When ``True``, save G-code (``.nc``) and run report
                    (``.json``) for each job under ``output_dir``.
    batch_name:     Optional human-readable label stored in the report.

    Returns
    -------
    ::

        {
          "ok": bool,
          "batch_report": dict,
          "warnings": list[str],
          "errors": list[str],
        }
    """
    batch_id = create_batch_id()
    created_at = utc_now_iso()
    batch_warnings: list[str] = []
    batch_errors: list[str] = []
    results: list[dict] = []

    if not isinstance(jobs, list):
        batch_errors.append("jobs must be a list.")
        return {
            "ok": False,
            "batch_report": _build_batch_report(
                batch_id=batch_id,
                created_at=created_at,
                total_jobs=0,
                ok_count=0,
                warning_count=0,
                failed_count=0,
                results=[],
                warnings=batch_warnings,
                errors=batch_errors,
                batch_name=batch_name,
            ),
            "warnings": batch_warnings,
            "errors": batch_errors,
        }

    # Resolve output directory.
    resolved_output_dir: str | None = None
    if save_artifacts:
        resolved_output_dir = output_dir or os.path.join("outputs", "batches", batch_id)
        try:
            _ensure_dirs(resolved_output_dir)
        except OSError as exc:
            batch_warnings.append(
                f"Could not create output directory '{resolved_output_dir}': {exc}. "
                "Artifacts will not be saved."
            )
            save_artifacts = False
            resolved_output_dir = None

    ok_count = warning_count = failed_count = 0

    for idx, job in enumerate(jobs):
        job_name = job.get("name") if isinstance(job, dict) else None
        safe_name = _safe_filename(job_name, f"job_{idx}")
        stem = f"job_{idx}_{safe_name}"

        save_gcode_path: str | None = None
        save_report_path: str | None = None

        if save_artifacts and resolved_output_dir:
            save_gcode_path = os.path.join(resolved_output_dir, "gcode", f"{stem}.nc")
            save_report_path = os.path.join(resolved_output_dir, "reports", f"{stem}_run.json")

        try:
            run_result = run_job(
                job,
                save_gcode_path=save_gcode_path,
                save_report_path=save_report_path,
            )
        except Exception as exc:  # noqa: BLE001
            run_result = {
                "ok": False,
                "run_report": {"status": "failed", "run_id": None},
                "warnings": [],
                "errors": [f"run_job raised unexpected exception: {exc}"],
                "artifacts": [],
            }

        rr = run_result.get("run_report", {})
        job_status = rr.get("status", "failed")
        job_ok = run_result.get("ok", False)
        run_id = rr.get("run_id")
        gcode_path, report_path = _extract_artifact_paths(run_result.get("artifacts", []))

        if job_ok and job_status == "ok":
            ok_count += 1
        elif job_status == "warning":
            warning_count += 1
        else:
            failed_count += 1

        results.append({
            "job_index": idx,
            "job_name": job_name,
            "job_path": None,
            "ok": job_ok,
            "status": job_status,
            "run_id": run_id,
            "report_path": report_path,
            "gcode_path": gcode_path,
            "warnings": run_result.get("warnings", []),
            "errors": run_result.get("errors", []),
            "metadata": {},
        })

    batch_status = _derive_batch_status(ok_count, warning_count, failed_count)
    batch_report = _build_batch_report(
        batch_id=batch_id,
        created_at=created_at,
        total_jobs=len(jobs),
        ok_count=ok_count,
        warning_count=warning_count,
        failed_count=failed_count,
        results=results,
        warnings=batch_warnings,
        errors=batch_errors,
        batch_name=batch_name,
    )

    return {
        "ok": failed_count == 0,
        "batch_report": batch_report,
        "warnings": batch_warnings,
        "errors": batch_errors,
    }


# ---------------------------------------------------------------------------
# run_job_batch_from_paths
# ---------------------------------------------------------------------------

def run_job_batch_from_paths(
    paths: list[str],
    output_dir: str | None = None,
    save_artifacts: bool = False,
    batch_name: str | None = None,
) -> dict:
    """Load JobSpec JSON files from *paths* and run them as a batch.

    Files that cannot be loaded produce a ``failed`` result entry.
    Order of *paths* is preserved.
    """
    batch_id = create_batch_id()
    created_at = utc_now_iso()
    batch_warnings: list[str] = []
    batch_errors: list[str] = []
    results: list[dict] = []

    if not isinstance(paths, list):
        batch_errors.append("paths must be a list.")
        return {
            "ok": False,
            "batch_report": _build_batch_report(
                batch_id=batch_id,
                created_at=created_at,
                total_jobs=0,
                ok_count=0,
                warning_count=0,
                failed_count=0,
                results=[],
                warnings=batch_warnings,
                errors=batch_errors,
                batch_name=batch_name,
            ),
            "warnings": batch_warnings,
            "errors": batch_errors,
        }

    # Resolve output directory.
    resolved_output_dir: str | None = None
    if save_artifacts:
        resolved_output_dir = output_dir or os.path.join("outputs", "batches", batch_id)
        try:
            _ensure_dirs(resolved_output_dir)
        except OSError as exc:
            batch_warnings.append(
                f"Could not create output directory '{resolved_output_dir}': {exc}. "
                "Artifacts will not be saved."
            )
            save_artifacts = False
            resolved_output_dir = None

    ok_count = warning_count = failed_count = 0

    for idx, path in enumerate(paths):
        load_result = load_job_spec(path)
        if not load_result["ok"]:
            failed_count += 1
            results.append({
                "job_index": idx,
                "job_name": None,
                "job_path": path,
                "ok": False,
                "status": "failed",
                "run_id": None,
                "report_path": None,
                "gcode_path": None,
                "warnings": load_result.get("warnings", []),
                "errors": load_result.get("errors", []),
                "metadata": {},
            })
            continue

        job = load_result["job"]
        job_name = job.get("name") if isinstance(job, dict) else None
        safe_name = _safe_filename(job_name, f"job_{idx}")
        stem = f"job_{idx}_{safe_name}"

        save_gcode_path: str | None = None
        save_report_path: str | None = None

        if save_artifacts and resolved_output_dir:
            save_gcode_path = os.path.join(resolved_output_dir, "gcode", f"{stem}.nc")
            save_report_path = os.path.join(resolved_output_dir, "reports", f"{stem}_run.json")

        try:
            run_result = run_job(
                job,
                save_gcode_path=save_gcode_path,
                save_report_path=save_report_path,
            )
        except Exception as exc:  # noqa: BLE001
            run_result = {
                "ok": False,
                "run_report": {"status": "failed", "run_id": None},
                "warnings": [],
                "errors": [f"run_job raised unexpected exception: {exc}"],
                "artifacts": [],
            }

        rr = run_result.get("run_report", {})
        job_status = rr.get("status", "failed")
        job_ok = run_result.get("ok", False)
        run_id = rr.get("run_id")
        gcode_path, report_path = _extract_artifact_paths(run_result.get("artifacts", []))

        if job_ok and job_status == "ok":
            ok_count += 1
        elif job_status == "warning":
            warning_count += 1
        else:
            failed_count += 1

        results.append({
            "job_index": idx,
            "job_name": job_name,
            "job_path": path,
            "ok": job_ok,
            "status": job_status,
            "run_id": run_id,
            "report_path": report_path,
            "gcode_path": gcode_path,
            "warnings": run_result.get("warnings", []),
            "errors": run_result.get("errors", []),
            "metadata": {},
        })

    batch_status = _derive_batch_status(ok_count, warning_count, failed_count)
    batch_report = _build_batch_report(
        batch_id=batch_id,
        created_at=created_at,
        total_jobs=len(paths),
        ok_count=ok_count,
        warning_count=warning_count,
        failed_count=failed_count,
        results=results,
        warnings=batch_warnings,
        errors=batch_errors,
        batch_name=batch_name,
    )

    return {
        "ok": failed_count == 0,
        "batch_report": batch_report,
        "warnings": batch_warnings,
        "errors": batch_errors,
    }


# ---------------------------------------------------------------------------
# run_job_batch_from_directory
# ---------------------------------------------------------------------------

def run_job_batch_from_directory(
    directory: str,
    pattern: str = "*.json",
    output_dir: str | None = None,
    save_artifacts: bool = False,
    batch_name: str | None = None,
) -> dict:
    """Glob *directory* for files matching *pattern* and run them as a batch.

    Paths are sorted stably before processing.
    """
    dir_path = Path(directory)

    if not dir_path.exists():
        return {
            "ok": False,
            "batch_report": _build_batch_report(
                batch_id=create_batch_id(),
                created_at=utc_now_iso(),
                total_jobs=0,
                ok_count=0,
                warning_count=0,
                failed_count=0,
                results=[],
                warnings=[],
                errors=[f"Directory not found: '{directory}'."],
                batch_name=batch_name,
            ),
            "warnings": [],
            "errors": [f"Directory not found: '{directory}'."],
        }

    if not dir_path.is_dir():
        return {
            "ok": False,
            "batch_report": _build_batch_report(
                batch_id=create_batch_id(),
                created_at=utc_now_iso(),
                total_jobs=0,
                ok_count=0,
                warning_count=0,
                failed_count=0,
                results=[],
                warnings=[],
                errors=[f"Path is not a directory: '{directory}'."],
                batch_name=batch_name,
            ),
            "warnings": [],
            "errors": [f"Path is not a directory: '{directory}'."],
        }

    matched = sorted(p for p in dir_path.glob(pattern) if p.is_file())

    if not matched:
        return {
            "ok": False,
            "batch_report": _build_batch_report(
                batch_id=create_batch_id(),
                created_at=utc_now_iso(),
                total_jobs=0,
                ok_count=0,
                warning_count=0,
                failed_count=0,
                results=[],
                warnings=[f"No files matching '{pattern}' found in '{directory}'."],
                errors=[],
                batch_name=batch_name,
            ),
            "warnings": [f"No files matching '{pattern}' found in '{directory}'."],
            "errors": [],
        }

    paths = [str(p) for p in matched]
    return run_job_batch_from_paths(
        paths=paths,
        output_dir=output_dir,
        save_artifacts=save_artifacts,
        batch_name=batch_name,
    )


# ---------------------------------------------------------------------------
# save_batch_report / load_batch_report
# ---------------------------------------------------------------------------

def save_batch_report(batch_report: dict, path: str) -> dict:
    """Serialise a batch report dict to a UTF-8 JSON file."""
    if not isinstance(batch_report, dict):
        return {
            "ok": False,
            "path": path,
            "errors": ["batch_report must be a dict."],
            "warnings": [],
        }
    errors: list[str] = []
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(batch_report, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        errors.append(f"Could not write file '{path}': {exc}")
    except TypeError as exc:
        errors.append(f"batch_report is not JSON-serialisable: {exc}")
    return {"ok": len(errors) == 0, "path": path, "errors": errors, "warnings": []}


def load_batch_report(path: str) -> dict:
    """Load a batch report dict from a UTF-8 JSON file."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {
            "ok": False,
            "batch_report": None,
            "path": path,
            "errors": [f"File not found: '{path}'."],
            "warnings": [],
        }
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "batch_report": None,
            "path": path,
            "errors": [f"Invalid JSON in '{path}': {exc}"],
            "warnings": [],
        }
    except OSError as exc:
        return {
            "ok": False,
            "batch_report": None,
            "path": path,
            "errors": [f"Could not read file '{path}': {exc}"],
            "warnings": [],
        }
    if not isinstance(data, dict):
        return {
            "ok": False,
            "batch_report": None,
            "path": path,
            "errors": ["File does not contain a JSON object at the top level."],
            "warnings": [],
        }
    return {"ok": True, "batch_report": data, "path": path, "errors": [], "warnings": []}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_batch_report(
    *,
    batch_id: str,
    created_at: str,
    total_jobs: int,
    ok_count: int,
    warning_count: int,
    failed_count: int,
    results: list[dict],
    warnings: list[str],
    errors: list[str],
    batch_name: str | None,
) -> dict:
    status = _derive_batch_status(ok_count, warning_count, failed_count)
    return {
        "schema_version": "0.1",
        "batch_id": batch_id,
        "created_at": created_at,
        "status": status,
        "total_jobs": total_jobs,
        "ok_count": ok_count,
        "warning_count": warning_count,
        "failed_count": failed_count,
        "results": results,
        "warnings": list(warnings),
        "errors": list(errors),
        "metadata": {"batch_name": batch_name} if batch_name else {},
    }


def _ensure_dirs(base: str) -> None:
    """Create base/gcode and base/reports directories."""
    os.makedirs(os.path.join(base, "gcode"), exist_ok=True)
    os.makedirs(os.path.join(base, "reports"), exist_ok=True)
