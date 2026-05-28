"""Tool Library schema — LibraryTool Pydantic model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LibraryTool(BaseModel):
    """A registered tool in the CNC Tool Library.

    Contains dimensional and capability metadata only — no cutting data.
    Cutting parameters (feedrate, spindle speed, depth of cut) are always
    job-specific and must be supplied at job-planning time.
    """

    id: str
    name: str
    tool_type: Literal["drill", "end_mill", "engraver", "laser", "unknown"] = "unknown"
    diameter: float | None = None
    units: Literal["mm", "inch"] = "mm"
    flute_count: int | None = None
    material: str | None = None
    supported_machine_types: list[str] = Field(default_factory=list)
    supported_operations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
