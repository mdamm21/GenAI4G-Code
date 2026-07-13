"""Operation plan normalization tools.

Converts agent output (which may use different field naming conventions)
into the canonical OperationPlan dict expected by validators and postprocessors.
"""


def normalize_operation_plan(raw: object) -> dict:
    """Normalize a raw agent output dict into the canonical OperationPlan format.

    Handles two common field naming conventions produced by different agents:

    New format (drilling agent):
        tools:      id, name, diameter, spindle_speed, feedrate
        operations: tool_id, feedrate, spindle_speed, parameters: {x, y, z}

    Canonical format (used by validators / postprocessors):
        tools:      tool_number, description, diameter_mm
        operations: tool_number, feedrate_mmpm, spindle_rpm, parameters: {x, y, z}

    Rules:
    - machine_type is NOT invented; if missing it stays None/absent.
    - safe_z is NOT invented; if missing it stays None/absent.
    - Defaults for optional structural fields: units="mm", work_coordinate_system="G54".
    - Existing missing_info, warnings, assumptions are preserved.
    - No exceptions are raised — errors produce a warning entry in the result.

    Args:
        raw: The raw dict (or any value) from an agent or external source.

    Returns:
        A normalized OperationPlan dict.
    """
    if not isinstance(raw, dict):
        return {
            "machine_type": None,
            "units": "mm",
            "work_coordinate_system": "G54",
            "tools": [],
            "operations": [],
            "assumptions": [],
            "warnings": [
                f"normalize_operation_plan: expected dict, got {type(raw).__name__}"
            ],
            "missing_info": [],
        }

    # Shallow copy so we don't mutate the input
    normalized: dict = dict(raw)

    # --- Optional field defaults (never invent machine_type or safe_z) ---
    normalized.setdefault("tools", [])
    normalized.setdefault("operations", [])
    normalized.setdefault("assumptions", [])
    normalized.setdefault("warnings", [])
    normalized.setdefault("missing_info", [])

    # Track which fields were defaulted (not explicitly provided)
    if "units" not in raw:
        normalized["units"] = "mm"
        normalized["assumptions"].append("Assumed units: mm (not specified in plan)")
    else:
        normalized.setdefault("units", raw["units"])

    if "work_coordinate_system" not in raw:
        normalized["work_coordinate_system"] = "G54"
        normalized["assumptions"].append("Assumed work coordinate system: G54 (not specified in plan)")
    else:
        normalized.setdefault("work_coordinate_system", raw["work_coordinate_system"])

    if "machine_type" not in raw or raw.get("machine_type") is None:
        normalized["assumptions"].append("Machine type not specified in plan")

    # --- Normalize tools ---
    normalized["tools"] = _normalize_tools(normalized["tools"])

    # --- Normalize operations ---
    normalized["operations"] = _normalize_operations(normalized["operations"])

    return normalized


def _normalize_tools(tools: list) -> list:
    """Normalize tool entries to the canonical field names."""
    result = []
    for i, t in enumerate(tools):
        if not isinstance(t, dict):
            continue
        nt = dict(t)

        # id / tool_number
        if "id" in nt and "tool_number" not in nt:
            nt["tool_number"] = _parse_tool_id(nt["id"], fallback=i + 1)

        # name / description
        if "name" in nt and "description" not in nt:
            nt["description"] = nt["name"]

        # diameter / diameter_mm — canonicalize then remove deprecated alias
        if "diameter" in nt and "diameter_mm" not in nt:
            nt["diameter_mm"] = nt["diameter"]
        if "diameter_mm" in nt:
            nt.pop("diameter", None)

        # spindle_speed / spindle_rpm (stored on tool in some agent formats)
        if "spindle_speed" in nt and "spindle_rpm" not in nt:
            nt["spindle_rpm"] = nt["spindle_speed"]
        if "spindle_rpm" in nt:
            nt.pop("spindle_speed", None)

        # feedrate on tool level → feedrate_mmpm (carry-over info, not canonical)
        if "feedrate" in nt and "feedrate_mmpm" not in nt:
            nt["feedrate_mmpm"] = nt["feedrate"]
        if "feedrate_mmpm" in nt:
            nt.pop("feedrate", None)

        result.append(nt)
    return result


def _normalize_operations(operations: list) -> list:
    """Normalize operation entries to the canonical field names."""
    result = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        nop = dict(op)

        # tool_id / tool_number
        if "tool_id" in nop and "tool_number" not in nop:
            nop["tool_number"] = _parse_tool_id(nop["tool_id"], fallback=None)

        # feedrate / feedrate_mmpm — canonicalize then remove deprecated alias
        if "feedrate" in nop and "feedrate_mmpm" not in nop:
            nop["feedrate_mmpm"] = nop["feedrate"]
        if "feedrate_mmpm" in nop:
            nop.pop("feedrate", None)

        # spindle_speed / spindle_rpm — canonicalize then remove deprecated alias
        if "spindle_speed" in nop and "spindle_rpm" not in nop:
            nop["spindle_rpm"] = nop["spindle_speed"]
        if "spindle_rpm" in nop:
            nop.pop("spindle_speed", None)

        # description / name
        if "description" in nop and "name" not in nop:
            nop["name"] = nop["description"]
        elif "name" not in nop:
            nop["name"] = str(nop.get("type", "operation"))

        result.append(nop)
    return result


