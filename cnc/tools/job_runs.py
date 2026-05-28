"""Job Run tools — execute a CNCJobSpec and produce a structured run report.

A *run* is one concrete processing of a JobSpec:

    validate_job_spec  →  job_spec_to_gcode  →  CNCRunReport

The run report captures every intermediate result (validation, guardrails,
postprocessor, safety analysis) and the final G-code for traceability.

No LLMs are called. G-code is always regenerated deterministically.
Stored ``gcode`` fields in the incoming job are ignored.
"""

from __future__ import annotations

import json
import uuid

from cnc.schemas.run_report import utc_now_iso
from cnc.tools.job_io import job_spec_to_gcode, validate_job_spec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_run_id(prefix: str = "run") -> str:
    """Return a unique run ID string like ``run_<uuid4>``."""
    return f"{prefix}_{uuid.uuid4()}"


def _derive_status(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "failed"
    if warnings:
        return "warning"
    return "ok"


# ---------------------------------------------------------------------------
# run_job
# ---------------------------------------------------------------------------

def run_job(
    job: dict,
    save_gcode_path: str | None = None,
    save_report_path: str | None = None,
) -> dict:
    """Execute a CNCJobSpec through the full deterministic pipeline.

    Steps:
      1. ``validate_job_spec`` — structural + guardrail checks
      2. ``job_spec_to_gcode`` — deterministic G-code generation (if valid)
      3. Optional: save G-code to ``save_gcode_path``
      4. Optional: save run report to ``save_report_path``

    Any stored ``gcode`` field on the job is ignored (handled by
    ``job_spec_to_gcode``).

    Returns::

        {
          "ok": bool,
          "run_report": dict,
          "gcode": str,
          "warnings": list[str],
          "errors": list[str],
          "artifacts": list[dict],
        }
    """
    all_warnings: list[str] = []
    all_errors: list[str] = []
    artifacts: list[dict] = []
    run_id = create_run_id()
    created_at = utc_now_iso()
    postprocessor = job.get("postprocessor", "fanuc") if isinstance(job, dict) else "fanuc"

    op_validation: dict | None = None
    guardrails: dict | None = None
    postprocess_result: dict | None = None
    safety_report: dict | None = None
    gcode = ""

    # ------------------------------------------------------------------
    # Guard: job must be a dict
    # ------------------------------------------------------------------
    if not isinstance(job, dict):
        all_errors.append("job must be a dict.")
        run_report = _build_run_report(
            run_id=run_id,
            created_at=created_at,
            status="failed",
            job=job if isinstance(job, dict) else {},
            postprocessor=postprocessor,
            op_validation=None,
            guardrails=None,
            postprocess_result=None,
            safety_report=None,
            gcode="",
            warnings=all_warnings,
            errors=all_errors,
            artifacts=artifacts,
        )
        if save_report_path:
            _try_save_report(run_report, save_report_path, artifacts)
        return {
            "ok": False,
            "run_report": run_report,
            "gcode": "",
            "warnings": all_warnings,
            "errors": all_errors,
            "artifacts": artifacts,
        }

    # ------------------------------------------------------------------
    # Step 1: validate
    # ------------------------------------------------------------------
    try:
        val_result = validate_job_spec(job)
        op_validation = val_result.get("operation_plan_validation")
        guardrails = val_result.get("guardrails")
        all_warnings.extend(val_result.get("warnings", []))
        all_errors.extend(val_result.get("errors", []))
    except Exception as exc:  # noqa: BLE001
        all_errors.append(f"validate_job_spec raised unexpected exception: {exc}")

    # ------------------------------------------------------------------
    # Step 2: generate G-code (only if validation passed)
    # ------------------------------------------------------------------
    if not all_errors:
        try:
            gc_result = job_spec_to_gcode(job)
            gcode = gc_result.get("gcode", "")
            postprocess_result = gc_result.get("validation")  # op_plan validation from pipeline
            safety_report = gc_result.get("safety_report")
            all_warnings.extend(gc_result.get("warnings", []))
            all_errors.extend(gc_result.get("errors", []))
            # Keep postprocessor from result if set
            postprocessor = gc_result.get("postprocessor", postprocessor)
        except Exception as exc:  # noqa: BLE001
            all_errors.append(f"job_spec_to_gcode raised unexpected exception: {exc}")

    # ------------------------------------------------------------------
    # Step 3: save G-code file
    # ------------------------------------------------------------------
    if gcode and save_gcode_path:
        try:
            with open(save_gcode_path, "w", encoding="utf-8") as fh:
                fh.write(gcode)
            artifacts.append({
                "kind": "gcode",
                "path": save_gcode_path,
                "content_preview": gcode[:500],
                "metadata": {"postprocessor": postprocessor},
            })
        except OSError as exc:
            all_warnings.append(f"Could not save G-code to '{save_gcode_path}': {exc}")

    # ------------------------------------------------------------------
    # Build run report
    # ------------------------------------------------------------------
    status = _derive_status(all_errors, all_warnings)
    run_report = _build_run_report(
        run_id=run_id,
        created_at=created_at,
        status=status,
        job=job,
        postprocessor=postprocessor,
        op_validation=op_validation,
        guardrails=guardrails,
        postprocess_result=postprocess_result,
        safety_report=safety_report,
        gcode=gcode,
        warnings=all_warnings,
        errors=all_errors,
        artifacts=artifacts,
    )

    # ------------------------------------------------------------------
    # Step 4: save run report
    # ------------------------------------------------------------------
    if save_report_path:
        _try_save_report(run_report, save_report_path, artifacts)
        # Update artifacts list inside run_report after appending
        run_report["artifacts"] = list(artifacts)

    return {
        "ok": len(all_errors) == 0,
        "run_report": run_report,
        "gcode": gcode,
        "warnings": all_warnings,
        "errors": all_errors,
        "artifacts": artifacts,
    }


def _build_run_report(
    *,
    run_id: str,
    created_at: str,
    status: str,
    job: dict,
    postprocessor: str,
    op_validation: dict | None,
    guardrails: dict | None,
    postprocess_result: dict | None,
    safety_report: dict | None,
    gcode: str,
    warnings: list[str],
    errors: list[str],
    artifacts: list[dict],
) -> dict:
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "created_at": created_at,
        "status": status,
        "job": job,
        "postprocessor": postprocessor,
        "operation_plan_validation": op_validation,
        "guardrails": guardrails,
        "postprocess_result": postprocess_result,
        "safety_report": safety_report,
        "gcode": gcode,
        "warnings": list(warnings),
        "errors": list(errors),
        "artifacts": list(artifacts),
        "metadata": {},
    }


