"""Batch Report schema — documents a multi-job CNC batch execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class BatchJobResult(BaseModel):
    """Summary of one job within a batch run."""

    job_index: int
    job_name: str | None = None
    job_path: str | None = None
    ok: bool
    status: str  # "ok" | "warning" | "failed"
    run_id: str | None = None
    report_path: str | None = None
    gcode_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CNCBatchReport(BaseModel):
    """Full record of one batch execution.

    A batch report documents all job results from a single batch run.
    It is a traceability artefact — not a safety release.

    ``status`` values:
      * ``"ok"``      — all jobs ok
      * ``"warning"`` — no failures but at least one warning
      * ``"mixed"``   — mix of ok/warning and failed
      * ``"failed"``  — all jobs failed
    """

    schema_version: str = "0.1"
    batch_id: str
    created_at: str
    status: str  # "ok" | "warning" | "mixed" | "failed"
    total_jobs: int
    ok_count: int = 0
    warning_count: int = 0
    failed_count: int = 0
    results: list[BatchJobResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
