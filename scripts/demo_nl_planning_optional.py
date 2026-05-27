"""Demo: Natural-Language Planning (optional — requires ANTHROPIC_API_KEY).

This script demonstrates the full NL → OperationPlan → G-code pipeline.
It requires:
- ANTHROPIC_API_KEY set in environment or .env file
- The CNC DeepAgent (cnc.agent.build_cnc_agent) to be functional

If the API key is missing or the agent is unavailable, the script prints a
clear error message and exits with a non-zero code.
"""

import os
import sys

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Check API key before importing agent
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY is not set.")
    print()
    print("This demo requires the Anthropic API key to use the CNC DeepAgent.")
    print("Set it in your environment or .env file:")
    print("  ANTHROPIC_API_KEY=your-key-here")
    print()
    print("For a demo that works WITHOUT an API key, run:")
    print("  python -m scripts.demo_agent_result_normalization")
    sys.exit(1)

import asyncio
import json

SEPARATOR = "-" * 60

EXAMPLE_PROMPTS = [
    {
        "label": "Simple single-hole drill",
        "prompt": (
            "Drill a 5mm deep hole at X0 Y0 with a 5mm drill bit. "
            "Safe Z 5mm, feedrate 100 mm/min, spindle 1200 rpm, units mm."
        ),
        "machine_type": "drill",
    },
    {
        "label": "Multi-hole drill pattern",
        "prompt": (
            "Drill three holes at X0Y0, X10Y0, and X10Y10, each 5mm deep. "
            "5mm drill, safe Z 5mm, feedrate 100 mm/min, spindle 1200 rpm, units mm."
        ),
        "machine_type": "drill",
    },
    {
        "label": "Rectangular pocket",
        "prompt": (
            "Mill a 20x10mm rectangular pocket 3mm deep at the origin. "
            "5mm end mill, step-down 1mm, step-over 2mm, safe Z 5mm, "
            "feedrate 150 mm/min, spindle 3000 rpm, units mm."
        ),
        "machine_type": "mill",
    },
    {
        "label": "Prompt with missing_info (no feedrate)",
        "prompt": (
            "Drill a hole at X5 Y5, depth 8mm, 5mm drill, safe Z 5mm, units mm. "
            "I forgot to specify the feedrate."
        ),
        "machine_type": "drill",
    },
]


async def run_plan_operation(label: str, prompt: str, machine_type: str) -> None:
    """Call the plan_operation MCP tool and print the result."""
    from cnc.server import plan_operation

    print(SEPARATOR)
    print(f"  PLAN OPERATION: {label}")
    print(SEPARATOR)
    print(f"  Prompt: {prompt[:100]}")
    print()

    try:
        result = await plan_operation(prompt=prompt, machine_type=machine_type)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        print()
        return

    print(f"  ok           : {result['ok']}")
    print(f"  machine_type : {result.get('machine_type')}")
    print(f"  errors       : {result.get('errors', [])}")
    print(f"  missing_info : {result.get('missing_info', [])}")
    print(f"  warnings     : {result.get('warnings', [])[:3]}")
    if result.get("operation_plan"):
        ops = result["operation_plan"].get("operations", [])
        print(f"  operations   : {len(ops)} operation(s)")
    print()


async def run_generate_gcode(label: str, prompt: str, machine_type: str) -> None:
    """Call generate_gcode and print result summary."""
    from cnc.server import generate_gcode

    print(SEPARATOR)
    print(f"  GENERATE GCODE: {label}")
    print(SEPARATOR)
    print(f"  Prompt: {prompt[:100]}")
    print()

    try:
        result = await generate_gcode(prompt=prompt, machine_type=machine_type)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        print()
        return

    print(f"  ok           : {result['ok']}")
    print(f"  machine_type : {result.get('machine_type')}")
    print(f"  postprocessor: {result.get('postprocessor', 'n/a')}")
    print(f"  errors       : {result.get('errors', [])}")
    print(f"  missing_info : {result.get('missing_info', [])}")
    if result.get("gcode"):
        lines = result["gcode"].strip().splitlines()
        print(f"  G-code lines : {len(lines)}")
        print(f"  G-code (first 5 lines):")
        for ln in lines[:5]:
            print(f"    {ln}")
    else:
        print("  G-code       : (none)")
    if result.get("safety_report"):
        sr = result["safety_report"]
        print(f"  risk_level   : {sr.get('risk_level')}")
    print()


async def main() -> None:
    # Run plan_operation for first two examples
    for ex in EXAMPLE_PROMPTS[:2]:
        await run_plan_operation(ex["label"], ex["prompt"], ex["machine_type"])

    # Run generate_gcode for the pocket and missing_info examples
    for ex in EXAMPLE_PROMPTS[2:]:
        await run_generate_gcode(ex["label"], ex["prompt"], ex["machine_type"])


if __name__ == "__main__":
    asyncio.run(main())
