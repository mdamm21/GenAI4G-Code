"""Milling tools — typed, deterministic helpers for milling operations.

This module provides a safe, parameter-driven path for generating milling G-code
without an LLM or API key. It backs the MCP tools:
    - generate_milling_facing_gcode  (rectangular surface facing)
    - generate_milling_slot_gcode    (straight slot/groove along X or Y)
    - generate_milling_pocket_gcode  (rectangular pocket, raster clearing)

Pipeline:
    build_milling_facing_operation_plan(...)       — OperationPlan dict from typed params
    generate_milling_facing_gcode_from_params(...) — validate → postprocess → validate G-code

    build_milling_slot_operation_plan(...)         — OperationPlan dict from typed params
    generate_milling_slot_gcode_from_params(...)   — validate → postprocess → validate G-code

    build_milling_pocket_operation_plan(...)       — OperationPlan dict from typed params
    generate_milling_pocket_gcode_from_params(...) — validate → postprocess → validate G-code

Design notes:
    - No cutter compensation (G41/G42) is applied automatically.
    - No tool radius offset is calculated — provide paths as programmed centerline.
    - Slot width is assumed to equal the tool diameter.
    - Pocket uses a simple raster clearing strategy.
    - This is a conservative MVP, not a full CAM system.
    - All generated G-code must be reviewed and simulated before use on a real machine.
"""

from __future__ import annotations


