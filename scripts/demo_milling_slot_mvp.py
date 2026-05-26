"""Demo: Milling Slot MVP — generate_milling_slot_gcode_from_params.

Run: python scripts/demo_milling_slot_mvp.py
"""

from cnc.tools.milling_tools import generate_milling_slot_gcode_from_params

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


# --- Case 1: Slot along X, 3 passes (depth=3, step_down=1) ------------------
r1 = generate_milling_slot_gcode_from_params(
    start_x=0.0, start_y=0.0,
    length=20.0, depth=3.0,
    tool_diameter=5.0, safe_z=5.0,
    feedrate=150.0, spindle_speed=3000.0,
    direction="x", step_down=1.0,
)
show("Slot along X, depth=3, step_down=1 -> 3 passes", r1)

# --- Case 2: Slot along Y, single pass (step_down > depth) ------------------
r2 = generate_milling_slot_gcode_from_params(
    start_x=10.0, start_y=5.0,
    length=30.0, depth=2.0,
    tool_diameter=6.0, safe_z=5.0,
    feedrate=120.0, spindle_speed=2500.0,
    direction="y", step_down=10.0,
)
show("Slot along Y, step_down=10 > depth=2 -> single pass + warning", r2)

# --- Case 3: Machine profile supplies safe_z --------------------------------
r3 = generate_milling_slot_gcode_from_params(
    start_x=0.0, start_y=0.0,
    length=15.0, depth=1.5,
    tool_diameter=4.0,
    safe_z=None,
    feedrate=100.0, spindle_speed=4000.0,
    direction="x", step_down=0.5,
    machine_profile="generic_mill_mm",
)
show("Machine profile 'generic_mill_mm' supplies safe_z=5.0", r3)

# --- Case 4: Missing step_down -> error, no G-code --------------------------
r4 = generate_milling_slot_gcode_from_params(
    start_x=0.0, start_y=0.0,
    length=20.0, depth=3.0,
    tool_diameter=5.0, safe_z=5.0,
    feedrate=150.0, spindle_speed=3000.0,
    direction="x", step_down=None,
)
show("Missing step_down -> ok=False, gcode=''", r4)
