"""Tool Library — built-in registry of common CNC tools.

Provides dimensional and capability metadata for well-known tools so that
job specs can reference tools by a stable ID rather than by inline geometry.

No cutting data (feedrate, spindle speed, depth of cut) is stored here —
those values are always job-specific.

Usage::

    from cnc.tools.tool_library import list_tools, get_tool, find_tools
    from cnc.tools.tool_library import resolve_tool_id, resolve_operation_plan_tools

    all_tools = list_tools()
    drill = get_tool("drill_5mm")
    mills = find_tools(machine_type="mill", tool_type="end_mill")
    resolution = resolve_tool_id("drill_5mm", machine_type="drill", operation_type="drill")
"""

from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# Built-in tool registry
# ---------------------------------------------------------------------------

_BUILTIN_TOOLS: dict[str, dict] = {
    "drill_5mm": {
        "id": "drill_5mm",
        "name": "5mm HSS Drill Bit",
        "tool_type": "drill",
        "diameter": 5.0,
        "units": "mm",
        "flute_count": 2,
        "material": "HSS",
        "supported_machine_types": ["drill", "mill"],
        "supported_operations": [
            "drill",
            "drilling",
            "peck_drill",
            "bore",
            "ream",
        ],
        "notes": [
            "General-purpose 5mm HSS drill bit.",
            "Suitable for drilling in mild steel, aluminium, and plastics.",
            "No cutting parameters stored — supply feedrate and spindle speed per job.",
        ],
        "metadata": {},
    },
    "drill_3mm": {
        "id": "drill_3mm",
        "name": "3mm HSS Drill Bit",
        "tool_type": "drill",
        "diameter": 3.0,
        "units": "mm",
        "flute_count": 2,
        "material": "HSS",
        "supported_machine_types": ["drill", "mill"],
        "supported_operations": [
            "drill",
            "drilling",
            "peck_drill",
            "bore",
            "ream",
        ],
        "notes": [
            "General-purpose 3mm HSS drill bit.",
            "Suitable for drilling in mild steel, aluminium, and plastics.",
            "No cutting parameters stored — supply feedrate and spindle speed per job.",
        ],
        "metadata": {},
    },
    "endmill_5mm_flat": {
        "id": "endmill_5mm_flat",
        "name": "5mm 4-Flute Flat End Mill",
        "tool_type": "end_mill",
        "diameter": 5.0,
        "units": "mm",
        "flute_count": 4,
        "material": "HSS",
        "supported_machine_types": ["mill"],
        "supported_operations": [
            "facing",
            "slot",
            "pocket",
            "contour",
            "profile",
        ],
        "notes": [
            "General-purpose 5mm 4-flute flat end mill.",
            "Suitable for facing, slotting, and pocket milling in aluminium and mild steel.",
            "No cutting parameters stored — supply feedrate and spindle speed per job.",
        ],
        "metadata": {},
    },
    "endmill_3mm_flat": {
        "id": "endmill_3mm_flat",
        "name": "3mm 4-Flute Flat End Mill",
        "tool_type": "end_mill",
        "diameter": 3.0,
        "units": "mm",
        "flute_count": 4,
        "material": "HSS",
        "supported_machine_types": ["mill"],
        "supported_operations": [
            "facing",
            "slot",
            "pocket",
            "contour",
            "profile",
        ],
        "notes": [
            "General-purpose 3mm 4-flute flat end mill.",
            "Suitable for facing, slotting, and pocket milling in aluminium and mild steel.",
            "No cutting parameters stored — supply feedrate and spindle speed per job.",
        ],
        "metadata": {},
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_tools() -> list[dict]:
    """Return all built-in tools as a list of dicts.

    Returns deep copies — callers cannot mutate the registry.
    """
    return [copy.deepcopy(t) for t in _BUILTIN_TOOLS.values()]


def get_tool(tool_id: str) -> dict | None:
    """Return the named built-in tool, or None if unknown.

    Args:
        tool_id: Tool ID, e.g. "drill_5mm".

    Returns:
        A copy of the tool dict, or None if the ID is not registered.
    """
    tool = _BUILTIN_TOOLS.get(tool_id)
    if tool is None:
        return None
    return copy.deepcopy(tool)


def find_tools(
    machine_type: str | None = None,
    operation_type: str | None = None,
    tool_type: str | None = None,
    units: str | None = None,
) -> list[dict]:
    """Return all tools matching the given filter criteria.

    All filters are optional and AND-combined. An empty call returns all tools.

    Args:
        machine_type:   Filter to tools that support this machine type
                        (e.g. "drill", "mill").
        operation_type: Filter to tools that support this operation type
                        (e.g. "drill", "facing", "pocket").
        tool_type:      Filter by tool_type field
                        (e.g. "drill", "end_mill", "engraver").
        units:          Filter by unit system ("mm" or "inch").

    Returns:
        List of matching tool dicts (deep copies).
    """
    results: list[dict] = []
    for tool in _BUILTIN_TOOLS.values():
        if machine_type and machine_type not in tool.get("supported_machine_types", []):
            continue
        if operation_type and operation_type not in tool.get("supported_operations", []):
            continue
        if tool_type and tool.get("tool_type") != tool_type:
            continue
        if units and tool.get("units") != units:
            continue
        results.append(copy.deepcopy(tool))
    return results


def resolve_tool_id(
    tool_id: str,
    machine_type: str | None = None,
    operation_type: str | None = None,
    units: str | None = None,
) -> dict:
    """Validate a tool_id against the built-in registry.

    Unknown tool_ids always produce a warning (never an error) since
    job specs often use machine-internal IDs like "T1" that are not
    in the library.

    Args:
        tool_id:        Tool ID to resolve.
        machine_type:   If provided, warn if tool does not support this machine.
        operation_type: If provided, warn if tool does not support this operation.
        units:          If provided, warn if tool units do not match.

    Returns::

        {
          "ok": bool,          # always True (unknown tool is a warning, not error)
          "tool": dict | None, # resolved tool dict, or None if not in registry
          "warnings": list[str],
          "errors": list[str], # always empty (all issues are warnings)
        }
    """
    warnings: list[str] = []
    errors: list[str] = []

    tool = _BUILTIN_TOOLS.get(tool_id)

    if tool is None:
        warnings.append(
            f"Tool ID '{tool_id}' is not in the built-in tool library. "
            "Using as-is — verify tool geometry manually."
        )
        return {"ok": True, "tool": None, "warnings": warnings, "errors": errors}

    tool_copy = copy.deepcopy(tool)

    # machine_type compatibility check
    if machine_type:
        supported_machines = tool.get("supported_machine_types", [])
        if supported_machines and machine_type not in supported_machines:
            warnings.append(
                f"Tool '{tool_id}' supports machine types {supported_machines} "
                f"but machine_type='{machine_type}' was specified."
            )

    # operation_type compatibility check
    if operation_type:
        supported_ops = tool.get("supported_operations", [])
        if supported_ops and operation_type not in supported_ops:
            warnings.append(
                f"Tool '{tool_id}' supports operations {supported_ops} "
                f"but operation_type='{operation_type}' was specified."
            )

    # units compatibility check
    if units:
        tool_units = tool.get("units", "mm")
        if tool_units != units:
            warnings.append(
                f"Tool '{tool_id}' is defined in '{tool_units}' "
                f"but units='{units}' was specified."
            )

    return {"ok": True, "tool": tool_copy, "warnings": warnings, "errors": errors}


def resolve_operation_plan_tools(operation_plan: dict) -> dict:
    """Validate all tool references in an OperationPlan against the registry.

    Checks both the top-level ``tools`` list and each operation's ``tool_id``
    field. Unknown tool_ids produce warnings; known tools used for unsupported
    operation types produce warnings.

    Args:
        operation_plan: An OperationPlan dict as produced by the build_* helpers.

    Returns::

        {
          "ok": bool,
          "warnings": list[str],
          "errors": list[str],
          "resolved": list[dict],  # one entry per tool resolved from the tools list
        }
    """
    warnings: list[str] = []
    errors: list[str] = []
    resolved: list[dict] = []

    if not isinstance(operation_plan, dict):
        return {
            "ok": False,
            "warnings": warnings,
            "errors": ["operation_plan must be a dict."],
            "resolved": resolved,
        }

    machine_type: str | None = operation_plan.get("machine_type")

    # --- Resolve each tool in the tools list ---
    tools_list = operation_plan.get("tools", [])
    for tool_entry in tools_list:
        if not isinstance(tool_entry, dict):
            continue
        tid = tool_entry.get("id") or tool_entry.get("tool_id") or tool_entry.get("tool_number")
        if not tid:
            continue
        tid = str(tid)
        result = resolve_tool_id(tid, machine_type=machine_type)
        warnings.extend(result["warnings"])
        errors.extend(result["errors"])
        if result["tool"] is not None:
            resolved.append(result["tool"])

    # --- Check each operation's tool_id against the registry ---
    operations = operation_plan.get("operations", [])
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            continue
        op_tool_id = op.get("tool_id") or op.get("tool_number")
        if not op_tool_id:
            continue
        op_tool_id = str(op_tool_id)
        op_type = op.get("type", "")

        # Only check against registry if we haven't already warned about this tool_id
        # (the tools list check above already warned for it)
        known_ids = {
            str(t.get("id") or t.get("tool_id") or t.get("tool_number", ""))
            for t in tools_list
            if isinstance(t, dict)
        }
        if op_tool_id not in known_ids:
            # Referenced in operation but not declared in tools list
            if _BUILTIN_TOOLS.get(op_tool_id) is None:
                warnings.append(
                    f"Operation {i} references tool_id='{op_tool_id}' "
                    "which is not in the tool list or built-in library."
                )
        elif op_type and _BUILTIN_TOOLS.get(op_tool_id) is not None:
            # Tool is known — check operation support
            lib_tool = _BUILTIN_TOOLS[op_tool_id]
            supported_ops = lib_tool.get("supported_operations", [])
            if supported_ops and op_type not in supported_ops:
                warnings.append(
                    f"Operation {i} (type='{op_type}') uses tool '{op_tool_id}' "
                    f"which supports {supported_ops}."
                )

    ok = len(errors) == 0
    return {"ok": ok, "warnings": warnings, "errors": errors, "resolved": resolved}
