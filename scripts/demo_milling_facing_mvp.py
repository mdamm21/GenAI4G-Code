"""Demo — milling facing MVP.

Shows the deterministic facing pipeline:
    explicit parameters + machine_profile -> OperationPlan -> validate -> G-code

No LLM or API key required.

Usage:
    python scripts/demo_milling_facing_mvp.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cnc.tools.milling_tools import generate_milling_facing_gcode_from_params


def _hr(title: str = "") -> None:
    if title:
        print(f"\n{'-' * 64}")
        print(f"  {title}")
        print(f"{'-' * 64}")
    else:
        print(f"{'-' * 64}")


def _run_case(label: str, **kwargs) -> None:
    _hr(label)
    print("  Parameters:")
    for k, v in kwargs.items():
        print(f"    {k:<30} = {v}")

    result = generate_milling_facing_gcode_from_params(**kwargs)

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
    ops = plan.get("operations", [])
    if ops:
        p = ops[0].get("parameters", {})
        print(f"  target_z     : {p.get('target_z')}")
        print(f"  area         : {p.get('width')}x{p.get('height')} at "
              f"X{p.get('origin_x')} Y{p.get('origin_y')}")
        print(f"  step_over    : {p.get('step_over')}")

    gcode = result.get("gcode") or ""
    if gcode:
        print("\n  --- G-CODE ---")
        print(gcode)
        print("  --- END ---")
    else:
        print("\n  [No G-code generated]")


def main() -> int:
    print("\n" + "=" * 64)
    print("  GENAI4G-CODE - Milling Facing MVP Demo")
    print("  Deterministic pipeline - no LLM or API key required")
    print("=" * 64)

    # Case 1: standard 20x10mm face pass, 1mm depth, generic_mill_mm profile
    _run_case(
        "Case 1: 20x10mm face pass — generic_mill_mm profile",
        origin_x=0.0,
        origin_y=0.0,
        width=20.0,
        height=10.0,
        depth=1.0,
        step_over=2.0,
        tool_diameter=5.0,
        feedrate=150.0,
        spindle_speed=3000.0,
        machine_profile="generic_mill_mm",
        material="6061 aluminium",
    )

    # Case 2: off-centre origin, coarser stepover
    _run_case(
        "Case 2: 50x30mm face pass with offset origin",
        origin_x=10.0,
        origin_y=5.0,
        width=50.0,
        height=30.0,
        depth=0.5,
        step_over=8.0,
        tool_diameter=10.0,
        safe_z=5.0,
        feedrate=400.0,
        spindle_speed=8000.0,
        material="mild steel S235",
    )

    # Case 3: negative depth input — normalisation
    _run_case(
        "Case 3: Negative depth input — normalised",
        origin_x=0.0,
        origin_y=0.0,
        width=20.0,
        height=10.0,
        depth=-2.0,
        step_over=3.0,
        tool_diameter=6.0,
        safe_z=5.0,
        feedrate=200.0,
        spindle_speed=4000.0,
        material="brass",
    )

    # Case 4: missing feedrate — should fail
    _run_case(
        "Case 4: Missing feedrate (should fail validation)",
        origin_x=0.0,
        origin_y=0.0,
        width=20.0,
        height=10.0,
        depth=1.0,
        step_over=2.0,
        tool_diameter=5.0,
        safe_z=5.0,
        feedrate=None,
        spindle_speed=3000.0,
    )

    print("\n" + "=" * 64)
    print("  SAFETY NOTE:")
    print("  Generated G-code is for review and simulation only.")
    print("  No cutter compensation is applied.")
    print("  Never run on a real machine without expert verification,")
    print("  simulation, and machine-specific setup validation.")
    print("=" * 64 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
