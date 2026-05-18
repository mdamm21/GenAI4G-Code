"""JobSpec schema — neutral manufacturing job description."""

from typing import Literal
from pydantic import BaseModel

MachineType = Literal["mill", "lathe", "grinder", "drill", "3d_printer", "laser"]


class JobSpec(BaseModel):
    machine_type: MachineType | None = None
    units: Literal["mm", "inch"] = "mm"
    material: str | None = None
    raw_stock: str | None = None
    description: str
    assumptions: list[str] = []
    missing_info: list[str] = []
