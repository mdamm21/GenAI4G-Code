"""LinuxCNC postprocessor stub — LinuxCNC (EMC2) compatible G-code output."""

# TODO: Implement LinuxCNC-specific output (RS274NGC dialect)


def generate_gcode_from_operations(operation_plan: dict) -> str:
    """Convert operation plan to LinuxCNC-compatible G-code.

    LinuxCNC differences:
    - RS274NGC dialect
    - Subroutines with o-words (o100 sub / o100 endsub)
    - Named parameters (#<param_name>)
    - Tool table integration
    """
    raise NotImplementedError(
        "LinuxCNC postprocessor is not yet implemented. "
        "LinuxCNC uses RS274NGC G-code dialect."
    )