def _try_save_report(run_report: dict, path: str, artifacts: list[dict]) -> None:
    """Save run_report to path; append artifact entry (mutates artifacts)."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(run_report, fh, indent=2, ensure_ascii=False)
        artifacts.append({
            "kind": "run_report",
            "path": path,
            "content_preview": None,
            "metadata": {},
        })
    except OSError as exc:
        # Can't raise — just log into run_report warnings
        run_report.setdefault("warnings", []).append(
            f"Could not save run report to '{path}': {exc}"
        )


# ---------------------------------------------------------------------------
# save_run_report / load_run_report
# ---------------------------------------------------------------------------

def save_run_report(run_report: dict, path: str) -> dict:
    """Serialise a run report dict to a UTF-8 JSON file.

    Returns::

        {"ok": bool, "path": str, "errors": list[str], "warnings": list[str]}
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(run_report, dict):
        return {
            "ok": False,
            "path": path,
            "errors": ["run_report must be a dict."],
            "warnings": [],
        }

    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(run_report, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        errors.append(f"Could not write file '{path}': {exc}")
    except TypeError as exc:
        errors.append(f"run_report is not JSON-serialisable: {exc}")

    return {
        "ok": len(errors) == 0,
        "path": path,
        "errors": errors,
        "warnings": warnings,
    }


def load_run_report(path: str) -> dict:
    """Load a run report dict from a UTF-8 JSON file.

    Returns::

        {
          "ok": bool,
          "run_report": dict | None,
          "path": str,
          "errors": list[str],
          "warnings": list[str],
        }
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {
            "ok": False,
            "run_report": None,
            "path": path,
            "errors": [f"File not found: '{path}'."],
            "warnings": [],
        }
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "run_report": None,
            "path": path,
            "errors": [f"Invalid JSON in '{path}': {exc}"],
            "warnings": [],
        }
    except OSError as exc:
        return {
            "ok": False,
            "run_report": None,
            "path": path,
            "errors": [f"Could not read file '{path}': {exc}"],
            "warnings": [],
        }

    if not isinstance(data, dict):
        return {
            "ok": False,
            "run_report": None,
            "path": path,
            "errors": ["File does not contain a JSON object at the top level."],
            "warnings": [],
        }

    return {
        "ok": True,
        "run_report": data,
        "path": path,
        "errors": [],
        "warnings": [],
    }
