"""Root agent.py — local test client for the CNC pipeline.

NOT for production use. Use cnc/server.py (MCP server) for integration.

Usage:
    python agent.py
    python agent.py "Turn a 30mm diameter shaft from 35mm stock in steel"
    python agent.py --non-interactive "Drill 6 holes ..."
    python agent.py --warnings-as-errors "Drill 6 holes ..."
    python agent.py --auto-continue "Drill 6 holes ..."
"""

from __future__ import annotations

import argparse
import io
import json
import sys

# Fix Windows console encoding for Unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CNC Test Client — run a prompt through the CNC pipeline",
    )
    parser.add_argument(
        "prompt", nargs="*", default=[],
        help="CNC prompt text (default: built-in pocket milling example)",
    )
    parser.add_argument(
        "--non-interactive", dest="non_interactive", action="store_true",
        help="Disable interactive warning resolution",
    )
    parser.add_argument(
        "--warnings-as-errors", dest="warnings_as_errors", action="store_true",
        help="Treat all warnings as blocking errors",
    )
    parser.add_argument(
        "--auto-continue", dest="auto_continue", action="store_true",
        help="Automatically continue past non-blocking warnings",
    )
    return parser


def main(prompt: str | None = None) -> None:
    """Run a test prompt through the CNC pipeline and print the result."""
    from dotenv import load_dotenv
    load_dotenv()

    parser = _build_arg_parser()
    args = parser.parse_args(sys.argv[1:] if prompt is None else [])

    test_prompt = prompt or (" ".join(args.prompt) if args.prompt else None) or (
        "Mill a rectangular pocket 50x30mm, 8mm deep, in 6061 aluminium. "
        "Use mm units. Safe Z = 10mm."
    )

    interactive = (
        sys.stdin.isatty()
        and not args.non_interactive
        and prompt is None  # programmatic call = non-interactive
    )

    print(f"[CNC Test Client]")
    print(f"Prompt: {test_prompt}")
    if not interactive:
        print("Mode: non-interactive")
    print("-" * 60)

    from cnc.agent import build_cnc_agent

    try:
        agent = build_cnc_agent()
        result = agent.run(test_prompt)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    # --- Interactive warning resolution ---
    if interactive:
        from cnc.cli_interaction import resolve_issues_interactively
        result = resolve_issues_interactively(result, prompt=test_prompt)

        if result.get("aborted"):
            print("\n[Aborted by user]")
            sys.exit(1)
    else:
        # Non-interactive: show issues structured
        from cnc.tools.issue_resolution import collect_interactive_issues
        issues = collect_interactive_issues(result, prompt=test_prompt)

        if issues:
            print("\n--- Issues ---")
            has_blocking = False
            for issue in issues:
                sev = issue["severity"].upper()
                prefix = "ERROR" if sev == "ERROR" else "WARN" if sev == "WARNING" else "INFO"
                print(f"  [{prefix}] {issue['title']}: {issue['message']}")
                if issue.get("affected_operations"):
                    ops = ", ".join(str(o) for o in issue["affected_operations"])
                    print(f"         Affected operations: {ops}")
                if issue.get("blocking"):
                    has_blocking = True

            if args.warnings_as_errors:
                actionable = [i for i in issues if i.get("actionable")]
                if actionable:
                    has_blocking = True
                    print("\n[--warnings-as-errors] Treating actionable warnings as blocking.")

            if has_blocking:
                print("\nBlocking issues present. No G-code output.")
                result["gcode_display_allowed"] = False
            else:
                if args.auto_continue:
                    result["gcode_display_allowed"] = True
                else:
                    result["gcode_display_allowed"] = True
        else:
            result["gcode_display_allowed"] = True

    # --- Display result ---
    print(f"\nMachine type : {result.get('machine_type') or 'unknown'}")

    validation = result.get("validation", {})
    ok = validation.get("ok", False)
    print(f"Validation   : {'OK' if ok else 'FAILED'}")

    # Show resolution log if present
    res_log = result.get("resolution_log", [])
    if res_log:
        print(f"\n--- Resolution Log ({len(res_log)} decision(s)) ---")
        for entry in res_log:
            action = entry.get("action", "?")
            code = entry.get("issue_code", "?")
            print(f"  {code} → {action}")

    # Determine if G-code should be displayed
    display_gcode = result.get("gcode_display_allowed", True)

    if not display_gcode:
        gcode = result.get("gcode", "")
        if gcode:
            lines = gcode.splitlines()
            print(f"\n[G-code generated ({len(lines)} lines) but not displayed due to unresolved issues]")
        else:
            print("\n[No G-code generated]")
    else:
        gcode = result.get("gcode", "")
        if isinstance(gcode, dict):
            print("\n--- G-CODE (multiple programs) ---")
            for prog_name, prog_code in gcode.items():
                if prog_code:
                    print(f"\n[{prog_name}]")
                    print(prog_code)
                else:
                    print(f"\n[{prog_name}] (empty)")
        elif isinstance(gcode, list):
            print("\n--- G-CODE (program list) ---")
            for i, prog_code in enumerate(gcode, 1):
                print(f"\n[Program {i}]")
                print(prog_code)
        elif gcode:
            print("\n--- G-CODE ---")
            print(gcode)
        else:
            print("\n[No G-code generated]")

    op_plan = result.get("operation_plan")
    if op_plan:
        print("\n--- OPERATION PLAN (JSON) ---")
        print(json.dumps(op_plan, indent=2))


if __name__ == "__main__":
    main()