def build_milling_facing_operation_plan(
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    depth: float,
    step_over: float,
    tool_diameter: float,
    safe_z: float | None = None,
    feedrate: float | None = None,
    spindle_speed: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    machine_profile: str | None = None,
    postprocessor: str = "fanuc",
) -> dict:
    """Build a structured OperationPlan dict for a rectangular facing operation.

    Does NOT call the postprocessor. Use generate_milling_facing_gcode_from_params
    for the full validate → postprocess → validate G-code pipeline.

    Args:
        origin_x: X start of the rectangular area to face (lower-left corner).
        origin_y: Y start of the rectangular area to face (lower-left corner).
        width: Width of the area along X (must be > 0).
        height: Height of the area along Y (must be > 0).
        depth: Cutting depth as a positive number (e.g. 1 → cuts to Z=-1).
               Negative values are accepted: interpreted as target Z with a warning.
        step_over: Y step-over distance per pass (must be > 0).
        tool_diameter: End mill diameter (must be > 0).
        safe_z: Safe retract height above the workpiece. Filled from profile if None.
        feedrate: Cutting feedrate (units/min). Filled from profile if None.
        spindle_speed: Spindle speed in RPM. If None, M03 will be skipped.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code, e.g. "G54".
        material: Optional material description.
        machine_profile: Name of a built-in machine profile for defaults.
        postprocessor: Intended postprocessor (informational at this stage).

    Returns:
        A canonical OperationPlan dict ready for validate_operation_plan and
        postprocess_operations.
    """
    from cnc.tools.machine_profiles import get_machine_profile

    assumptions: list[str] = []
    warnings: list[str] = []
    missing_info: list[str] = []

    # --- Apply machine profile defaults ---
    resolved_safe_z = safe_z
    resolved_feedrate = feedrate
    resolved_spindle = spindle_speed

    if machine_profile is not None:
        profile = get_machine_profile(machine_profile)
        if profile is None:
            warnings.append(
                f"Machine profile '{machine_profile}' is not recognised. "
                "Profile defaults not applied."
            )
        else:
            # Profile sets units and WCS authoritatively
            units = profile.get("units", units)
            work_coordinate_system = profile.get(
                "work_coordinate_system", work_coordinate_system
            )
            if resolved_safe_z is None and profile.get("default_safe_z") is not None:
                resolved_safe_z = float(profile["default_safe_z"])
            if resolved_feedrate is None and profile.get("default_feedrate") is not None:
                resolved_feedrate = float(profile["default_feedrate"])
            if resolved_spindle is None and profile.get("default_spindle_speed") is not None:
                resolved_spindle = float(profile["default_spindle_speed"])

    # --- Normalise depth to negative Z target ---
    if depth < 0:
        target_z = float(depth)
        warnings.append(
            "Depth was provided as negative value and was interpreted as target Z "
            f"(target_z={depth})."
        )
    else:
        target_z = -abs(float(depth))

    # --- Validate geometry ---
    if width is None or width <= 0:
        warnings.append(f"Width={width} is not positive — facing area is degenerate.")
        missing_info.append("width")

    if height is None or height <= 0:
        warnings.append(f"Height={height} is not positive — facing area is degenerate.")
        missing_info.append("height")

    if tool_diameter is None or tool_diameter <= 0:
        warnings.append(f"Tool diameter={tool_diameter} is not positive.")
        missing_info.append("tool_diameter")

    if step_over is None or step_over <= 0:
        warnings.append(f"Step-over={step_over} is not positive.")
        missing_info.append("step_over")

    # --- Missing required params ---
    if resolved_feedrate is None:
        warnings.append("Feedrate was not specified.")
        missing_info.append("feedrate")

    if resolved_safe_z is None:
        warnings.append("Safe Z was not specified.")
        missing_info.append("safe_z")

    if resolved_spindle is None:
        warnings.append(
            "Spindle speed was not specified. "
            "Spindle start (M03) will be skipped in generated G-code."
        )

    # --- Material ---
    if material:
        assumptions.append(f"Material: {material}")
    else:
        assumptions.append("Material was not specified.")

    # --- Tool ---
    td = tool_diameter if tool_diameter and tool_diameter > 0 else 0
    tool: dict = {
        "id": "T1",
        "name": f"{td:g}{units} end mill",
        "diameter": td,
        "units": units,
    }
    if resolved_feedrate is not None:
        tool["feedrate"] = resolved_feedrate
    if resolved_spindle is not None:
        tool["spindle_speed"] = resolved_spindle

    # --- Operation ---
    w = width if width and width > 0 else 0
    h = height if height and height > 0 else 0
    so = step_over if step_over and step_over > 0 else 0

    op: dict = {
        "type": "facing",
        "description": (
            f"Face rectangular area {w:g}x{h:g}{units} "
            f"at origin X{float(origin_x):g} Y{float(origin_y):g} "
            f"to depth {abs(target_z):g}{units}"
        ),
        "tool_id": "T1",
        "parameters": {
            "origin_x": float(origin_x),
            "origin_y": float(origin_y),
            "width": float(w),
            "height": float(h),
            "target_z": target_z,
            "step_over": float(so),
            "tool_diameter": float(td),
        },
    }
    if resolved_feedrate is not None:
        op["feedrate"] = resolved_feedrate
    if resolved_spindle is not None:
        op["spindle_speed"] = resolved_spindle

    return {
        "machine_type": "mill",
        "units": units,
        "work_coordinate_system": work_coordinate_system,
        "safe_z": resolved_safe_z,
        "tools": [tool],
        "operations": [op],
        "assumptions": assumptions,
        "warnings": warnings,
        "missing_info": missing_info,
    }


