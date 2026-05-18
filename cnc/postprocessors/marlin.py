"""Marlin postprocessor stub — Marlin firmware G-code (3D printing / laser engraving)."""

# TODO: Implement Marlin-specific output (temperature commands, fan control, etc.)


def generate_gcode_from_operations(operation_plan: dict) -> str:
    """Convert operation plan to Marlin-compatible G-code.

    Marlin differences:
    - M104/M109 for hotend temperature
    - M140/M190 for bed temperature
    - M106/M107 for fan control
    - G28 home
    - Laser power via M3/M5 (S parameter = power 0-255)
    """
    raise NotImplementedError(
        "Marlin postprocessor is not yet implemented. "
        "Marlin is used for 3D printers and laser engravers."
    )
