"""Run Report schema — documents a concrete CNC job execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class RunArtifact(BaseModel):
    """A file or artefact produced by a run."""

    kind: str  # "gcode" | "run_report"
    path: str | None = None
    content_preview: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CNCRunReport(BaseModel):
    """Full record of one CNC job execution.

    A run report documents everything that happened when a JobSpec was
    processed: validation, guardrails, postprocessing, safety analysis,
    and the final G-code.  It is a traceability artefact — not a safety
    release or a G-code authority.

    ``status`` values:
      * ``"ok"``      — no errors, no warnings
      * ``"warning"`` — no errors but at least one warning
      * ``"failed"``  — at least one error (gcode is always empty)
    """

    schema_version: str = "0.1"
    run_id: str
    created_at: str
    status: str  # "ok" | "warning" | "failed"
    job: dict[str, Any]
    postprocessor: str
    operation_plan_validation: dict[str, Any] | None = None
    guardrails: dict[str, Any] | None = None
    postprocess_result: dict[str, Any] | None = None
    safety_report: dict[str, Any] | None = None
    gcode: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    artifacts: list[RunArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
