"""Demo for the typed generate_drill_gcode MCP tool — no LLM or API key needed.

Shows the full deterministic pipeline:
    explicit parameters -> OperationPlan -> validate -> postprocess -> G-code

Usage:
    python scripts/demo_drill_mcp_tool.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cnc.tools.drill_tools import generate_drill_gcode_from_params


def _hr(title: str = "") -> None:
    if title:
        print(f"\n{'-' * 62}")
        print(f"  {title}")
        print(f"{'-' * 62}")
    else:
        print(f"{'-' * 62}")


def _run_case(label: str, **kwargs) -> None:
    _hr(label)
    print("  Parameters:")
    for k, v in kwargs.items():
        print(f"    {k:<25} = {v}")

    result = generate_drill_gcode_from_params(**kwargs)

    status = "OK" if result["ok"] else "FAILED"
    print(f"\n  Result     : {status}")
    print(f"  Postprocessor: {result.get('postprocessor')}")

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
        print(f"  Hole pos     : X{p.get('x')}  Y{p.get('y')}  Z{p.get('z')}")

    gcode = result.get("gcode") or ""
    if gcode:
        print("\n  --- G-CODE ---")
        print(gcode)
        print("  --- END ---")
    else:
        print("\n  [No G-code generated]")


def main() -> int:
    print("\n" + "=" * 62)
    print("  GENAI4G-CODE — generate_drill_gcode MCP Tool Demo")
    print("  Deterministic pipeline — no LLM or API key required")
    print("=" * 62)

    # Case 1: Simple metric hole, aluminium, Fanuc
    _run_case(
        "Case 1: 8mm hole in aluminium — Fanuc",
        x=0.0,
        y=0.0,
        depth=20.0,
        tool_diameter=8.0,
        safe_z=5.0,
        feedrate=150.0,
        spindle_speed=2000.0,
        units="mm",
        work_coordinate_system="G54",
        material="6061 aluminium",
        postprocessor="fanuc",
    )

    # Case 2: Off-center hole, steel, GRBL postprocessor
    _run_case(
        "Case 2: 5mm hole in steel, offset position — GRBL",
        x=25.0,
        y=-15.0,
        depth=12.0,
        tool_diameter=5.0,
        safe_z=3.0,
        feedrate=80.0,
        spindle_speed=1400.0,
        units="mm",
        work_coordinate_system="G55",
        material="mild steel S235",
        postprocessor="grbl",
    )

    # Case 3: No spindle speed — safe handling
    _run_case(
        "Case 3: No spindle_speed specified — safety warning",
        x=10.0,
        y=10.0,
        depth=5.0,
        tool_diameter=4.0,
        safe_z=5.0,
        feedrate=100.0,
        spindle_speed=None,
        material=None,
        postprocessor="fanuc",
    )

    # Case 4: Negative depth input — normalisation
    _run_case(
        "Case 4: Negative depth input (depth=-8) — normalised",
        x=0.0,
        y=0.0,
        depth=-8.0,
        tool_diameter=6.0,
        safe_z=5.0,
        feedrate=120.0,
        spindle_speed=1800.0,
        material="brass",
        postprocessor="fanuc",
    )

    print("\n" + "=" * 62)
    print("  SAFETY NOTE:")
    print("  Generated G-code is for review and simulation only.")
    print("  Never run on a real machine without expert verification,")
    print("  simulation, and machine-specific setup validation.")
    print("=" * 62 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
