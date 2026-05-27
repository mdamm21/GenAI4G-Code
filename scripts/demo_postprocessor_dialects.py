"""Demo: Postprocessor Dialects v0 — Fanuc, GRBL, LinuxCNC, Marlin.

Runs without any API key or LLM. Shows how the same drill plan is
translated to each dialect by the deterministic postprocessor pipeline.
"""

from cnc.tools.postprocess_tools import postprocess_operations

SEPARATOR = "-" * 60


def make_drill_plan() -> dict:
    return {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5.0,
        "tools": [
            {
                "tool_number": 1,
                "description": "5mm HSS drill",
                "diameter": 5,
            }
        ],
        "operations": [
            {
                "type": "drill",
                "name": "centre hole",
                "tool_number": 1,
                "feedrate": 100,
                "spindle_speed": 1200,
                "parameters": {"x": 0.0, "y": 0.0, "z": -5.0},
            }
        ],
        "assumptions": [],
        "warnings": [],
    }


def run_demo(plan: dict, postprocessor: str) -> None:
    print(SEPARATOR)
    print(f"  POSTPROCESSOR: {postprocessor.upper()}")
    print(SEPARATOR)
    result = postprocess_operations(plan, postprocessor=postprocessor)
    print(f"  ok       : {result['ok']}")
    if result["warnings"]:
        print(f"  warnings : {result['warnings']}")
    if result["errors"]:
        print(f"  errors   : {result['errors']}")
    print()
    if result.get("gcode"):
        print(result["gcode"])
    else:
        print("  (no G-code generated)")
    print()


if __name__ == "__main__":
    plan = make_drill_plan()

    # Fanuc — reference postprocessor
    run_demo(plan, "fanuc")

    # GRBL — conservative hobbyist CNC output
    run_demo(plan, "grbl")

    # LinuxCNC — conservative RS274NGC output
    run_demo(plan, "linuxcnc")

    # Marlin — stub / unsupported for CNC drilling
    print(SEPARATOR)
    print("  POSTPROCESSOR: MARLIN (expected: unsupported for machine_type 'drill')")
    print(SEPARATOR)
    result = postprocess_operations(plan, postprocessor="marlin")
    print(f"  ok     : {result['ok']}")
    print(f"  errors : {result['errors']}")
    print()
