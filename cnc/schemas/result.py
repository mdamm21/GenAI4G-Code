"""Result schemas — output types for G-code generation pipeline."""

from pydantic import BaseModel, Field

from .job_spec import MachineType


class ValidationResult(BaseModel):
    ok: bool
    errors: list[str] = []
    warnings: list[str] = []
    machine_type: str = "mill"


class GCodeResult(BaseModel):
    gcode: str
    operation_plan: dict | None = None
    assumptions: list[str] = []
    warnings: list[str] = []
    errors: list[str] = Field(default_factory=list)
    validation: ValidationResult
    machine_type: MachineType | None = None
