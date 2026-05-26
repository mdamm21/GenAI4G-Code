"""Drill MVP deterministic demo — runs WITHOUT an LLM or API key.

Demonstrates the full deterministic pipeline:
    normalize_operation_plan → validate_operation_plan → postprocess_operations

Usage:
    python scripts/demo_drill_mvp.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cnc.tools.operation_plan_tools import normalize_operation_plan
from cnc.tools.validation_tools import validate_operation_plan
from cnc.tools.postprocess_tools import postprocess_operations

# ---------------------------------------------------------------------------
# Demo plan (uses "agent output" field names — tool_id, feedrate, spindle_speed)
# ---------------------------------------------------------------------------

DEMO_PLAN = {
    "machine_type": "drill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5,
    "tools": [
        {
            "id": "T1",
            "name": "5mm HSS twist drill",
            "diameter": 5,
            "units": "mm",
            "spindle_speed": 1200,
            "feedrate": 100,
        }
    ],
    "operations": [
        {
            "type": "drill",
            "description": "Drill 5mm deep hole at X0 Y0",
            "tool_id": "T1",
            "parameters": {"x": 0, "y": 0, "z": -5},
            "feedrate": 100,
            "spindle_speed": 1200,
        }
    ],
    "assumptions": [
        "Material: aluminium (assumed if not specified)",
        "G54 work offset assumed",
    ],
    "warnings": [],
}


def _hr(title: str = "") -> None:
    if title:
        print(f"\n{'-' * 60}")
        print(f"  {title}")
        print("-" * 60)
    else:
        print("-" * 60)


def main() -> int:
    print("\n" + "=" * 60)
    print("  GENAI4G-CODE — Drill MVP Deterministic Demo")
    print("  (no LLM / API key required)")
    print("=" * 60)

    # --- Step 1: normalize ---
    _hr("Step 1: normalize_operation_plan")
    normalized = normalize_operation_plan(DEMO_PLAN)
    print("  Input tool fields:  id, name, diameter, spindle_speed, feedrate")
    print("  After normalize:    tool_number, description, diameter_mm, spindle_rpm, feedrate_mmpm")
    t = normalized["tools"][0] if normalized["tools"] else {}
    op = normalized["operations"][0] if normalized["operations"] else {}
    print(f"  tool_number  : {t.get('tool_number')}")
    print(f"  diameter_mm  : {t.get('diameter_mm')}")
    print(f"  feedrate_mmpm: {op.get('feedrate_mmpm')}")
    print(f"  spindle_rpm  : {op.get('spindle_rpm')}")

    # --- Step 2: validate ---
    _hr("Step 2: validate_operation_plan")
    val = validate_operation_plan(normalized)
    status = "OK" if val["ok"] else "FAILED"
    print(f"  Validation : {status}")
    if val["errors"]:
        for e in val["errors"]:
            print(f"    [ERROR]   {e}")
    if val["warnings"]:
        for w in val["warnings"]:
            print(f"    [WARN]    {w}")
    if not val["errors"] and not val["warnings"]:
        print("    No errors or warnings.")

    if not val["ok"]:
        print("\n  [STOPPED] Validation failed — postprocessing skipped.")
        return 1

    # --- Step 3: postprocess ---
    _hr("Step 3: postprocess_operations (fanuc)")
    result = postprocess_operations(normalized, postprocessor="fanuc")
    pp_status = "OK" if result["ok"] else "FAILED"
    print(f"  Result     : {pp_status}")
    print(f"  Postprocessor: {result.get('postprocessor')}")
    if result.get("errors"):
        for e in result["errors"]:
            print(f"    [ERROR]   {e}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"    [WARN]    {w}")
    val2 = result.get("validation", {})
    print(f"  G-code valid : {val2.get('ok', '?')}")
    if val2.get("warnings"):
        for w in val2["warnings"]:
            print(f"    [GCODE WARN] {w}")

    # --- G-Code output ---
    gcode = result.get("gcode") or ""
    if gcode:
        _hr("Generated G-Code")
        print(gcode)
        _hr()
        print("\n  SAFETY NOTE: This G-code is for review and simulation only.")
        print("  Never run on a real machine without expert verification,")
        print("  simulation, and machine-specific setup validation.")
    else:
        print("\n  [No G-code generated]")

    print()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
