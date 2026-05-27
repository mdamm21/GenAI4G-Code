"""Demo: Agent Result Normalization — extract and normalize OperationPlans from agent output.

Shows how extract_operation_plan_from_agent_result and normalize_agent_operation_plan
handle various agent return shapes — no API key or LLM required.
"""

import json
from cnc.tools.agent_result_tools import (
    extract_operation_plan_from_agent_result,
    normalize_agent_operation_plan,
    is_operation_plan_like,
)

SEPARATOR = "-" * 60

MINIMAL_DRILL_PLAN = {
    "machine_type": "drill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"tool_number": 1, "description": "5mm drill", "diameter_mm": 5}],
    "operations": [
        {
            "type": "drill",
            "name": "hole 1",
            "tool_number": 1,
            "feedrate_mmpm": 100,
            "spindle_rpm": 1200,
            "parameters": {"x": 0.0, "y": 0.0, "z": -5.0},
        }
    ],
    "assumptions": [],
    "warnings": [],
    "missing_info": [],
}


def run_extraction(label: str, raw: object) -> None:
    print(SEPARATOR)
    print(f"  {label}")
    print(SEPARATOR)
    result = extract_operation_plan_from_agent_result(raw)
    plan_found = is_operation_plan_like(result)
    print(f"  OperationPlan found : {plan_found}")
    if plan_found:
        normalized = normalize_agent_operation_plan(result)
        print(f"  machine_type        : {normalized.get('machine_type')}")
        print(f"  units               : {normalized.get('units', '(not set)')}")
        print(f"  safe_z              : {normalized.get('safe_z', '(not set)')}")
        print(f"  operations          : {len(normalized.get('operations', []))} op(s)")
        print(f"  missing_info        : {normalized.get('missing_info', [])}")
        print(f"  warnings            : {normalized.get('warnings', [])}")
    else:
        print(f"  ok                  : {result.get('ok')}")
        print(f"  errors              : {result.get('errors')}")
        preview = result.get("raw_output_preview", "")
        if preview:
            print(f"  raw_output_preview  : {preview[:80]!r}")
    print()


# 1. Direct OperationPlan dict
run_extraction(
    "Example 1: Direct OperationPlan dict",
    MINIMAL_DRILL_PLAN,
)

# 2. Agent result wrapped under "operation_plan" key (CNCAgent style)
run_extraction(
    "Example 2: {'operation_plan': plan, 'gcode': '', ...}",
    {
        "operation_plan": MINIMAL_DRILL_PLAN,
        "gcode": "",
        "assumptions": [],
        "warnings": [],
        "missing_info": [],
        "validation": {"ok": False, "errors": [], "warnings": []},
        "machine_type": "drill",
    },
)

# 3. JSON string containing OperationPlan
run_extraction(
    "Example 3: Plain JSON string of OperationPlan",
    json.dumps(MINIMAL_DRILL_PLAN),
)

# 4. JSON string inside markdown code fence
run_extraction(
    "Example 4: Markdown-fenced JSON string",
    "Here is the operation plan:\n```json\n" + json.dumps(MINIMAL_DRILL_PLAN) + "\n```",
)

# 5. Plan with missing_info (normalize will preserve it)
run_extraction(
    "Example 5: Plan with missing_info (depth, feedrate)",
    {
        "machine_type": "drill",
        "units": "mm",
        "operations": [],
        "missing_info": ["depth not specified", "feedrate not specified"],
        "warnings": [],
        "assumptions": [],
    },
)

# 6. Unstructured prose output — should produce error dict
run_extraction(
    "Example 6: Unstructured prose (should produce error)",
    "I will now generate G-code: G21 G90 M03 S1200 G01 Z-5 F100 M30",
)

# 7. Plan without WCS — normalize adds G54 default + warning
print(SEPARATOR)
print("  Example 7: Plan without WCS — normalize adds G54 default")
print(SEPARATOR)
plan_no_wcs = {
    "machine_type": "mill",
    "units": "mm",
    "operations": [],
}
normalized = normalize_agent_operation_plan(plan_no_wcs)
print(f"  work_coordinate_system : {normalized['work_coordinate_system']}")
print(f"  warnings added         : {normalized['warnings']}")
print()
