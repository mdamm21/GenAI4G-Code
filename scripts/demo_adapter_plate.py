"""Demo: Adapterplatte mit Tasche + Nut — deterministisch, kein API-Key.

Teil: Aluminiumplatte mit:
  - 60x35mm Tasche, 12mm tief (Komponentenaufnahme)
  - 80mm Nut entlang X, 4mm tief (Kabelführung / Passung)
  - 6mm Fräser, step-down 3mm / 2mm, step-over 2mm
"""

from cnc.tools.milling_tools import (
    generate_milling_pocket_gcode_from_params,
    generate_milling_slot_gcode_from_params,
)

SEP = "-" * 60


def show(label: str, result: dict) -> None:
    print(SEP)
    print(f"  {label}")
    print(SEP)
    print(f"  ok       : {result['ok']}")
    if result.get("errors"):
        print(f"  errors   : {result['errors']}")
    if result.get("warnings"):
        print(f"  warnings : {result['warnings']}")
    if result.get("gcode"):
        lines = result["gcode"].strip().splitlines()
        print(f"  lines    : {len(lines)}")
        print()
        print(result["gcode"])
    print()


# --- Tasche: Komponentenaufnahme 60x35mm, 12mm tief ---
pocket = generate_milling_pocket_gcode_from_params(
    origin_x=0.0,
    origin_y=0.0,
    width=60.0,
    height=35.0,
    depth=12.0,
    tool_diameter=6.0,
    step_down=3.0,
    step_over=2.0,
    safe_z=8.0,
    feedrate=200.0,
    spindle_speed=8000.0,
    units="mm",
    work_coordinate_system="G54",
    material="6061 aluminium",
    postprocessor="fanuc",
)
show("TASCHE — 60x35mm, 12mm tief, step-down 3mm, step-over 2mm", pocket)

# --- Nut: Kabelführung 80mm entlang X, 4mm tief ---
slot = generate_milling_slot_gcode_from_params(
    start_x=0.0,
    start_y=-30.0,
    length=80.0,
    depth=4.0,
    tool_diameter=6.0,
    safe_z=8.0,
    feedrate=200.0,
    spindle_speed=8000.0,
    direction="x",
    step_down=2.0,
    units="mm",
    work_coordinate_system="G54",
    material="6061 aluminium",
    postprocessor="fanuc",
)
show("NUT — 80mm entlang X bei Y-30, 4mm tief, step-down 2mm", slot)
