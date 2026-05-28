"""Demo: Tool Library and Tool-ID Resolution.

Demonstrates the Tool Library API and tool-ID resolution pipeline.
No LLM or API key required — all operations are deterministic.

Run:
    python scripts/demo_tool_resolution.py
"""

from __future__ import annotations

import json


def _pretty(data: object) -> str:
    return json.dumps(data, indent=2, default=str)


def main() -> None:
    print("=" * 60)
    print("DEMO: Tool Library and Tool-ID Resolution")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # 1. List all built-in tools
    # -----------------------------------------------------------------------
    print("\n--- 1. list_tools() ---")
    from cnc.tools.tool_library import list_tools
    tools = list_tools()
    print(f"Found {len(tools)} built-in tools:")
    for t in tools:
        print(f"  {t['id']}: {t['name']} ({t['tool_type']}, ø{t['diameter']}mm)")

    # -----------------------------------------------------------------------
    # 2. Get a single tool
    # -----------------------------------------------------------------------
    print("\n--- 2. get_tool('drill_5mm') ---")
    from cnc.tools.tool_library import get_tool
    tool = get_tool("drill_5mm")
    print(f"  id: {tool['id']}")
    print(f"  name: {tool['name']}")
    print(f"  diameter: {tool['diameter']}mm")
    print(f"  supported_machine_types: {tool['supported_machine_types']}")
    print(f"  supported_operations: {tool['supported_operations']}")

    # -----------------------------------------------------------------------
    # 3. Find tools by machine type and operation
    # -----------------------------------------------------------------------
    print("\n--- 3. find_tools(machine_type='mill', operation_type='pocket') ---")
    from cnc.tools.tool_library import find_tools
    mill_pocket_tools = find_tools(machine_type="mill", operation_type="pocket")
    print(f"  {len(mill_pocket_tools)} tool(s) found:")
    for t in mill_pocket_tools:
        print(f"    {t['id']}")

    # -----------------------------------------------------------------------
    # 4. Resolve a known tool
    # -----------------------------------------------------------------------
    print("\n--- 4. resolve_tool_id('drill_5mm', machine_type='drill', operation_type='drill') ---")
    from cnc.tools.tool_library import resolve_tool_id
    result = resolve_tool_id("drill_5mm", machine_type="drill", operation_type="drill")
    print(f"  ok: {result['ok']}")
    print(f"  tool.id: {result['tool']['id']}")
    print(f"  warnings: {result['warnings']}")

    # -----------------------------------------------------------------------
    # 5. Resolve an unknown tool (warning, not error)
    # -----------------------------------------------------------------------
    print("\n--- 5. resolve_tool_id('T1') — unknown tool ---")
    result = resolve_tool_id("T1")
    print(f"  ok: {result['ok']}")  # True — unknown is a warning
    print(f"  tool: {result['tool']}")
    print(f"  warnings: {result['warnings']}")

    # -----------------------------------------------------------------------
    # 6. Resolve a known tool used with wrong machine (warning)
    # -----------------------------------------------------------------------
    print("\n--- 6. resolve_tool_id('endmill_5mm_flat', machine_type='drill') ---")
    result = resolve_tool_id("endmill_5mm_flat", machine_type="drill")
    print(f"  ok: {result['ok']}")
    print(f"  warnings: {result['warnings']}")

    # -----------------------------------------------------------------------
    # 7. Build a drill plan with library tool_id
    # -----------------------------------------------------------------------
    print("\n--- 7. build_drill_operation_plan(tool_id='drill_5mm') ---")
    from cnc.tools.drill_tools import build_drill_operation_plan
    plan = build_drill_operation_plan(
        x=10, y=20, depth=5, tool_diameter=5.0,
        safe_z=5.0, feedrate=150, spindle_speed=1200,
        tool_id="drill_5mm",
    )
    print(f"  tools[0].id: {plan['tools'][0]['id']}")
    print(f"  operations[0].tool_id: {plan['operations'][0]['tool_id']}")

    # -----------------------------------------------------------------------
    # 8. Resolve all tool references in an operation plan
    # -----------------------------------------------------------------------
    print("\n--- 8. resolve_operation_plan_tools(plan with known drill_5mm) ---")
    from cnc.tools.tool_library import resolve_operation_plan_tools
    resolution = resolve_operation_plan_tools(plan)
    print(f"  ok: {resolution['ok']}")
    print(f"  resolved: {[t['id'] for t in resolution['resolved']]}")
    print(f"  warnings: {resolution['warnings']}")

    # -----------------------------------------------------------------------
    # 9. Machine profile default_tool_ids
    # -----------------------------------------------------------------------
    print("\n--- 9. get_machine_profile('generic_drill_mm').default_tool_ids ---")
    from cnc.tools.machine_profiles import get_machine_profile
    profile = get_machine_profile("generic_drill_mm")
    print(f"  default_tool_ids: {profile['default_tool_ids']}")

    print("\n--- 10. get_machine_profile('generic_mill_mm').default_tool_ids ---")
    profile_mill = get_machine_profile("generic_mill_mm")
    print(f"  default_tool_ids: {profile_mill['default_tool_ids']}")

    print("\n" + "=" * 60)
    print("Demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
