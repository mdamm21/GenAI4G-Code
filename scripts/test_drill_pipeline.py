"""Deterministic end-to-end test for the Drill MVP pipeline.

Runs WITHOUT an LLM / API key. Tests the following stages:
    1. normalize_operation_plan — field-name normalization
    2. validate_operation_plan  — structural validation
    3. postprocess_operations   — G-code generation + G-code validation

Usage:
    python scripts/test_drill_pipeline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make sure the repo root is on the path when run directly
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cnc.tools.operation_plan_tools import normalize_operation_plan
from cnc.tools.validation_tools import validate_operation_plan
from cnc.tools.postprocess_tools import postprocess_operations


# ---------------------------------------------------------------------------
# Test plan (uses "new format" field names from the drilling agent)
# ---------------------------------------------------------------------------

RAW_PLAN = {
    "machine_type": "drill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5,
    "tools": [
        {
            "id": "T1",
            "name": "5mm drill",
            "diameter": 5,
            "units": "mm",
            "spindle_speed": 1200,
            "feedrate": 100,
        }
    ],
    "operations": [
        {
            "type": "drill",
            "description": "Drill one 5mm deep hole at X0 Y0",
            "tool_id": "T1",
            "parameters": {
                "x": 0,
                "y": 0,
                "z": -5,
            },
            "feedrate": 100,
            "spindle_speed": 1200,
        }
    ],
    "assumptions": [],
    "warnings": [],
}


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def _ok(label: str, value: object) -> None:
    icon = "[OK]  " if value else "[FAIL]"
    print(f"  {icon} {label}")


def main() -> int:
    """Run the deterministic drill pipeline test. Returns 0 on success, 1 on failure."""
    failed = False

    # ------------------------------------------------------------------
    # Stage 1: normalize_operation_plan
    # ------------------------------------------------------------------
    _section("Stage 1: normalize_operation_plan")
    normalized = normalize_operation_plan(RAW_PLAN)

    has_tool_number = any(
        t.get("tool_number") is not None for t in normalized.get("tools", [])
    )
    has_diameter_mm = any(
        t.get("diameter_mm") is not None for t in normalized.get("tools", [])
    )
    has_feedrate_mmpm = any(
        op.get("feedrate_mmpm") is not None for op in normalized.get("operations", [])
    )
    has_tool_number_op = any(
        op.get("tool_number") is not None for op in normalized.get("operations", [])
    )

    _ok("tool 'id' -> 'tool_number' mapped", has_tool_number)
    _ok("tool 'diameter' -> 'diameter_mm' mapped", has_diameter_mm)
    _ok("op 'feedrate' -> 'feedrate_mmpm' mapped", has_feedrate_mmpm)
    _ok("op 'tool_id' -> 'tool_number' mapped", has_tool_number_op)

    if not all([has_tool_number, has_diameter_mm, has_feedrate_mmpm, has_tool_number_op]):
        failed = True

    print("\n  Normalized plan (tools + operations):")
    print(
        "  tools:     ",
        json.dumps(normalized.get("tools"), indent=None, default=str),
    )
    print(
        "  operations:",
        json.dumps(normalized.get("operations"), indent=None, default=str),
    )

    # ------------------------------------------------------------------
    # Stage 2: validate_operation_plan (using normalized plan)
    # ------------------------------------------------------------------
    _section("Stage 2: validate_operation_plan")
    val = validate_operation_plan(normalized)

    _ok("ok == True", val.get("ok"))
    _ok("no errors", not val.get("errors"))
    print(f"  errors:   {val.get('errors', [])}")
    print(f"  warnings: {val.get('warnings', [])}")

    if not val.get("ok"):
        failed = True
        print("\n  [FAIL] Validation failed — skipping postprocessing.")
        return 1

    # ------------------------------------------------------------------
    # Stage 3: postprocess_operations
    # ------------------------------------------------------------------
    _section("Stage 3: postprocess_operations (fanuc)")
    result = postprocess_operations(normalized, postprocessor="fanuc")

    _ok("ok == True", result.get("ok"))
    _ok("gcode is not empty", bool(result.get("gcode")))

    gcode = result.get("gcode") or ""
    has_g21 = "G21" in gcode
    has_g90 = "G90" in gcode
    has_g54 = "G54" in gcode
    has_safe_z = "Z5.000" in gcode or "Z5.0" in gcode
    has_spindle = "M03" in gcode or "M3" in gcode
    has_drill_move = "G01" in gcode or "G1 " in gcode
    has_m5 = "M05" in gcode or "M5" in gcode
    has_m30 = "M30" in gcode
    has_percent = gcode.startswith("%")

    _ok("starts with %", has_percent)
    _ok("contains G21 (mm units)", has_g21)
    _ok("contains G90 (absolute)", has_g90)
    _ok("contains G54 (WCS)", has_g54)
    _ok("contains safe_z retract (Z5)", has_safe_z)
    _ok("contains spindle start (M03)", has_spindle)
    _ok("contains drill plunge (G01)", has_drill_move)
    _ok("contains spindle stop (M05)", has_m5)
    _ok("contains M30 (program end)", has_m30)

    checks = [
        has_percent, has_g21, has_g90, has_g54,
        has_safe_z, has_drill_move, has_m5, has_m30,
    ]
    if not all(checks):
        failed = True

    print(f"\n  postprocessor: {result.get('postprocessor')}")
    print(f"  errors:        {result.get('errors', [])}")
    print(f"  warnings:      {result.get('warnings', [])}")
    print(f"  gcode_val ok:  {result.get('validation', {}).get('ok')}")

    print("\n--- GENERATED G-CODE ---")
    print(gcode)
    print("--- END G-CODE ---")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _section("Summary")
    if failed:
        print("  [FAIL] One or more checks failed.")
        return 1
    else:
        print("  [OK] All checks passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
