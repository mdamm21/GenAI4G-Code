"""Drill tools — typed, deterministic helpers for drill operations.

This module provides a safe, parameter-driven path for generating drill G-code
without an LLM or API key. It backs the MCP tools `generate_drill_gcode`
(single hole) and `generate_drill_pattern_gcode` (multiple holes).

Pipeline:
    build_drill_operation_plan(...)          — single hole → OperationPlan dict
    generate_drill_gcode_from_params(...)    — validate → postprocess → validate G-code

    build_drill_pattern_operation_plan(...)  — N holes → OperationPlan dict
    generate_drill_pattern_gcode_from_params(...) — same pipeline for N holes
"""

from __future__ import annotations


def build_drill_operation_plan(
    x: float,
    y: float,
    depth: float,
    tool_diameter: float,
    safe_z: float,
    feedrate: float,
    spindle_speed: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    postprocessor: str = "fanuc",
    tool_id: str | None = None,
) -> dict:
    """Build a structured OperationPlan dict from explicit drill parameters.

    Does NOT call the postprocessor. Use generate_drill_gcode_from_params for
    the full validate → postprocess → validate pipeline.

    Args:
        x: Hole X position (in `units`).
        y: Hole Y position (in `units`).
        depth: Drill depth as a positive number (e.g. 5 means 5mm below surface).
               Negative values are accepted and normalised — a warning is added.
        tool_diameter: Drill bit diameter (in `units`).
        safe_z: Safe retract height above the workpiece (positive, in `units`).
        feedrate: Drill feedrate (units/min).
        spindle_speed: Spindle speed in RPM. If None, M03 will be skipped and a
                       warning is added.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code, e.g. "G54" (default).
        material: Optional material description for documentation purposes.
        postprocessor: Intended postprocessor name (informational only at this stage).

    Returns:
        A canonical OperationPlan dict ready for validate_operation_plan and
        postprocess_operations.
    """
    assumptions: list[str] = []
    warnings: list[str] = []

    # --- Normalise depth to a negative Z target ---
    z_target: float
    if depth < 0:
        z_target = depth  # already negative
        warnings.append(
            "Depth was provided as a negative value and was interpreted as target Z "
            f"(z={depth})."
        )
    else:
        z_target = -abs(depth)

    # --- Material ---
    if material:
        assumptions.append(f"Material: {material}")
        from cnc.tools.material_library import normalize_material
        mat_result = normalize_material(material)
        if not mat_result.get("ok"):
            warnings.extend(mat_result.get("warnings", []))
    else:
        assumptions.append("Material was not specified.")

    # --- Spindle warning ---
    if spindle_speed is None:
        warnings.append(
            "Spindle speed was not specified. "
            "Spindle start (M03) will be skipped in generated G-code."
        )

    # --- Tool ---
    resolved_tool_id = tool_id if tool_id else "T1"
    tool: dict = {
        "id": resolved_tool_id,
        "name": f"{tool_diameter:g}{units} drill",
        "diameter": tool_diameter,
        "units": units,
        "feedrate": feedrate,
    }
    if spindle_speed is not None:
        tool["spindle_speed"] = spindle_speed

    # --- Operation ---
    operation: dict = {
        "type": "drill",
        "description": (
            f"Drill one hole at X{x:g} Y{y:g} to depth {abs(z_target):g}{units}"
        ),
        "tool_id": resolved_tool_id,
        "parameters": {
            "x": float(x),
            "y": float(y),
            "z": z_target,
        },
        "feedrate": feedrate,
    }
    if spindle_speed is not None:
        operation["spindle_speed"] = spindle_speed

    plan: dict = {
        "machine_type": "drill",
        "units": units,
        "work_coordinate_system": work_coordinate_system,
        "safe_z": safe_z,
        "tools": [tool],
        "operations": [operation],
        "assumptions": assumptions,
        "warnings": warnings,
        "missing_info": [],
    }
    if material:
        plan["material"] = material
    return plan