def generate_milling_facing_gcode_from_params(
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    depth: float,
    step_over: float,
    tool_diameter: float,
    safe_z: float | None = None,
    feedrate: float | None = None,
    spindle_speed: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    machine_profile: str | None = None,
    postprocessor: str = "fanuc",
) -> dict:
    """Full deterministic facing pipeline from typed parameters to G-code.

    Steps:
        1. build_milling_facing_operation_plan(...)  — construct OperationPlan
        2. normalize_operation_plan(...)             — canonicalise field names
        3. validate_operation_plan(...)              — structural safety check
        4. postprocess_operations(...)               — G-code + G-code validation
           (only executed if plan has no errors)

    No LLM, no API key, no free-text interpretation.
    No cutter compensation. No tool radius offset. Review output before use.

    Returns:
        {
          "ok": bool,
          "machine_type": "mill",
          "operation_plan": dict,
          "gcode": str,
          "validation": dict,
          "warnings": list[str],
          "errors": list[str],
          "postprocessor": str,
          "machine_profile": str | None,
        }
    """
    try:
        from cnc.tools.operation_plan_tools import normalize_operation_plan
        from cnc.tools.validation_tools import validate_operation_plan
        from cnc.tools.postprocess_tools import postprocess_operations

        # 1. Build plan
        operation_plan = build_milling_facing_operation_plan(
            origin_x=origin_x,
            origin_y=origin_y,
            width=width,
            height=height,
            depth=depth,
            step_over=step_over,
            tool_diameter=tool_diameter,
            safe_z=safe_z,
            feedrate=feedrate,
            spindle_speed=spindle_speed,
            units=units,
            work_coordinate_system=work_coordinate_system,
            material=material,
            machine_profile=machine_profile,
            postprocessor=postprocessor,
        )

        # 2. Normalise field names
        normalized = normalize_operation_plan(operation_plan)

        # 3. Validate plan structure
        plan_val = validate_operation_plan(normalized)

        if plan_val.get("errors"):
            return {
                "ok": False,
                "machine_type": "mill",
                "operation_plan": normalized,
                "gcode": "",
                "validation": plan_val,
                "warnings": list({
                    *operation_plan.get("warnings", []),
                    *plan_val.get("warnings", []),
                }),
                "errors": plan_val.get("errors", []),
                "postprocessor": postprocessor,
                "machine_profile": machine_profile,
            }

        # 4. Postprocess
        pp_result = postprocess_operations(normalized, postprocessor=postprocessor)

        # Merge and deduplicate warnings
        all_warnings = (
            operation_plan.get("warnings", [])
            + pp_result.get("warnings", [])
        )
        seen: set[str] = set()
        deduped: list[str] = []
        for w in all_warnings:
            if w not in seen:
                seen.add(w)
                deduped.append(w)

        return {
            "ok": pp_result.get("ok", False),
            "machine_type": "mill",
            "operation_plan": normalized,
            "gcode": pp_result.get("gcode") or "",
            "validation": pp_result.get("validation", {}),
            "warnings": deduped,
            "errors": pp_result.get("errors", []),
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "mill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"Unexpected error in generate_milling_facing_gcode_from_params: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }


# ---------------------------------------------------------------------------
# Milling slot
# ---------------------------------------------------------------------------

_VALID_DIRECTIONS = {"x", "y"}


