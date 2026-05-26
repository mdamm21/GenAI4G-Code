"""Drill tools — typed, deterministic helpers for single-hole drill operations.

This module provides a safe, parameter-driven path for generating drill G-code
without an LLM or API key. It is the backing implementation for the
MCP tool `generate_drill_gcode`.

Pipeline:
    build_drill_operation_plan(...)   — builds OperationPlan dict from typed params
    generate_drill_gcode_from_params(...) — validate → postprocess → validate G-code
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
    else:
        assumptions.append("Material was not specified.")

    # --- Spindle warning ---
    if spindle_speed is None:
        warnings.append(
            "Spindle speed was not specified. "
            "Spindle start (M03) will be skipped in generated G-code."
        )

    # --- Tool ---
    tool: dict = {
        "id": "T1",
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
        "tool_id": "T1",
        "parameters": {
            "x": float(x),
            "y": float(y),
            "z": z_target,
        },
        "feedrate": feedrate,
    }
    if spindle_speed is not None:
        operation["spindle_speed"] = spindle_speed

    return {
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