def generate_drill_gcode_from_params(
    x: float,
    y: float,
    depth: float,
    tool_diameter: float,
    safe_z: float,
    feedrate: float,
    spindle_speed: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    postprocessor: str = "fanuc",
) -> dict:
    """Full deterministic drill pipeline from typed parameters to G-code.

    Steps:
        1. build_drill_operation_plan(...)   — construct OperationPlan
        2. normalize_operation_plan(...)     — canonicalise field names
        3. validate_operation_plan(...)      — structural safety check
        4. postprocess_operations(...)       — G-code generation + G-code validation
           (only executed if plan has no errors)

    No LLM, no API key, no free-text interpretation.

    Args:
        x, y, depth, tool_diameter, safe_z, feedrate, spindle_speed,
        units, work_coordinate_system, material, postprocessor:
            See build_drill_operation_plan for full documentation.

    Returns:
        {
          "ok": bool,
          "machine_type": "drill",
          "operation_plan": dict,
          "gcode": str,          # empty string if validation failed
          "validation": dict,    # G-code validation or plan validation on early exit
          "warnings": list[str],
          "errors": list[str],
          "postprocessor": str,
        }
    """
    try:
        from cnc.tools.operation_plan_tools import normalize_operation_plan
        from cnc.tools.validation_tools import validate_operation_plan
        from cnc.tools.postprocess_tools import postprocess_operations

        # 1. Build plan
        operation_plan = build_drill_operation_plan(
            x=x,
            y=y,
            depth=depth,
            tool_diameter=tool_diameter,
            safe_z=safe_z,
            feedrate=feedrate,
            spindle_speed=spindle_speed,
            units=units,
            work_coordinate_system=work_coordinate_system,
            material=material,
            postprocessor=postprocessor,
        )

        # 2. Normalise field names (tool_id → tool_number, etc.)
        normalized = normalize_operation_plan(operation_plan)

        # 3. Validate plan structure
        plan_val = validate_operation_plan(normalized)

        if plan_val.get("errors"):
            return {
                "ok": False,
                "machine_type": "drill",
                "operation_plan": normalized,
                "gcode": "",
                "validation": plan_val,
                "warnings": plan_val.get("warnings", []) + operation_plan.get("warnings", []),
                "errors": plan_val.get("errors", []),
                "postprocessor": postprocessor,
            }

        # 4. Postprocess (includes G-code validation internally)
        pp_result = postprocess_operations(normalized, postprocessor=postprocessor)

        # Merge plan warnings (from build step) with postprocess warnings
        all_warnings = (
            operation_plan.get("warnings", [])
            + pp_result.get("warnings", [])
        )
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped_warnings: list[str] = []
        for w in all_warnings:
            if w not in seen:
                seen.add(w)
                deduped_warnings.append(w)

        return {
            "ok": pp_result.get("ok", False),
            "machine_type": "drill",
            "operation_plan": normalized,
            "gcode": pp_result.get("gcode") or "",
            "validation": pp_result.get("validation", {}),
            "warnings": deduped_warnings,
            "errors": pp_result.get("errors", []),
            "postprocessor": postprocessor,
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "drill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"Unexpected error in generate_drill_gcode_from_params: {exc}"],
            "postprocessor": postprocessor,
        }


# ---------------------------------------------------------------------------
# Multi-hole drill pattern
# ---------------------------------------------------------------------------


