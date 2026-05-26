"""Validation tools — check operation plans before postprocessing."""

# Drill operation types that require complete x/y/z/feedrate parameters.
_DRILL_OP_TYPES = {"drill", "drilling", "peck_drill", "bore", "ream"}

# Mill facing operation types — the structured typed "facing" op only.
# Legacy "face_mill" and "face" types use a different parameter schema and are
# not subject to the new structured facing checks.
_MILL_FACING_OP_TYPES = {"facing"}

# Mill slot operation types.
_MILL_SLOT_OP_TYPES = {"slot"}

# Valid slot directions.
_VALID_SLOT_DIRECTIONS = {"x", "y"}

# Mill pocket operation types.
_MILL_POCKET_OP_TYPES = {"pocket"}


def validate_operation_plan(operation_plan: dict) -> dict:
    """Validate a structured operation plan dict.

    Performs generic checks for all machine types and additional
    drill-specific checks when machine_type == "drill".

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

    machine_type: str = operation_plan.get("machine_type") or ""

    # --- Required fields (all machine types) ---
    if not machine_type:
        errors.append("Missing required field: machine_type.")

    if not operation_plan.get("units"):
        errors.append("Missing required field: units (mm or inch).")

    safe_z = operation_plan.get("safe_z")
    if safe_z is None:
        errors.append("Missing required field: safe_z.")
    elif isinstance(safe_z, (int, float)) and safe_z <= 0:
        warnings.append(
            f"safe_z={safe_z} is not positive. Safe Z should be above the workpiece."
        )

    operations = operation_plan.get("operations")
    if not operations:
        errors.append("No operations defined in plan.")

    # --- Generic per-operation checks ---
    if operations:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                warnings.append(f"Operation {i} is not a dict, skipping detail checks.")
                continue
            op_label = f"Operation {i} ('{op.get('name', op.get('type', i))}')"
            if not op.get("feedrate_mmpm") and not op.get("feedrate"):
                # For drill this becomes an error below; here it is a generic warning
                warnings.append(f"{op_label} has no feedrate defined.")
            if op.get("tool_number") is None and op.get("tool_id") is None:
                warnings.append(f"{op_label} has no tool_number or tool_id.")

    # --- Tool data completeness (all machine types) ---
    tools = operation_plan.get("tools", [])
    if not tools:
        warnings.append("No tool definitions found in operation plan.")
    else:
        for t in tools:
            if not isinstance(t, dict):
                continue
            tid = t.get("tool_number") or t.get("id") or "?"
            if not t.get("diameter_mm") and not t.get("diameter"):
                warnings.append(f"Tool {tid} has no diameter defined.")

    # --- Drill-specific checks ---
    if machine_type == "drill" and operations:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                continue
            op_type = op.get("type", "")
            if op_type not in _DRILL_OP_TYPES and op_type:
                # Not a drill-type operation — skip drill-specific checks
                continue

            op_label = f"Operation {i} (type='{op_type}')"
            params = op.get("parameters", {})

            # x, y, z are errors — cannot drill without coordinates
            if params.get("x") is None:
                errors.append(f"{op_label}: missing required parameter 'x' (hole X position).")
            if params.get("y") is None:
                errors.append(f"{op_label}: missing required parameter 'y' (hole Y position).")
            if params.get("z") is None:
                errors.append(
                    f"{op_label}: missing required parameter 'z' (drill depth/target Z)."
                )

            # feedrate is an error for drill — G1 without F is illegal
            if not op.get("feedrate_mmpm") and not op.get("feedrate"):
                errors.append(
                    f"{op_label}: missing required 'feedrate' "
                    "(G1 plunge without feedrate is not safe)."
                )

            # spindle_speed is a warning — can drill without spindle cmd but unusual
            if not op.get("spindle_rpm") and not op.get("spindle_speed"):
                warnings.append(
                    f"{op_label}: no spindle_speed/spindle_rpm specified. "
                    "Spindle start (M03) will be skipped."
                )

    # --- Mill-specific checks ---
    if machine_type == "mill" and operations:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                continue
            op_type = op.get("type", "")
            if op_type not in _MILL_FACING_OP_TYPES:
                # Not a facing-type operation — skip facing-specific checks
                continue

            op_label = f"Operation {i} (type='{op_type}')"
            params = op.get("parameters", {})

            # origin_x / origin_y: required (0 is valid → use is None check)
            if params.get("origin_x") is None:
                errors.append(
                    f"{op_label}: missing required parameter 'origin_x'."
                )
            if params.get("origin_y") is None:
                errors.append(
                    f"{op_label}: missing required parameter 'origin_y'."
                )

            # width, height, step_over, tool_diameter: required and positive
            for param_name in ("width", "height", "step_over", "tool_diameter"):
                val = params.get(param_name)
                if val is None:
                    errors.append(f"{op_label}: missing required parameter '{param_name}'.")
                elif isinstance(val, (int, float)) and val <= 0:
                    errors.append(
                        f"{op_label}: invalid parameter '{param_name}'={val} "
                        "(must be > 0)."
                    )

            # target_z: required (0 is invalid for a cutting depth)
            target_z = params.get("target_z")
            if target_z is None:
                errors.append(f"{op_label}: missing required parameter 'target_z'.")
            elif isinstance(target_z, (int, float)) and target_z >= 0:
                errors.append(
                    f"{op_label}: 'target_z'={target_z} is not negative. "
                    "Cutting depth must be below Z=0."
                )

            # feedrate is an error — G1 cutting without F is illegal
            if not op.get("feedrate_mmpm") and not op.get("feedrate"):
                errors.append(
                    f"{op_label}: missing required 'feedrate' "
                    "(G1 cutting move without feedrate is not safe)."
                )

            # spindle_speed is a warning
            if not op.get("spindle_rpm") and not op.get("spindle_speed"):
                warnings.append(
                    f"{op_label}: no spindle_speed/spindle_rpm specified. "
                    "Spindle start (M03) will be skipped."
                )

    # --- Mill slot-specific checks ---
    if machine_type == "mill" and operations:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                continue
            op_type = op.get("type", "")
            if op_type not in _MILL_SLOT_OP_TYPES:
                continue

            op_label = f"Operation {i} (type='{op_type}')"
            params = op.get("parameters", {})

            # start_x / start_y: required (0 is valid → use is None)
            if params.get("start_x") is None:
                errors.append(f"{op_label}: missing required parameter 'start_x'.")
            if params.get("start_y") is None:
                errors.append(f"{op_label}: missing required parameter 'start_y'.")

            # length: required and > 0
            length_val = params.get("length")
            if length_val is None:
                errors.append(f"{op_label}: missing required parameter 'length'.")
            elif isinstance(length_val, (int, float)) and length_val <= 0:
                errors.append(
                    f"{op_label}: invalid parameter 'length'={length_val} (must be > 0)."
                )

            # target_z: required and negative
            target_z = params.get("target_z")
            if target_z is None:
                errors.append(f"{op_label}: missing required parameter 'target_z'.")
            elif isinstance(target_z, (int, float)) and target_z >= 0:
                errors.append(
                    f"{op_label}: 'target_z'={target_z} is not negative. "
                    "Cutting depth must be below Z=0."
                )

            # direction: required, must be "x" or "y"
            direction = params.get("direction")
            if direction is None:
                errors.append(f"{op_label}: missing required parameter 'direction'.")
            elif str(direction).strip().lower() not in _VALID_SLOT_DIRECTIONS:
                errors.append(
                    f"{op_label}: invalid parameter 'direction'='{direction}'. "
                    "Must be 'x' or 'y'."
                )

            # step_down: required and > 0
            step_down = params.get("step_down")
            if step_down is None:
                errors.append(f"{op_label}: missing required parameter 'step_down'.")
            elif isinstance(step_down, (int, float)) and step_down <= 0:
                errors.append(
                    f"{op_label}: invalid parameter 'step_down'={step_down} (must be > 0)."
                )
            elif (
                isinstance(step_down, (int, float))
                and isinstance(target_z, (int, float))
                and step_down > abs(target_z)
            ):
                warnings.append(
                    f"{op_label}: step_down ({step_down}) > total depth ({abs(target_z)}). "
                    "A single pass to target_z will be used."
                )

            # tool_diameter: required and > 0
            td_val = params.get("tool_diameter")
            if td_val is None:
                errors.append(f"{op_label}: missing required parameter 'tool_diameter'.")
            elif isinstance(td_val, (int, float)) and td_val <= 0:
                errors.append(
                    f"{op_label}: invalid parameter 'tool_diameter'={td_val} (must be > 0)."
                )

            # feedrate: error — G1 without F is unsafe
            if not op.get("feedrate_mmpm") and not op.get("feedrate"):
                errors.append(
                    f"{op_label}: missing required 'feedrate' "
                    "(G1 cutting move without feedrate is not safe)."
                )

            # spindle_speed: warning
            if not op.get("spindle_rpm") and not op.get("spindle_speed"):
                warnings.append(
                    f"{op_label}: no spindle_speed/spindle_rpm specified. "
                    "Spindle start (M03) will be skipped."
                )

    # --- Mill pocket-specific checks ---
    if machine_type == "mill" and operations:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                continue
            op_type = op.get("type", "")
            if op_type not in _MILL_POCKET_OP_TYPES:
                continue

            op_label = f"Operation {i} (type='{op_type}')"
            params = op.get("parameters", {})

            # origin_x / origin_y: required (0 is valid -> use is None)
            if params.get("origin_x") is None:
                errors.append(f"{op_label}: missing required parameter 'origin_x'.")
            if params.get("origin_y") is None:
                errors.append(f"{op_label}: missing required parameter 'origin_y'.")

            # width, height: required and > 0
            for param_name in ("width", "height"):
                val = params.get(param_name)
                if val is None:
                    errors.append(f"{op_label}: missing required parameter '{param_name}'.")
                elif isinstance(val, (int, float)) and val <= 0:
                    errors.append(
                        f"{op_label}: invalid parameter '{param_name}'={val} (must be > 0)."
                    )

            # target_z: required and negative
            target_z = params.get("target_z")
            if target_z is None:
                errors.append(f"{op_label}: missing required parameter 'target_z'.")
            elif isinstance(target_z, (int, float)) and target_z >= 0:
                errors.append(
                    f"{op_label}: 'target_z'={target_z} is not negative. "
                    "Cutting depth must be below Z=0."
                )

            # step_down: required and > 0
            step_down = params.get("step_down")
            if step_down is None:
                errors.append(f"{op_label}: missing required parameter 'step_down'.")
            elif isinstance(step_down, (int, float)) and step_down <= 0:
                errors.append(
                    f"{op_label}: invalid parameter 'step_down'={step_down} (must be > 0)."
                )
            elif (
                isinstance(step_down, (int, float))
                and isinstance(target_z, (int, float))
                and step_down > abs(target_z)
            ):
                warnings.append(
                    f"{op_label}: step_down ({step_down}) > total depth ({abs(target_z)}). "
                    "A single pass to target_z will be used."
                )

            # step_over: required and > 0
            step_over = params.get("step_over")
            if step_over is None:
                errors.append(f"{op_label}: missing required parameter 'step_over'.")
            elif isinstance(step_over, (int, float)) and step_over <= 0:
                errors.append(
                    f"{op_label}: invalid parameter 'step_over'={step_over} (must be > 0)."
                )
            else:
                td_val = params.get("tool_diameter")
                if (
                    isinstance(step_over, (int, float))
                    and isinstance(td_val, (int, float))
                    and td_val > 0
                    and step_over > td_val
                ):
                    warnings.append(
                        f"{op_label}: step_over ({step_over}) > tool_diameter ({td_val}). "
                        "May leave uncut material."
                    )

            # tool_diameter: required and > 0
            td_val = params.get("tool_diameter")
            if td_val is None:
                errors.append(f"{op_label}: missing required parameter 'tool_diameter'.")
            elif isinstance(td_val, (int, float)) and td_val <= 0:
                errors.append(
                    f"{op_label}: invalid parameter 'tool_diameter'={td_val} (must be > 0)."
                )

            # feedrate: error — G1 without F is unsafe
            if not op.get("feedrate_mmpm") and not op.get("feedrate"):
                errors.append(
                    f"{op_label}: missing required 'feedrate' "
                    "(G1 cutting move without feedrate is not safe)."
                )

            # spindle_speed: warning
            if not op.get("spindle_rpm") and not op.get("spindle_speed"):
                warnings.append(
                    f"{op_label}: no spindle_speed/spindle_rpm specified. "
                    "Spindle start (M03) will be skipped."
                )

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings}