def build_milling_slot_operation_plan(
    start_x: float,
    start_y: float,
    length: float,
    depth: float,
    tool_diameter: float,
    safe_z: float | None = None,
    feedrate: float | None = None,
    spindle_speed: float | None = None,
    direction: str = "x",
    step_down: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    machine_profile: str | None = None,
    postprocessor: str = "fanuc",
) -> dict:
    """Build a structured OperationPlan dict for a straight slot milling operation.

    Does NOT call the postprocessor. Use generate_milling_slot_gcode_from_params
    for the full validate → postprocess → validate G-code pipeline.

    Args:
        start_x: X start position of the slot centerline.
        start_y: Y start position of the slot centerline.
        length: Slot length along the chosen direction (must be > 0).
        depth: Total cutting depth as a positive number (e.g. 3 → Z=-3).
               Negative values are accepted: interpreted as target Z with a warning.
        tool_diameter: End mill diameter — also defines slot width (must be > 0).
        safe_z: Safe retract height. Filled from profile if None.
        feedrate: Cutting feedrate (units/min). Filled from profile if None.
        spindle_speed: Spindle speed in RPM. If None, M03 will be skipped.
        direction: "x" (slot along X axis) or "y" (slot along Y axis).
        step_down: Z depth per pass (must be > 0). If None, missing_info is set.
                   If step_down > depth, a warning is added but one pass is allowed.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code, e.g. "G54".
        material: Optional material description.
        machine_profile: Name of a built-in machine profile for defaults.
        postprocessor: Intended postprocessor (informational at this stage).

    Returns:
        A canonical OperationPlan dict ready for validate_operation_plan and
        postprocess_operations.
    """
    from cnc.tools.machine_profiles import get_machine_profile

    assumptions: list[str] = []
    warnings: list[str] = []
    missing_info: list[str] = []

    # --- Apply machine profile defaults ---
    resolved_safe_z = safe_z
    resolved_feedrate = feedrate
    resolved_spindle = spindle_speed

    if machine_profile is not None:
        profile = get_machine_profile(machine_profile)
        if profile is None:
            warnings.append(
                f"Machine profile '{machine_profile}' is not recognised. "
                "Profile defaults not applied."
            )
        else:
            units = profile.get("units", units)
            work_coordinate_system = profile.get(
                "work_coordinate_system", work_coordinate_system
            )
            if resolved_safe_z is None and profile.get("default_safe_z") is not None:
                resolved_safe_z = float(profile["default_safe_z"])
            if resolved_feedrate is None and profile.get("default_feedrate") is not None:
                resolved_feedrate = float(profile["default_feedrate"])
            if resolved_spindle is None and profile.get("default_spindle_speed") is not None:
                resolved_spindle = float(profile["default_spindle_speed"])

    # --- Normalise depth to negative Z target ---
    if depth < 0:
        target_z = float(depth)
        warnings.append(
            "Depth was provided as negative value and was interpreted as target Z "
            f"(target_z={depth})."
        )
    else:
        target_z = -abs(float(depth))

    # --- Validate direction ---
    direction_clean = str(direction).strip().lower()
    if direction_clean not in _VALID_DIRECTIONS:
        warnings.append(
            f"Direction '{direction}' is not valid. Must be 'x' or 'y'. "
            "Keeping value as-is for validator to catch."
        )

    # --- Validate geometry ---
    if length is None or length <= 0:
        warnings.append(f"Length={length} is not positive — slot has no extent.")
        missing_info.append("length")

    if tool_diameter is None or tool_diameter <= 0:
        warnings.append(f"Tool diameter={tool_diameter} is not positive.")
        missing_info.append("tool_diameter")

    # --- step_down validation ---
    resolved_step_down = step_down
    if resolved_step_down is None:
        warnings.append("Step-down was not specified.")
        missing_info.append("step_down")
    elif resolved_step_down <= 0:
        warnings.append(f"Step-down={resolved_step_down} is not positive.")
    elif abs(target_z) > 0 and resolved_step_down > abs(target_z):
        warnings.append(
            f"Step-down ({resolved_step_down}) is greater than total depth "
            f"({abs(target_z)}). A single pass to target_z will be used."
        )

    # --- Missing required params ---
    if resolved_feedrate is None:
        warnings.append("Feedrate was not specified.")
        missing_info.append("feedrate")

    if resolved_safe_z is None:
        warnings.append("Safe Z was not specified.")
        missing_info.append("safe_z")

    if resolved_spindle is None:
        warnings.append(
            "Spindle speed was not specified. "
            "Spindle start (M03) will be skipped in generated G-code."
        )
        missing_info.append("spindle_speed")

    # --- Material & slot-width assumption ---
    if material:
        assumptions.append(f"Material: {material}")
    else:
        assumptions.append("Material was not specified.")
    assumptions.append("Slot width is assumed to equal tool diameter.")

    # Slot width assumption warning
    warnings.append(
        "Slot width is not modeled separately; using tool diameter as slot width."
    )

    # --- Tool ---
    td = tool_diameter if tool_diameter and tool_diameter > 0 else 0
    tool: dict = {
        "id": "T1",
        "name": f"{td:g}{units} end mill",
        "diameter": td,
        "units": units,
    }
    if resolved_feedrate is not None:
        tool["feedrate"] = resolved_feedrate
    if resolved_spindle is not None:
        tool["spindle_speed"] = resolved_spindle

    # --- Operation ---
    ll = length if length and length > 0 else 0
    op: dict = {
        "type": "slot",
        "description": (
            f"Mill straight slot from X{float(start_x):g} Y{float(start_y):g} "
            f"along {direction_clean}-direction, length={ll:g}{units}, "
            f"depth={abs(target_z):g}{units}"
        ),
        "tool_id": "T1",
        "parameters": {
            "start_x": float(start_x),
            "start_y": float(start_y),
            "length": float(ll),
            "target_z": target_z,
            "direction": direction_clean,
            "step_down": float(resolved_step_down) if resolved_step_down is not None else None,
            "tool_diameter": float(td),
        },
    }
    if resolved_feedrate is not None:
        op["feedrate"] = resolved_feedrate
    if resolved_spindle is not None:
        op["spindle_speed"] = resolved_spindle

    return {
        "machine_type": "mill",
        "units": units,
        "work_coordinate_system": work_coordinate_system,
        "safe_z": resolved_safe_z,
        "tools": [tool],
        "operations": [op],
        "assumptions": assumptions,
        "warnings": warnings,
        "missing_info": missing_info,
    }


