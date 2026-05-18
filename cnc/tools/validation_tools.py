"""Validation tools — check operation plans before postprocessing."""


def validate_operation_plan(operation_plan: dict) -> dict:
    """Validate a structured operation plan dict.

    Returns:
        {
          "ok": bool,
          "errors": list[str],
          "warnings": list[str],
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not operation_plan:
        errors.append("Operation plan is empty or None.")
        return {"ok": False, "errors": errors, "warnings": warnings}

    # Required fields
    if not operation_plan.get("machine_type"):
        errors.append("Missing required field: machine_type.")

    if not operation_plan.get("units"):
        errors.append("Missing required field: units (mm or inch).")

    safe_z = operation_plan.get("safe_z")
    if safe_z is None:
        errors.append("Missing required field: safe_z.")
    elif isinstance(safe_z, (int, float)) and safe_z <= 0:
        warnings.append(f"safe_z={safe_z} is not positive. Safe Z should be above workpiece.")

    operations = operation_plan.get("operations")
    if not operations:
        errors.append("No operations defined in plan.")
    else:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                warnings.append(f"Operation {i} is not a dict, skipping detail checks.")
                continue
            if not op.get("feedrate_mmpm") and not op.get("feedrate"):
                warnings.append(f"Operation '{op.get('name', i)}' has no feedrate defined.")
            tool_num = op.get("tool_number")
            if tool_num is None:
                warnings.append(f"Operation '{op.get('name', i)}' has no tool_number.")

    # Tool data completeness
    tools = operation_plan.get("tools", [])
    if not tools:
        warnings.append("No tool definitions found in operation plan.")
    else:
        for t in tools:
            if not isinstance(t, dict):
                continue
            if not t.get("diameter_mm") and not t.get("diameter"):
                warnings.append(f"Tool {t.get('tool_number', '?')} has no diameter defined.")

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings}
