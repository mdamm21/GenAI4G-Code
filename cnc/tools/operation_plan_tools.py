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
    normalized.setdefault("units", "mm")
    normalized.setdefault("work_coordinate_system", "G54")
    normalized.setdefault("tools", [])
    normalized.setdefault("operations", [])
    normalized.setdefault("assumptions", [])
    normalized.setdefault("warnings", [])
    normalized.setdefault("missing_info", [])

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

        # diameter / diameter_mm
        if "diameter" in nt and "diameter_mm" not in nt:
            nt["diameter_mm"] = nt["diameter"]

        # spindle_speed / spindle_rpm (stored on tool in some agent formats)
        if "spindle_speed" in nt and "spindle_rpm" not in nt:
            nt["spindle_rpm"] = nt["spindle_speed"]

        # feedrate on tool level → feedrate_mmpm (carry-over info, not canonical)
        if "feedrate" in nt and "feedrate_mmpm" not in nt:
            nt["feedrate_mmpm"] = nt["feedrate"]

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

        # feedrate / feedrate_mmpm
        if "feedrate" in nop and "feedrate_mmpm" not in nop:
            nop["feedrate_mmpm"] = nop["feedrate"]

        # spindle_speed / spindle_rpm
        if "spindle_speed" in nop and "spindle_rpm" not in nop:
            nop["spindle_rpm"] = nop["spindle_speed"]

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