def generate_milling_slot_gcode_from_params(
    start_x: float,
    start_y: float,
    length: float,
    depth: float,
    tool_diameter: float,
    safe_z: float | None = None,
    feedrate: float | None = None,
    spindle_speed: float | None = None,
    direction: str = "x",
    step_down: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    machine_profile: str | None = None,
    postprocessor: str = "fanuc",
) -> dict:
    """Full deterministic slot pipeline from typed parameters to G-code.

    Steps:
        1. build_milling_slot_operation_plan(...)  — construct OperationPlan
        2. normalize_operation_plan(...)           — canonicalise field names
        3. validate_operation_plan(...)            — structural safety check
        4. postprocess_operations(...)             — G-code + G-code validation
           (only executed if plan has no errors)

    No LLM, no API key, no free-text interpretation.
    No cutter compensation. Slot width equals tool diameter. Review output before use.

    Returns:
        {
          "ok": bool,
          "machine_type": "mill",
          "operation_plan": dict,
          "gcode": str,
          "validation": dict,
          "warnings": list[str],
          "errors": list[str],
          "postprocessor": str,
          "machine_profile": str | None,
        }
    """
    try:
        from cnc.tools.operation_plan_tools import normalize_operation_plan
        from cnc.tools.validation_tools import validate_operation_plan
        from cnc.tools.postprocess_tools import postprocess_operations

        # 1. Build plan
        operation_plan = build_milling_slot_operation_plan(
            start_x=start_x,
            start_y=start_y,
            length=length,
            depth=depth,
            tool_diameter=tool_diameter,
            safe_z=safe_z,
            feedrate=feedrate,
            spindle_speed=spindle_speed,
            direction=direction,
            step_down=step_down,
            units=units,
            work_coordinate_system=work_coordinate_system,
            material=material,
            machine_profile=machine_profile,
            postprocessor=postprocessor,
        )

        # 2. Normalise
        normalized = normalize_operation_plan(operation_plan)

        # 3. Validate
        plan_val = validate_operation_plan(normalized)

        if plan_val.get("errors"):
            return {
                "ok": False,
                "machine_type": "mill",
                "operation_plan": normalized,
                "gcode": "",
                "validation": plan_val,
                "warnings": list({
                    *operation_plan.get("warnings", []),
                    *plan_val.get("warnings", []),
                }),
                "errors": plan_val.get("errors", []),
                "postprocessor": postprocessor,
                "machine_profile": machine_profile,
            }

        # 4. Postprocess
        pp_result = postprocess_operations(normalized, postprocessor=postprocessor)

        all_warnings = (
            operation_plan.get("warnings", [])
            + pp_result.get("warnings", [])
        )
        seen: set[str] = set()
        deduped: list[str] = []
        for w in all_warnings:
            if w not in seen:
                seen.add(w)
                deduped.append(w)

        return {
            "ok": pp_result.get("ok", False),
            "machine_type": "mill",
            "operation_plan": normalized,
            "gcode": pp_result.get("gcode") or "",
            "validation": pp_result.get("validation", {}),
            "warnings": deduped,
            "errors": pp_result.get("errors", []),
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "mill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"Unexpected error in generate_milling_slot_gcode_from_params: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }


# ---------------------------------------------------------------------------
# Milling pocket
# ---------------------------------------------------------------------------


def build_milling_pocket_operation_plan(
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    depth: float,
    tool_diameter: float,
    step_down: float | None = None,
    step_over: float | None = None,
    safe_z: float | None = None,
    feedrate: float | None = None,
    spindle_speed: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    machine_profile: str | None = None,
    postprocessor: str = "fanuc",
) -> dict:
    """Build a structured OperationPlan dict for a rectangular pocket operation.

    Does NOT call the postprocessor. Use generate_milling_pocket_gcode_from_params
    for the full validate -> postprocess -> validate G-code pipeline.

    Args:
        origin_x: X position of the lower-left corner of the pocket.
        origin_y: Y position of the lower-left corner of the pocket.
        width: Pocket width along X (must be > 0).
        height: Pocket height along Y (must be > 0).
        depth: Total cutting depth as a positive number (e.g. 3 -> cuts to Z=-3).
               Negative values are accepted: interpreted as target Z with a warning.
        tool_diameter: End mill diameter (must be > 0).
        step_down: Z depth per pass (must be > 0). None -> missing_info.
        step_over: Radial step-over per raster pass (must be > 0). None -> missing_info.
                   Values > tool_diameter produce a warning (may leave uncut material).
        safe_z: Safe retract height above workpiece. Filled from profile if None.
        feedrate: Cutting feedrate (units/min). Filled from profile if None.
        spindle_speed: Spindle speed in RPM. If None, M03 will be skipped.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code, e.g. "G54".
        material: Optional material description.
        machine_profile: Name of a built-in machine profile for defaults.
        postprocessor: Intended postprocessor (informational at this stage).

    Returns:
        A canonical OperationPlan dict ready for validate_operation_plan and
        postprocess_operations.
    """
    from cnc.tools.machine_profiles import get_machine_profile

    assumptions: list[str] = []
    warnings: list[str] = []
    missing_info: list[str] = []

    # --- Apply machine profile defaults ---
    resolved_safe_z = safe_z
    resolved_feedrate = feedrate
    resolved_spindle = spindle_speed

    if machine_profile is not None:
        profile = get_machine_profile(machine_profile)
        if profile is None:
            warnings.append(
                f"Machine profile '{machine_profile}' is not recognised. "
                "Profile defaults not applied."
            )
        else:
            units = profile.get("units", units)
            work_coordinate_system = profile.get(
                "work_coordinate_system", work_coordinate_system
            )
            if resolved_safe_z is None and profile.get("default_safe_z") is not None:
                resolved_safe_z = float(profile["default_safe_z"])
            if resolved_feedrate is None and profile.get("default_feedrate") is not None:
                resolved_feedrate = float(profile["default_feedrate"])
            if resolved_spindle is None and profile.get("default_spindle_speed") is not None:
                resolved_spindle = float(profile["default_spindle_speed"])

    # --- Normalise depth to negative Z target ---
    if depth < 0:
        target_z = float(depth)
        warnings.append(
            "Depth was provided as negative value and was interpreted as target Z "
            f"(target_z={depth})."
        )
    else:
        target_z = -abs(float(depth))

    # --- Validate geometry ---
    if width is None or width <= 0:
        warnings.append(f"Width={width} is not positive — pocket area is degenerate.")
        missing_info.append("width")

    if height is None or height <= 0:
        warnings.append(f"Height={height} is not positive — pocket area is degenerate.")
        missing_info.append("height")

    if tool_diameter is None or tool_diameter <= 0:
        warnings.append(f"Tool diameter={tool_diameter} is not positive.")
        missing_info.append("tool_diameter")

    # --- step_down ---
    resolved_step_down = step_down
    if resolved_step_down is None:
        warnings.append("Step-down was not specified.")
        missing_info.append("step_down")
    elif resolved_step_down <= 0:
        warnings.append(f"Step-down={resolved_step_down} is not positive.")
    elif abs(target_z) > 0 and resolved_step_down > abs(target_z):
        warnings.append(
            f"Step-down ({resolved_step_down}) is greater than total depth "
            f"({abs(target_z)}). A single pass to target_z will be used."
        )

    # --- step_over ---
    resolved_step_over = step_over
    if resolved_step_over is None:
        warnings.append("Step-over was not specified.")
        missing_info.append("step_over")
    elif resolved_step_over <= 0:
        warnings.append(f"Step-over={resolved_step_over} is not positive.")
    elif tool_diameter and tool_diameter > 0 and resolved_step_over > tool_diameter:
        warnings.append(
            f"Step-over ({resolved_step_over}) is larger than tool diameter "
            f"({tool_diameter}) and may leave uncut material."
        )

    # Warn if pocket smaller than tool
    td = tool_diameter if tool_diameter and tool_diameter > 0 else 0
    w = width if width and width > 0 else 0
    h = height if height and height > 0 else 0
    if td > 0 and w > 0 and w < td:
        warnings.append(
            f"Pocket width ({w}) is smaller than tool diameter ({td}). "
            "The pocket cannot be milled with this tool."
        )
    if td > 0 and h > 0 and h < td:
        warnings.append(
            f"Pocket height ({h}) is smaller than tool diameter ({td}). "
            "The pocket cannot be milled with this tool."
        )

    # --- Missing required params ---
    if resolved_feedrate is None:
        warnings.append("Feedrate was not specified.")
        missing_info.append("feedrate")

    if resolved_safe_z is None:
        warnings.append("Safe Z was not specified.")
        missing_info.append("safe_z")

    if resolved_spindle is None:
        warnings.append(
            "Spindle speed was not specified. "
            "Spindle start (M03) will be skipped in generated G-code."
        )

    # --- Material & strategy assumptions ---
    if material:
        assumptions.append(f"Material: {material}")
    else:
        assumptions.append("Material was not specified.")
    assumptions.append("Pocket toolpath is a simple raster clearing strategy.")
    assumptions.append("No cutter compensation is applied.")

    # --- Tool ---
    tool: dict = {
        "id": "T1",
        "name": f"{td:g}{units} end mill",
        "diameter": td,
        "units": units,
    }
    if resolved_feedrate is not None:
        tool["feedrate"] = resolved_feedrate
    if resolved_spindle is not None:
        tool["spindle_speed"] = resolved_spindle

    # --- Operation ---
    so = resolved_step_over if resolved_step_over and resolved_step_over > 0 else None
    sd = resolved_step_down if resolved_step_down and resolved_step_down > 0 else None

    op: dict = {
        "type": "pocket",
        "description": (
            f"Mill rectangular pocket {w:g}x{h:g}{units} "
            f"at origin X{float(origin_x):g} Y{float(origin_y):g} "
            f"to depth {abs(target_z):g}{units}"
        ),
        "tool_id": "T1",
        "parameters": {
            "origin_x": float(origin_x),
            "origin_y": float(origin_y),
            "width": float(w),
            "height": float(h),
            "target_z": target_z,
            "step_down": float(sd) if sd is not None else None,
            "step_over": float(so) if so is not None else None,
            "tool_diameter": float(td),
        },
    }
    if resolved_feedrate is not None:
        op["feedrate"] = resolved_feedrate
    if resolved_spindle is not None:
        op["spindle_speed"] = resolved_spindle

    return {
        "machine_type": "mill",
        "units": units,
        "work_coordinate_system": work_coordinate_system,
        "safe_z": resolved_safe_z,
        "tools": [tool],
        "operations": [op],
        "assumptions": assumptions,
        "warnings": warnings,
        "missing_info": missing_info,
    }