def _parse_tool_id(tool_id: object, fallback: int | None) -> int | None:
    """Convert a tool id like 'T1' or '1' to an integer, or return fallback."""
    id_str = str(tool_id).strip().lstrip("Tt")
    try:
        return int(id_str)
    except ValueError:
        return fallback


# ---------------------------------------------------------------------------
# Tool reference normalization
# ---------------------------------------------------------------------------


def normalize_tool_references(operation_plan: dict) -> dict:
    """Normalize tool_number references to stable plan-local tool IDs.

    When the agent produces tools with ``tool_number`` but no ``id``, this
    function assigns a canonical plan-local ID (e.g. ``"T1"``) so that
    validators do not incorrectly look up numeric IDs like ``"1"`` in the
    built-in tool library.

    Existing real ``id`` / ``tool_id`` values (e.g. ``"drill_5mm"``) are
    preserved.

    Args:
        operation_plan: An OperationPlan dict (modified in place and returned).

    Returns:
        The updated operation_plan dict with:
        - tools[].id set to "T{tool_number}" when id was missing
        - operations[].tool_id set to match the corresponding tool id
    """
    if not isinstance(operation_plan, dict):
        return operation_plan

    warnings: list[str] = list(operation_plan.get("warnings", []))

    # Build tool_number → id mapping
    tool_number_to_id: dict[int | str, str] = {}
    tools = operation_plan.get("tools", [])

    for t in tools:
        if not isinstance(t, dict):
            continue

        existing_id = t.get("id")
        tool_number = t.get("tool_number")

        if existing_id and not _is_bare_numeric_id(existing_id):
            # Real tool_id like "drill_5mm" — keep it
            if tool_number is not None:
                tool_number_to_id[tool_number] = existing_id
                tool_number_to_id[str(tool_number)] = existing_id
        elif tool_number is not None:
            # No real id or bare numeric id — assign plan-local ID
            plan_id = f"T{tool_number}"
            t["id"] = plan_id
            tool_number_to_id[tool_number] = plan_id
            tool_number_to_id[str(tool_number)] = plan_id
        elif existing_id and _is_bare_numeric_id(existing_id):
            # id is just a number like "1" — normalize to "T1"
            num = _parse_tool_id(existing_id, None)
            if num is not None:
                plan_id = f"T{num}"
                t["id"] = plan_id
                if tool_number is None:
                    t["tool_number"] = num

    # Update operation tool references
    operations = operation_plan.get("operations", [])
    for op in operations:
        if not isinstance(op, dict):
            continue

        op_tool_id = op.get("tool_id")
        op_tool_number = op.get("tool_number")

        if op_tool_id and not _is_bare_numeric_id(str(op_tool_id)):
            # Real tool_id — keep it
            continue

        # Try to map from tool_number
        if op_tool_number is not None and op_tool_number in tool_number_to_id:
            op["tool_id"] = tool_number_to_id[op_tool_number]
        elif op_tool_number is not None and str(op_tool_number) in tool_number_to_id:
            op["tool_id"] = tool_number_to_id[str(op_tool_number)]
        elif op_tool_number is not None:
            # No matching tool definition — assign plan-local ID anyway
            op["tool_id"] = f"T{op_tool_number}"
        elif op_tool_id is not None and _is_bare_numeric_id(str(op_tool_id)):
            # Bare numeric tool_id like "1" — normalize
            num = _parse_tool_id(op_tool_id, None)
            if num is not None:
                mapped = tool_number_to_id.get(num, tool_number_to_id.get(str(num)))
                op["tool_id"] = mapped or f"T{num}"

    operation_plan["warnings"] = warnings
    return operation_plan


def _is_bare_numeric_id(tool_id: str) -> bool:
    """Check if a tool_id is just a bare number (e.g. '1', '01')."""
    stripped = str(tool_id).strip()
    try:
        int(stripped)
        return True
    except ValueError:
        return False


def get_plan_local_tool_ids(operation_plan: dict) -> set[str]:
    """Return the set of tool IDs defined in the plan's tools list.

    These are plan-local references that should NOT be looked up in the
    built-in tool library.
    """
    ids: set[str] = set()
    if not isinstance(operation_plan, dict):
        return ids
    for t in operation_plan.get("tools", []):
        if isinstance(t, dict):
            tid = t.get("id")
            if tid:
                ids.add(str(tid))
    return ids
