"""Operation plan schemas — structured representation of machining steps."""

from typing import Any, Literal
from pydantic import BaseModel, Field

from .job_spec import MachineType


class ToolSpec(BaseModel):
    tool_number: int
    description: str
    diameter_mm: float | None = None
    type: str | None = None  # e.g. "end_mill", "drill", "face_mill"
    flutes: int | None = None
    material: str | None = None  # e.g. "carbide", "HSS"


class Operation(BaseModel):
    name: str
    type: str  # e.g. "face_mill", "pocket", "profile", "drill", "bore"
    tool_number: int
    feedrate_mmpm: float | None = None
    spindle_rpm: int | None = None
    depth_mm: float | None = None
    stepover_mm: float | None = None
    parameters: dict[str, Any] = {}
    notes: str | None = None


class OperationPlan(BaseModel):
    machine_type: MachineType
    units: Literal["mm", "inch"] = "mm"
    work_coordinate_system: str = "G54"
    safe_z: float = 10.0
    material: str | None = None  # optional workpiece material (name or library ID)
    tools: list[ToolSpec] = []
    operations: list[Operation] = []
    assumptions: list[str] = []
    warnings: list[str] = []
    missing_info: list[str] = Field(default_factory=list)
