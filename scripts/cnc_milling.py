"""CNC Milling script — wrapper around the structured pipeline.

This script provides a CLI and programmatic interface for CNC milling G-code generation.
It delegates to the CNC pipeline (agent -> subagent -> postprocessor -> validator).

Usage (CLI):
    python scripts/cnc_milling.py "Mill a 50x50mm pocket 10mm deep in 6061 aluminium"

Usage (import):
    from scripts.cnc_milling import generate_milling_gcode
    result = generate_milling_gcode(operation_plan)
"""

from __future__ import annotations

import json
import sys
from typing import Any


def generate_milling_gcode(operation_plan: dict) -> str:
    """Generate Fanuc-compatible milling G-code from a structured operation plan.

    This function wraps the Fanuc postprocessor and validates the output.

    Args:
        operation_plan: Structured dict following the OperationPlan schema.
                        Must include machine_type, units, safe_z, tools, operations.

    Returns:
        G-code string (Fanuc-compatible).

    Raises:
        ValueError: If the operation plan is invalid or produces unsafe G-code.

    TODO: If you have a previous milling script with custom logic, integrate it here
          or call it from this wrapper rather than replacing it.
    """
    from cnc.postprocessors.fanuc import generate_gcode_from_operations
    from cnc.tools.validation_tools import validate_operation_plan
    from cnc.validators.gcode_validator import validate_gcode_text

    # Validate the operation plan before postprocessing
    plan_validation = validate_operation_plan(operation_plan)
    if not plan_validation.get("ok"):
        errors = plan_validation.get("errors", [])
        raise ValueError(f"Invalid operation plan: {'; '.join(errors)}")

    # Generate G-code
    gcode = generate_gcode_from_operations(operation_plan)

    # Validate generated G-code
    machine_type = operation_plan.get("machine_type", "mill")
    gcode_validation = validate_gcode_text(gcode, machine_type=machine_type)
    if not gcode_validation.get("ok"):
        errors = gcode_validation.get("errors", [])
        raise ValueError(f"Generated G-code failed validation: {'; '.join(errors)}")

    return gcode


def run_from_prompt(prompt: str) -> dict[str, Any]:
    """Run the full CNC agent pipeline from a natural language prompt.

    Args:
        prompt: Natural language manufacturing request.

    Returns:
        Structured result dict (gcode, operation_plan, assumptions, warnings, validation).
    """
    from cnc.agent import build_cnc_agent

    agent = build_cnc_agent()
    return agent.run(prompt)


def _print_result(result: dict[str, Any]) -> None:
    """Pretty-print a CNC pipeline result."""
    print("\n" + "=" * 60)
    print("CNC GENERATION RESULT")
    print("=" * 60)

    machine = result.get("machine_type") or "unknown"
    print(f"Machine type : {machine}")

    validation = result.get("validation", {})
    ok = validation.get("ok", False)
    print(f"Validation   : {'OK' if ok else 'FAILED'}")

    errors = validation.get("errors", [])
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  [ERROR] {e}")

    warnings = result.get("warnings", []) + validation.get("warnings", [])
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  [WARN]  {w}")

    assumptions = result.get("assumptions", [])
    if assumptions:
        print("Assumptions:")
        for a in assumptions:
            print(f"  [INFO]  {a}")

    missing = result.get("missing_info", [])
    if missing:
        print("Missing info:")
        for m in missing:
            print(f"  [MISS]  {m}")

    gcode = result.get("gcode", "")
    if gcode:
        print("\n--- G-CODE ---")
        print(gcode)
    else:
        print("\n[No G-code generated]")

    op_plan = result.get("operation_plan")
    if op_plan:
        print("\n--- OPERATION PLAN ---")
        print(json.dumps(op_plan, indent=2))

    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/cnc_milling.py \"<manufacturing prompt>\"")
        print("Example: python scripts/cnc_milling.py \"Mill a 50x50mm pocket 10mm deep\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"Prompt: {prompt}")

    try:
        result = run_from_prompt(prompt)
        _print_result(result)
    except RuntimeError as exc:
        print(f"[ERROR] Agent not available: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
