"""Demo: Milling Pocket MVP — generate_milling_pocket_gcode_from_params.

Run: python -m scripts.demo_milling_pocket_mvp
"""

from cnc.tools.milling_tools import generate_milling_pocket_gcode_from_params

SEPARATOR = "-" * 60


def show(title: str, result: dict) -> None:
    print(f"\n{SEPARATOR}")
    print(f"CASE: {title}")
    print(SEPARATOR)
    print(f"ok            : {result['ok']}")
    print(f"machine_type  : {result.get('machine_type', '-')}")
    print(f"postprocessor : {result.get('postprocessor', '-')}")
    print(f"machine_profile: {result.get('machine_profile', '-')}")
    if result.get("warnings"):
        print(f"warnings      : {result['warnings']}")
    if result.get("errors"):
        print(f"errors        : {result['errors']}")
    if result.get("gcode"):
        print("\n--- G-code ---")
        print(result["gcode"])
    print(SEPARATOR)


# --- Case 1: Pocket, depth=3, step_down=1, step_over=2 -> 3 Z passes -------
r1 = generate_milling_pocket_gcode_from_params(
    origin_x=0.0, origin_y=0.0,
    width=20.0, height=10.0,
    depth=3.0, tool_diameter=5.0,
    step_down=1.0, step_over=2.0,
    safe_z=5.0, feedrate=150.0, spindle_speed=3000.0,
)
show("Pocket 20x10mm, depth=3, step_down=1, step_over=2 -> 3 Z passes", r1)

# --- Case 2: step_down > depth -> single Z pass with warning ----------------
r2 = generate_milling_pocket_gcode_from_params(
    origin_x=5.0, origin_y=5.0,
    width=30.0, height=15.0,
    depth=2.0, tool_diameter=6.0,
    step_down=10.0, step_over=3.0,
    safe_z=5.0, feedrate=120.0, spindle_speed=2500.0,
)
show("step_down=10 > depth=2 -> single Z pass + warning", r2)

# --- Case 3: Machine profile supplies safe_z --------------------------------
r3 = generate_milling_pocket_gcode_from_params(
    origin_x=0.0, origin_y=0.0,
    width=15.0, height=8.0,
    depth=1.5, tool_diameter=4.0,
    step_down=0.5, step_over=1.5,
    safe_z=None,
    feedrate=100.0, spindle_speed=4000.0,
    machine_profile="generic_mill_mm",
)
show("Machine profile 'generic_mill_mm' supplies safe_z=5.0", r3)

# --- Case 4: Missing step_down -> error, no G-code --------------------------
r4 = generate_milling_pocket_gcode_from_params(
    origin_x=0.0, origin_y=0.0,
    width=20.0, height=10.0,
    depth=3.0, tool_diameter=5.0,
    step_down=None, step_over=2.0,
    safe_z=5.0, feedrate=150.0, spindle_speed=3000.0,
)
show("Missing step_down -> ok=False, gcode=''", r4)

# --- Case 5: step_over > tool_diameter -> warning, still ok -----------------
r5 = generate_milling_pocket_gcode_from_params(
    origin_x=0.0, origin_y=0.0,
    width=20.0, height=10.0,
    depth=3.0, tool_diameter=5.0,
    step_down=1.0, step_over=8.0,
    safe_z=5.0, feedrate=150.0, spindle_speed=3000.0,
)
show("step_over=8 > tool_diameter=5 -> warning but ok=True", r5)
