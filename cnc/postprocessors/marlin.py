"""Marlin postprocessor — stub/unsupported for CNC milling and drilling.

Marlin is a firmware for laser engravers and 3D printers.
CNC milling and drilling operations are not supported.

For 3D printing: the postprocessor is not implemented yet — use a slicer instead.
For laser:       use the GRBL postprocessor with laser mode or a dedicated laser slicer.

This module returns a clear stub message and never generates machine motion G-code
for CNC mill or drill operations.
"""

from __future__ import annotations


def generate_gcode_from_operations(operation_plan: dict) -> str:
    """Return a stub message. No machine motion is generated.

    Args:
        operation_plan: Structured operation plan dict (ignored — no motion generated).

    Returns:
        A comment-only string explaining the limitation.
    """
    machine_type = operation_plan.get("machine_type", "")
    if machine_type == "3d_printer":
        return (
            "; Marlin 3D-printing postprocessor is not implemented yet.\n"
            "; No machine motion generated.\n"
            "; Use a slicer (e.g. PrusaSlicer, Cura) to generate 3D printing G-code."
        )
    return (
        f"; Marlin postprocessor is not supported for machine_type: {machine_type!r}\n"
        "; No machine motion generated.\n"
        "; For CNC milling/drilling use: fanuc, grbl, or linuxcnc postprocessor."
    )
