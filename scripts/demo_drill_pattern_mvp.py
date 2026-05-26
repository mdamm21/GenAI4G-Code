"""Demo — multi-hole drill pattern with machine profile.

Shows the deterministic pipeline:
    explicit holes + machine_profile -> OperationPlan -> validate -> G-code

No LLM or API key required.

Usage:
    python scripts/demo_drill_pattern_mvp.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cnc.tools.machine_profiles import list_machine_profiles, get_machine_profile
from cnc.tools.drill_tools import generate_drill_pattern_gcode_from_params


def _hr(title: str = "") -> None:
    if title:
        print(f"\n{'-' * 64}")
        print(f"  {title}")
        print(f"{'-' * 64}")
    else:
        print(f"{'-' * 64}")


def _run_case(label: str, **kwargs) -> None:
    _hr(label)

    holes = kwargs.get("holes", [])
    print(f"  Holes ({len(holes)} total):")
    for i, h in enumerate(holes):
        print(f"    [{i}]  X{h.get('x', '?')}  Y{h.get('y', '?')}  depth={h.get('depth', '?')}")

    print("  Parameters:")
    for k, v in kwargs.items():
        if k == "holes":
            continue
        print(f"    {k:<25} = {v}")

    result = generate_drill_pattern_gcode_from_params(**kwargs)

    status = "OK" if result["ok"] else "FAILED"
    print(f"\n  Result       : {status}")
    print(f"  Postprocessor: {result.get('postprocessor')}")
    print(f"  Profile used : {result.get('machine_profile')}")

    if result.get("errors"):
        for e in result["errors"]:
            print(f"    [ERROR]   {e}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"    [WARN]    {w}")

    val = result.get("validation", {})
    print(f"  G-code valid : {val.get('ok', '?')}")
    if val.get("warnings"):
        for w in val["warnings"]:
            print(f"    [GCODE]   {w}")

    plan = result.get("operation_plan", {})
    print(f"  safe_z       : {plan.get('safe_z')}")
    print(f"  ops in plan  : {len(plan.get('operations', []))}")

    gcode = result.get("gcode") or ""
    if gcode:
        print("\n  --- G-CODE ---")
        print(gcode)
        print("  --- END ---")
    else:
        print("\n  [No G-code generated]")


def main() -> int:
    print("\n" + "=" * 64)
    print("  GENAI4G-CODE - Multi-Hole Drill Pattern Demo")
    print("  Deterministic pipeline - no LLM or API key required")
    print("=" * 64)

    # --- Show available profiles ---
    _hr("Available Machine Profiles")
    for p in list_machine_profiles():
        print(f"  {p['name']}")
        print(f"    machine_type : {p['machine_type']}")
        print(f"    units        : {p['units']}")
        print(f"    default_safe_z: {p['default_safe_z']}")
        print(f"    default_feedrate: {p['default_feedrate']}")
        print(f"    default_spindle_speed: {p['default_spindle_speed']}")
        for note in p.get("notes", []):
            print(f"    NOTE: {note}")
        print()

    # Case 1: 3-hole pattern, generic_drill_mm profile, feedrate+spindle explicit
    _run_case(
        "Case 1: 3-hole pattern, generic_drill_mm profile",
        holes=[
            {"x": 0, "y": 0, "depth": 5},
            {"x": 10, "y": 0, "depth": 5},
            {"x": 10, "y": 10, "depth": 8},
        ],
        tool_diameter=5,
        feedrate=100,
        spindle_speed=1200,
        machine_profile="generic_drill_mm",
        material="6061 aluminium",
    )

    # Case 2: inch profile, 2 holes, GRBL postprocessor
    _run_case(
        "Case 2: 2-hole pattern, generic_drill_inch, GRBL",
        holes=[
            {"x": 0, "y": 0, "depth": 0.5},
            {"x": 1.0, "y": 0, "depth": 0.75},
        ],
        tool_diameter=0.25,
        feedrate=5,
        spindle_speed=3000,
        machine_profile="generic_drill_inch",
        postprocessor="grbl",
        material="mild steel",
    )

    # Case 3: negative depth — normalisation and warning
    _run_case(
        "Case 3: Mixed positive/negative depths",
        holes=[
            {"x": 0, "y": 0, "depth": 10},
            {"x": 20, "y": 0, "depth": -6},
        ],
        tool_diameter=6,
        safe_z=5,
        feedrate=120,
        spindle_speed=1500,
        material="brass",
    )

    # Case 4: missing feedrate — should fail with errors
    _run_case(
        "Case 4: Missing feedrate (should fail validation)",
        holes=[
            {"x": 0, "y": 0, "depth": 5},
            {"x": 10, "y": 0, "depth": 5},
        ],
        tool_diameter=5,
        safe_z=5,
        feedrate=None,
        spindle_speed=1200,
    )

    print("\n" + "=" * 64)
    print("  SAFETY NOTE:")
    print("  Generated G-code is for review and simulation only.")
    print("  Never run on a real machine without expert verification,")
    print("  simulation, and machine-specific setup validation.")
    print("=" * 64 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