def build_drill_pattern_operation_plan(
    holes: list[dict],
    tool_diameter: float,
    safe_z: float | None = None,
    feedrate: float | None = None,
    spindle_speed: float | None = None,
    units: str = "mm",
    work_coordinate_system: str = "G54",
    material: str | None = None,
    machine_profile: str | None = None,
    postprocessor: str = "fanuc",
    tool_id: str | None = None,
) -> dict:
    """Build a structured OperationPlan dict for a multi-hole drill pattern.

    Does NOT call the postprocessor. Use generate_drill_pattern_gcode_from_params
    for the full validate → postprocess → validate G-code pipeline.

    Args:
        holes: List of dicts, each with keys ``x``, ``y``, ``depth``.
               ``depth`` is positive (e.g. 5 → drills to Z=-5).
               Negative depth values are accepted and normalised with a warning.
        tool_diameter: Drill bit diameter (in ``units``).
        safe_z: Safe retract height above the workpiece. If None and a profile
                provides a default, the profile value is used.
        feedrate: Drill feedrate (units/min). If None, the profile default is
                  used if available.
        spindle_speed: Spindle speed in RPM. If None, M03 will be skipped.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code, e.g. "G54".
        material: Optional material description.
        machine_profile: Name of a built-in machine profile to supply defaults
                         for safe_z, feedrate, spindle_speed. Unknown names
                         produce a warning.
        postprocessor: Intended postprocessor (informational at this stage).

    Returns:
        A canonical OperationPlan dict ready for validate_operation_plan and
        postprocess_operations.
    """
    from cnc.tools.machine_profiles import get_machine_profile

    assumptions: list[str] = []
    warnings: list[str] = []
    missing_info: list[str] = []

    # --- Apply machine profile defaults (None params only) ---
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
            # Apply profile-level settings — profile is the authoritative source
            # for units and WCS since they define how the machine interprets coordinates.
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

    # --- Validate inputs ---
    if not holes:
        missing_info.append("holes")

    if tool_diameter is None or tool_diameter <= 0:
        missing_info.append("tool_diameter")

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

    if material:
        assumptions.append(f"Material: {material}")
        from cnc.tools.material_library import normalize_material
        mat_result = normalize_material(material)
        if not mat_result.get("ok"):
            warnings.extend(mat_result.get("warnings", []))
    else:
        assumptions.append("Material was not specified.")

    # --- Build tool ---
    resolved_tool_id = tool_id if tool_id else "T1"
    td = tool_diameter if tool_diameter and tool_diameter > 0 else 0
    tool: dict = {
        "id": resolved_tool_id,
        "name": f"{td:g}{units} drill",
        "diameter": td,
        "units": units,
    }
    if resolved_feedrate is not None:
        tool["feedrate"] = resolved_feedrate
    if resolved_spindle is not None:
        tool["spindle_speed"] = resolved_spindle

    # --- Build operations (one per hole) ---
    operations: list[dict] = []
    for idx, hole in enumerate(holes):
        if not isinstance(hole, dict):
            warnings.append(f"Hole {idx} is not a dict and was skipped.")
            continue

        hx = float(hole.get("x", 0.0))
        hy = float(hole.get("y", 0.0))
        raw_depth = hole.get("depth")

        if raw_depth is None:
            warnings.append(f"Hole {idx} has no depth specified — using 0 (will fail validation).")
            raw_depth = 0.0

        raw_depth_f = float(raw_depth)
        if raw_depth_f < 0:
            z_target = raw_depth_f
            warnings.append(
                f"Hole {idx} depth was provided as a negative value and was "
                f"interpreted as target Z (z={raw_depth_f})."
            )
        else:
            z_target = -abs(raw_depth_f)

        op: dict = {
            "type": "drill",
            "description": (
                f"Drill hole {idx} at X{hx:g} Y{hy:g} to depth {abs(z_target):g}{units}"
            ),
            "tool_id": resolved_tool_id,
            "parameters": {
                "x": hx,
                "y": hy,
                "z": z_target,
            },
        }
        if resolved_feedrate is not None:
            op["feedrate"] = resolved_feedrate
        if resolved_spindle is not None:
            op["spindle_speed"] = resolved_spindle

        operations.append(op)

    plan: dict = {
        "machine_type": "drill",
        "units": units,
        "work_coordinate_system": work_coordinate_system,
        "safe_z": resolved_safe_z,
        "tools": [tool],
        "operations": operations,
        "assumptions": assumptions,
        "warnings": warnings,
        "missing_info": missing_info,
    }
    if material:
        plan["material"] = material
    return plan


def generate_drill_pattern_gcode_from_params(
    holes: list[dict],
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
    """Full deterministic multi-hole drill pipeline from typed parameters to G-code.

    Steps:
        1. build_drill_pattern_operation_plan(...)  — construct OperationPlan
        2. normalize_operation_plan(...)            — canonicalise field names
        3. validate_operation_plan(...)             — structural safety check
        4. postprocess_operations(...)              — G-code + G-code validation
           (only executed if plan has no errors)

    No LLM, no API key, no free-text interpretation.

    Returns:
        {
          "ok": bool,
          "machine_type": "drill",
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
        operation_plan = build_drill_pattern_operation_plan(
            holes=holes,
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
                "machine_type": "drill",
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
            "machine_type": "drill",
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
            "machine_type": "drill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"Unexpected error in generate_drill_pattern_gcode_from_params: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }
