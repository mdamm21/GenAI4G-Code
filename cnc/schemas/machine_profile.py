"""Machine profile schema — lightweight defaults container for CNC machine configurations.

A MachineProfile supplies safe defaults for a known machine setup.
It does NOT guarantee safety — critical parameters (feedrate, spindle speed)
that are None in the profile must be provided explicitly per job.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MachineProfile(BaseModel):
    """Defaults for a specific CNC machine configuration.

    All numeric defaults are Optional — None means "must be specified per job".
    Profiles never silently invent safety-critical values.
    """

    name: str
    machine_type: Literal["drill", "mill", "lathe", "grinder", "3d_printer", "laser"]
    units: Literal["mm", "inch"] = "mm"
    work_coordinate_system: str = "G54"
    default_safe_z: float | None = None
    default_feedrate: float | None = None
    default_spindle_speed: float | None = None
    default_postprocessor: str = "fanuc"
    notes: list[str] = Field(default_factory=list)
