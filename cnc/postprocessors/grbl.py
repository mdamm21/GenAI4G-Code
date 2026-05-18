"""GRBL postprocessor stub — GRBL-compatible G-code output."""

# TODO: Implement GRBL-specific output (no tool change commands, no O-number, etc.)


def generate_gcode_from_operations(operation_plan: dict) -> str:
    """Convert operation plan to GRBL-compatible G-code.

    GRBL differences from Fanuc:
    - No O-number program identifier
    - No M06 tool change (manual tool changes only)
    - Limited canned cycles
    - Feed rate in mm/min only
    """
    raise NotImplementedError(
        "GRBL postprocessor is not yet implemented. "
        "Use 'fanuc' postprocessor as a starting point and adapt for GRBL."
    )
