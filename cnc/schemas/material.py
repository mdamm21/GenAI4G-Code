"""Material schema — structured representation of workpiece material context.

MaterialSpec is informational only. It carries notes and warnings about
machining considerations. It does NOT contain cutting data (feedrate,
spindle speed, step_down, step_over) — those must always be supplied
explicitly by the operator or CAM programmer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MaterialSpec(BaseModel):
    """Informational material descriptor.

    Attributes:
        id:                   Machine-readable identifier, e.g. "aluminum_6061".
        name:                 Human-readable name, e.g. "Aluminum 6061".
        category:             Broad material family.
        machinability:        Qualitative machining difficulty.
        notes:                General machining notes (informational only).
        warnings:             Caution notices shown alongside the plan.
        supported_operations: Operation types this material is typically used for.
        metadata:             Arbitrary additional context (not used by the pipeline).
    """

    id: str
    name: str
    category: Literal[
        "aluminum",
        "steel",
        "stainless_steel",
        "brass",
        "plastic",
        "wood",
        "composite",
        "unknown",
    ] = "unknown"
    machinability: Literal[
        "easy",
        "medium",
        "hard",
        "unknown",
    ] = "unknown"
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supported_operations: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