def generate_milling_pocket_gcode_from_params(
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    depth: float,
    tool_diameter: float,
    step_down: float | None = None,
    step_over: float | None = None,
    safe_z: float | None = None,
    feedrate: float | None = None,
    spindle_speed: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    machine_profile: str | None = None,
    postprocessor: str = "fanuc",
) -> dict:
    """Full deterministic pocket pipeline from typed parameters to G-code.

    Steps:
        1. build_milling_pocket_operation_plan(...)  -- construct OperationPlan
        2. normalize_operation_plan(...)             -- canonicalise field names
        3. validate_operation_plan(...)              -- structural safety check
        4. postprocess_operations(...)               -- G-code + G-code validation
           (only executed if plan has no errors)

    No LLM, no API key, no free-text interpretation.
    No cutter compensation. Simple raster clearing strategy. Review output before use.

    Returns:
        {
          "ok": bool,
          "machine_type": "mill",
          "operation_plan": dict,
          "gcode": str,
          "validation": dict,
          "warnings": list[str],
          "errors": list[str],
          "postprocessor": str,
          "machine_profile": str | None,
        }
    """
    try:
        from cnc.tools.operation_plan_tools import normalize_operation_plan
        from cnc.tools.validation_tools import validate_operation_plan
        from cnc.tools.postprocess_tools import postprocess_operations

        # 1. Build plan
        operation_plan = build_milling_pocket_operation_plan(
            origin_x=origin_x,
            origin_y=origin_y,
            width=width,
            height=height,
            depth=depth,
            tool_diameter=tool_diameter,
            step_down=step_down,
            step_over=step_over,
            safe_z=safe_z,
            feedrate=feedrate,
            spindle_speed=spindle_speed,
            units=units,
            work_coordinate_system=work_coordinate_system,
            material=material,
            machine_profile=machine_profile,
            postprocessor=postprocessor,
        )

        # 2. Normalise field names
        normalized = normalize_operation_plan(operation_plan)

        # 3. Validate plan structure
        plan_val = validate_operation_plan(normalized)

        if plan_val.get("errors"):
            return {
                "ok": False,
                "machine_type": "mill",
                "operation_plan": normalized,
                "gcode": "",
                "validation": plan_val,
                "warnings": list({
                    *operation_plan.get("warnings", []),
                    *plan_val.get("warnings", []),
                }),
                "errors": plan_val.get("errors", []),
                "postprocessor": postprocessor,
                "machine_profile": machine_profile,
            }

        # 4. Postprocess
        pp_result = postprocess_operations(normalized, postprocessor=postprocessor)

        all_warnings = (
            operation_plan.get("warnings", [])
            + pp_result.get("warnings", [])
        )
        seen: set[str] = set()
        deduped: list[str] = []
        for w in all_warnings:
            if w not in seen:
                seen.add(w)
                deduped.append(w)

        return {
            "ok": pp_result.get("ok", False),
            "machine_type": "mill",
            "operation_plan": normalized,
            "gcode": pp_result.get("gcode") or "",
            "validation": pp_result.get("validation", {}),
            "warnings": deduped,
            "errors": pp_result.get("errors", []),
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "mill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"Unexpected error in generate_milling_pocket_gcode_from_params: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }
