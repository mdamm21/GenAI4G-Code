"""Demo: Interactive Warning Resolution — runs without API key.

Simulates the current bolt-circle scenario with:
  - 6 unknown/local tool issues (grouped into 1)
  - Missing material (with prompt inference)
  - Duplicated warnings

Uses injected fake answers to demonstrate the flow non-interactively.
"""

from __future__ import annotations

import json
import sys
import os

# Ensure package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cnc.tools.issue_resolution import collect_interactive_issues, build_issue_choices
from cnc.cli_interaction import resolve_issues_interactively


def _build_demo_result() -> dict:
    """Build a realistic result dict simulating 6-hole bolt circle output."""
    return {
        "machine_type": "drill",
        "gcode": "",
        "ok": True,
        "postprocessor": "fanuc",
        "warnings": [
            "Agent-provided gcode was discarded and regenerated deterministically from operation_plan.",
            "Operation 0 references tool_id='1' which is not in the built-in tool library.",
            "Operation 1 references tool_id='1' which is not in the built-in tool library.",
            "Operation 2 references tool_id='1' which is not in the built-in tool library.",
            "Operation 3 references tool_id='1' which is not in the built-in tool library.",
            "Operation 4 references tool_id='1' which is not in the built-in tool library.",
            "Operation 5 references tool_id='1' which is not in the built-in tool library.",
            "Material was not specified. Specify a material for guardrail checks and documentation.",
        ],
        "errors": [],
        "validation": {
            "ok": True,
            "warnings": [
                "Material was not specified. Specify a material for guardrail checks and documentation.",
            ],
            "errors": [],
        },
        "operation_plan": {
            "machine_type": "drill",
            "units": "mm",
            "work_coordinate_system": "G54",
            "safe_z": 5.0,
            "material": None,
            "tools": [
                {
                    "tool_number": 1,
                    "description": "8.5mm HSS twist drill (M8 clearance hole)",
                    "diameter_mm": 8.5,
                    "type": "drill",
                }
            ],
            "operations": [
                {
                    "name": f"Drill hole {i+1} on bolt circle",
                    "type": "drill",
                    "tool_number": 1,
                    "feedrate_mmpm": 80,
                    "spindle_rpm": 1200,
                    "parameters": {
                        "x": round(40 * __import__("math").cos(__import__("math").radians(i * 60)), 3),
                        "y": round(40 * __import__("math").sin(__import__("math").radians(i * 60)), 3),
                        "z": -18,
                    },
                }
                for i in range(6)
            ],
            "assumptions": [
                "M8 bolt requires 8.5mm clearance hole",
                "Bolt circle diameter: 80mm, radius: 40mm",
            ],
            "warnings": [],
            "missing_info": [],
        },
    }


def main() -> None:
    prompt = "Drill 6 holes on a 80mm bolt circle for M8 bolts, 18mm deep in steel, safe Z 5mm"

    print("=" * 70)
    print("DEMO: Interactive Warning Resolution")
    print("=" * 70)
    print(f"\nPrompt: {prompt}")
    print("-" * 70)

    result = _build_demo_result()

    # --- Phase 1: Show raw issue collection ---
    print("\n[Phase 1] Collecting and deduplicating issues...\n")
    issues = collect_interactive_issues(result, prompt=prompt)

    print(f"  Raw warnings in result: {len(result['warnings'])}")
    print(f"  Deduplicated issues:    {len(issues)}")
    print()

    for issue in issues:
        sev = issue["severity"].upper()
        act = "ACTIONABLE" if issue["actionable"] else "info-only"
        ops = issue["affected_operations"]
        ops_str = f" (ops: {', '.join(str(o) for o in ops)})" if ops else ""
        print(f"  [{sev}] [{act}] {issue['code']}: {issue['message']}{ops_str}")

        # Show choices
        choices = build_issue_choices(issue, result, prompt=prompt)
        if choices:
            for c in choices:
                print(f"         {c['key']}. {c['label']}")

    print()

    # --- Phase 2: Simulate interactive resolution ---
    print("-" * 70)
    print("[Phase 2] Simulating interactive resolution...\n")

    # Fake answers:
    #   "1" = Use mild_steel for material (first actionable issue)
    #   "3" = USE_TRANSIENT_CUSTOM_TOOL for tool issue (second actionable issue)
    #   "1" = continue to G-code (final prompt)
    fake_answers = iter(["1", "3", "1"])

    def fake_input(prompt_text: str) -> str:
        try:
            answer = next(fake_answers)
            print(f"  [SIMULATED INPUT] {prompt_text}{answer}")
            return answer
        except StopIteration:
            return "1"

    result = resolve_issues_interactively(
        result,
        prompt=prompt,
        input_fn=fake_input,
        output_fn=print,
    )

    # --- Phase 3: Show resolution results ---
    print("\n" + "-" * 70)
    print("[Phase 3] Resolution results\n")

    res_log = result.get("resolution_log", [])
    print(f"  Resolution decisions: {len(res_log)}")
    for entry in res_log:
        print(f"    {entry['issue_code']} -> {entry['action']}")
        if entry.get("after"):
            print(f"      After: {json.dumps(entry['after'], default=str)}")

    op = result.get("operation_plan", {})
    print(f"\n  Material after resolution: {op.get('material')}")
    if op.get("tools"):
        for t in op["tools"]:
            print(f"  Tool: id={t.get('id')}, type={t.get('type')}, "
                  f"diameter={t.get('diameter_mm')}mm, source={t.get('source', 'original')}")

    print(f"\n  Aborted: {result.get('aborted', False)}")
    print(f"  G-code display allowed: {result.get('gcode_display_allowed', 'N/A')}")

    gcode = result.get("gcode", "")
    if gcode:
        lines = gcode.strip().splitlines()
        print(f"  G-code lines: {len(lines)}")
        if len(lines) <= 30:
            print(f"\n--- G-CODE ---")
            print(gcode)
        else:
            print(f"\n--- G-CODE (first 10 / last 5 lines) ---")
            for line in lines[:10]:
                print(f"  {line}")
            print(f"  ... ({len(lines) - 15} lines omitted) ...")
            for line in lines[-5:]:
                print(f"  {line}")
    else:
        print("  [No G-code generated]")

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
