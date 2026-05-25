"""Root agent.py — local test client for the CNC pipeline.

NOT for production use. Use cnc/server.py (MCP server) for integration.

Usage:
    python agent.py
    python agent.py "Turn a 30mm diameter shaft from 35mm stock in steel"
"""

from __future__ import annotations

import io
import json
import sys

# Fix Windows console encoding for Unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main(prompt: str | None = None) -> None:
    """Run a test prompt through the CNC pipeline and print the result."""
    from dotenv import load_dotenv
    load_dotenv()

    from cnc.agent import build_cnc_agent

    test_prompt = prompt or (
        "Mill a rectangular pocket 50x30mm, 8mm deep, in 6061 aluminium. "
        "Use mm units. Safe Z = 10mm."
    )

    print(f"[CNC Test Client]")
    print(f"Prompt: {test_prompt}")
    print("-" * 60)

    try:
        agent = build_cnc_agent()
        result = agent.run(test_prompt)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    # Print structured result
    print(f"Machine type : {result.get('machine_type') or 'unknown'}")

    validation = result.get("validation", {})
    ok = validation.get("ok", False)
    print(f"Validation   : {'OK' if ok else 'FAILED'}")

    for err in validation.get("errors", []):
        print(f"  [ERROR] {err}")
    for warn in result.get("warnings", []) + validation.get("warnings", []):
        print(f"  [WARN]  {warn}")
    for assumption in result.get("assumptions", []):
        print(f"  [INFO]  {assumption}")
    for missing in result.get("missing_info", []):
        print(f"  [MISS]  {missing}")

    gcode = result.get("gcode", "")
    if gcode:
        print("\n--- G-CODE ---")
        print(gcode)
    else:
        print("\n[No G-code generated]")

    op_plan = result.get("operation_plan")
    if op_plan:
        print("\n--- OPERATION PLAN (JSON) ---")
        print(json.dumps(op_plan, indent=2))


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    main(prompt)
