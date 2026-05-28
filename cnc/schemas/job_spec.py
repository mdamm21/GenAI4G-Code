"""JobSpec schema — neutral manufacturing job description."""

from typing import Literal
from pydantic import BaseModel, Field

MachineType = Literal["mill", "lathe", "grinder", "drill", "3d_printer", "laser"]


class JobSpec(BaseModel):
    machine_type: MachineType | None = None
    units: Literal["mm", "inch"] = "mm"
    material: str | None = None
    raw_stock: str | None = None
    description: str
    assumptions: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)


class CNCJobSpec(BaseModel):
    """Reproducible JSON container for a CNC job.

    Bundles OperationPlan, machine_profile, material, tool_ids,
    postprocessor, and metadata into a single serialisable record.
    G-code is never stored — it is always regenerated deterministically
    from ``operation_plan``.
    """

    schema_version: str = "0.1"
    job_id: str | None = None
    name: str | None = None
    description: str | None = None

    machine_type: MachineType | None = None
    machine_profile: str | None = None
    postprocessor: str = "fanuc"

    material: str | None = None
    tool_ids: list[str] = Field(default_factory=list)

    # operation_plan stays as plain dict so all existing tools work without
    # conversion to/from the Pydantic OperationPlan model.
    operation_plan: dict | None = None

    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
