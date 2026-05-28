"""CNC MCP Server — outer tool API for the CNC G-code generation system.

Exposes CNC tools via the Model Context Protocol (MCP).
The DeepAgent (cnc.agent) is the internal orchestrator — never called directly by users.

Architecture:
    MCP client -> cnc/server.py (tool API)
               -> cnc/agent.py  (orchestrator, next step)
               -> cnc/tools/*   (validation, postprocessing)
               -> cnc/validators/*  (G-code safety checks)
               -> cnc/postprocessors/* (deterministic G-code generation)

Start with:
    python -m cnc.server

Or via MCP client configuration:
    {
      "command": "python",
      "args": ["-m", "cnc.server"],
      "transport": "stdio"
    }
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# FastMCP setup
# ---------------------------------------------------------------------------

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "mcp package is required. Install with: pip install mcp[cli]"
    ) from exc

from cnc.tools.postprocess_tools import postprocess_operations
from cnc.tools.validation_tools import validate_operation_plan
from cnc.validators.gcode_validator import validate_gcode_text
from cnc.tools.drill_tools import (
    generate_drill_gcode_from_params,
    generate_drill_pattern_gcode_from_params,
)
from cnc.tools.milling_tools import (
    generate_milling_facing_gcode_from_params,
    generate_milling_slot_gcode_from_params,
    generate_milling_pocket_gcode_from_params,
)
from cnc.tools.machine_profiles import list_machine_profiles, get_machine_profile
from cnc.tools.material_library import list_materials, get_material, find_materials
from cnc.tools.parameter_guardrails import evaluate_parameter_guardrails
from cnc.tools.job_io import (
    create_job_spec,
    validate_job_spec,
    job_spec_to_gcode,
    save_job_spec,
    load_job_spec,
)
from cnc.tools.job_runs import run_job, save_run_report, load_run_report

mcp = FastMCP("genai4g-cnc")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _error_response(
    errors: list[str],
    warnings: list[str] | None = None,
    machine_type: str | None = None,
) -> dict:
    """Return a standard structured error dict."""
    mt = machine_type or "unknown"
    return {
        "ok": False,
        "gcode": "",
        "operation_plan": None,
        "assumptions": [],
        "warnings": warnings or [],
        "errors": errors,
        "missing_info": [],
        "machine_type": machine_type,
        "validation": {
            "ok": False,
            "errors": errors,
            "warnings": warnings or [],
            "machine_type": mt,
        },
        "safety_report": None,
    }


def _normalize_agent_result(raw: object, machine_type: str | None) -> dict:
    """Normalise whatever the agent returns into the canonical response dict.

    The agent may return:
      - a well-formed dict (ideal)
      - a dict with partial keys (tolerated)
      - a plain string (treated as unstructured — refused as G-code)
      - anything else (treated as error)
    """
    if isinstance(raw, str):
        return _error_response(
            errors=["Agent returned unstructured output. Refusing to treat it as final G-code."],
            warnings=[f"Raw agent output (first 200 chars): {raw[:200]}"],
            machine_type=machine_type,
        )

    if not isinstance(raw, dict):
        return _error_response(
            errors=[f"Agent returned unexpected type: {type(raw).__name__}"],
            machine_type=machine_type,
        )

    # Ensure required keys exist with safe defaults
    result: dict = {
        "ok": raw.get("ok", True),
        "gcode": raw.get("gcode", ""),
        "operation_plan": raw.get("operation_plan"),
        "assumptions": raw.get("assumptions", []),
        "warnings": raw.get("warnings", []),
        "errors": raw.get("errors", []),
        "machine_type": raw.get("machine_type") or machine_type,
        "validation": raw.get("validation", {
            "ok": False,
            "errors": ["No validation result from agent."],
            "warnings": [],
            "machine_type": machine_type or "unknown",
        }),
        "missing_info": raw.get("missing_info", []),
    }

    # If the agent produced an operation_plan but no G-code, run postprocessor
    if result["operation_plan"] and not result["gcode"]:
        plan_val = validate_operation_plan(result["operation_plan"])
        if not plan_val.get("errors"):
            pp = postprocess_operations(result["operation_plan"], postprocessor="fanuc")
            if pp.get("ok"):
                result["gcode"] = pp["gcode"]
            else:
                result["errors"].extend(pp.get("errors", []))
                result["warnings"].extend(pp.get("warnings", []))

    # Validate G-code if present
    if result["gcode"]:
        mt = result["machine_type"] or "mill"
        gval = validate_gcode_text(result["gcode"], machine_type=mt)
        result["validation"] = gval
        result["ok"] = gval.get("ok", False)
    else:
        result.setdefault("ok", False)

    return result


# ---------------------------------------------------------------------------
# Tool 1: list_supported_machines
# ---------------------------------------------------------------------------


@mcp.tool()
def list_supported_machines() -> list[str]:
    """List all supported CNC machine types.

    Returns:
        List of supported machine type identifiers.
    """
    return ["mill", "lathe", "grinder", "drill", "3d_printer", "laser"]


# ---------------------------------------------------------------------------
# Tool 2: validate_gcode
# ---------------------------------------------------------------------------


@mcp.tool()
def validate_gcode(gcode: str, machine_type: str = "mill") -> dict:
    """Validate a G-code program for safety and completeness.

    Args:
        gcode: G-code program text to validate.
        machine_type: Target machine type (mill, lathe, laser, 3d_printer, drill, grinder).

    Returns:
        Validation result dict with keys: ok, errors, warnings, machine_type.
    """
    try:
        return validate_gcode_text(gcode, machine_type=machine_type)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [f"Validator raised unexpected exception: {exc}"],
            "warnings": [],
            "machine_type": machine_type,
        }


# ---------------------------------------------------------------------------
# Tool 3: validate_plan
# ---------------------------------------------------------------------------


@mcp.tool()
def validate_plan(operation_plan: dict) -> dict:
    """Validate a structured OperationPlan for completeness and safety.

    Checks for required fields: machine_type, units, safe_z, operations.
    Warns about missing feedrates and tool data.

    Args:
        operation_plan: Dict following the OperationPlan schema.

    Returns:
        Dict with keys: ok, errors, warnings.
    """
    try:
        return validate_operation_plan(operation_plan)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [f"Plan validator raised unexpected exception: {exc}"],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# Tool 4: postprocess_plan
# ---------------------------------------------------------------------------


@mcp.tool()
def postprocess_plan(operation_plan: dict, postprocessor: str = "fanuc") -> dict:
    """Convert a validated OperationPlan to G-code using a named postprocessor.

    Does NOT invoke the agent. Deterministic translation of an already-planned
    operation set into controller-specific G-code.

    Args:
        operation_plan: Validated OperationPlan dict.
        postprocessor: Postprocessor name (fanuc, grbl, marlin, linuxcnc).

    Returns:
        Dict with keys: ok, gcode, postprocessor, warnings, errors.
    """
    try:
        return postprocess_operations(operation_plan, postprocessor=postprocessor)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gcode": "",
            "postprocessor": postprocessor,
            "warnings": [],
            "errors": [f"Postprocessor raised unexpected exception: {exc}"],
        }


# ---------------------------------------------------------------------------
# Tool 5: generate_drill_gcode  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_drill_gcode(
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
    """Generate conservative Fanuc-style drilling G-code from explicit drilling parameters.

    This deterministic tool does NOT use an LLM. It builds a structured
    OperationPlan from the supplied parameters, validates the plan, runs the
    named postprocessor to produce G-code, and validates the resulting G-code.

    Args:
        x: Hole X position (in units).
        y: Hole Y position (in units).
        depth: Drill depth as a positive number (e.g. 5 → drills to Z=-5).
               Negative values are accepted and normalised with a warning.
        tool_diameter: Drill bit diameter (in units).
        safe_z: Safe retract height above the workpiece (positive, in units).
        feedrate: Drill feedrate in units/min.
        spindle_speed: Spindle speed in RPM. If omitted, M03 is skipped and a
                       warning is included in the response.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code (default "G54").
        material: Optional material description for documentation in the G-code header.
        postprocessor: "fanuc" (default), "grbl", "marlin", or "linuxcnc".

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
        }

    Safety note:
        Generated G-code is for review and simulation only.
        Never run on a real machine without expert verification.
    """
    try:
        return generate_drill_gcode_from_params(
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
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "drill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"generate_drill_gcode: unexpected error: {exc}"],
            "postprocessor": postprocessor,
        }


# ---------------------------------------------------------------------------
# Tool 6: list_profiles  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def list_profiles() -> list[dict]:
    """List all available built-in machine profiles.

    Returns:
        List of machine profile dicts, each with: name, machine_type, units,
        work_coordinate_system, default_safe_z, default_feedrate,
        default_spindle_speed, default_postprocessor, notes.
    """
    return list_machine_profiles()


# ---------------------------------------------------------------------------
# Tool 7: get_profile  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_profile(name: str) -> dict:
    """Get a built-in machine profile by name.

    Args:
        name: Profile name, e.g. "generic_drill_mm" or "generic_drill_inch".

    Returns:
        Dict with keys: ok, profile (or None if not found), error (on failure).
    """
    profile = get_machine_profile(name)
    if profile is None:
        return {
            "ok": False,
            "error": f"Unknown machine profile: {name!r}. "
                     "Use list_profiles() to see available profiles.",
            "profile": None,
        }
    return {
        "ok": True,
        "profile": profile,
    }


# ---------------------------------------------------------------------------
# Tool 8: generate_drill_pattern_gcode  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_drill_pattern_gcode(
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
    """Generate conservative drilling G-code for multiple explicit hole positions.

    This deterministic tool does NOT use an LLM. It accepts a list of hole
    coordinates, builds a structured OperationPlan, validates the plan, runs
    the named postprocessor to produce G-code, and validates the G-code.

    If a machine_profile is supplied, its defaults (safe_z, feedrate,
    spindle_speed) fill in any missing job parameters. Feedrate and spindle
    speed are never invented — missing values produce clear warnings or errors.

    Args:
        holes: List of hole dicts, each with keys ``x``, ``y``, ``depth``
               (depth as a positive number, e.g. 5 → drills to Z=-5).
        tool_diameter: Drill bit diameter (in units).
        safe_z: Safe retract height (positive). If None, the machine_profile
                default is used if available; missing safe_z is a plan error.
        feedrate: Drill feedrate in units/min. If None, profile default is used.
        spindle_speed: Spindle RPM. If None, M03 is skipped.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code (default "G54").
        material: Optional material description for G-code header.
        machine_profile: Optional built-in profile name, e.g. "generic_drill_mm".
        postprocessor: "fanuc" (default), "grbl", "marlin", or "linuxcnc".

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

    Safety note:
        Generated G-code is for review and simulation only.
        Never run on a real machine without expert verification.
    """
    try:
        return generate_drill_pattern_gcode_from_params(
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
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "drill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"generate_drill_pattern_gcode: unexpected error: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }


# ---------------------------------------------------------------------------
# Tool 9: generate_milling_facing_gcode  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_milling_facing_gcode(
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
    """Generate conservative milling facing G-code from explicit rectangular facing parameters.

    This deterministic tool does NOT use an LLM. It generates parallel X-axis
    passes across a rectangular area, stepping in Y by step_over per pass.

    No cutter compensation (G41/G42) is applied. No tool radius offset is
    calculated automatically. The output is a conservative MVP — review and
    simulate before use on a real machine.

    Args:
        origin_x: X coordinate of the lower-left corner of the facing area.
        origin_y: Y coordinate of the lower-left corner of the facing area.
        width: Width of the facing area along X (must be > 0).
        height: Height of the facing area along Y (must be > 0).
        depth: Cutting depth as a positive number (e.g. 1 → cuts to Z=-1).
               Negative values are accepted and normalised with a warning.
        step_over: Y step-over distance per pass (must be > 0).
        tool_diameter: End mill diameter (must be > 0).
        safe_z: Safe retract height (positive). Profile default used if None.
        feedrate: Cutting feedrate in units/min. Profile default used if None.
        spindle_speed: Spindle RPM. If None, M03 is skipped.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code (default "G54").
        material: Optional material description for G-code header.
        machine_profile: Optional built-in profile, e.g. "generic_mill_mm".
        postprocessor: "fanuc" (default), "grbl", "marlin", or "linuxcnc".

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

    Safety note:
        Generated G-code is for review and simulation only.
        Never run on a real machine without expert verification.
    """
    try:
        return generate_milling_facing_gcode_from_params(
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
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "mill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"generate_milling_facing_gcode: unexpected error: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }


# ---------------------------------------------------------------------------
# Tool 10: generate_milling_slot_gcode  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_milling_slot_gcode(
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
    """Generate conservative milling slot G-code from explicit straight-slot parameters.

    This deterministic tool does NOT use an LLM. It generates a straight slot
    in multiple Z passes (step_down per pass) along the X or Y axis.

    Slot width equals the tool diameter. No cutter compensation (G41/G42) is
    applied. No ramp entry. This is a conservative MVP — review and simulate
    before use on a real machine.

    Args:
        start_x: X start position of the slot centerline.
        start_y: Y start position of the slot centerline.
        length: Slot length along the chosen direction (must be > 0).
        depth: Total cutting depth as a positive number (e.g. 3 → Z=-3).
               Negative values are accepted and normalised with a warning.
        tool_diameter: End mill diameter — also defines slot width (must be > 0).
        safe_z: Safe retract height (positive). Profile default used if None.
        feedrate: Cutting feedrate in units/min. Profile default used if None.
        spindle_speed: Spindle RPM. If None, M03 is skipped.
        direction: "x" (slot along X) or "y" (slot along Y).
        step_down: Z depth increment per pass (must be > 0).
                   If larger than total depth, a single pass is used.
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code (default "G54").
        material: Optional material description for G-code header.
        machine_profile: Optional built-in profile, e.g. "generic_mill_mm".
        postprocessor: "fanuc" (default), "grbl", "marlin", or "linuxcnc".

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

    Safety note:
        Generated G-code is for review and simulation only.
        Never run on a real machine without expert verification.
    """
    try:
        return generate_milling_slot_gcode_from_params(
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
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "mill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"generate_milling_slot_gcode: unexpected error: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }


# ---------------------------------------------------------------------------
# Tool 11: generate_milling_pocket_gcode  (deterministic, no API key needed)
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_milling_pocket_gcode(
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
    """Generate conservative milling pocket G-code from explicit rectangular pocket parameters.

    This deterministic tool does not use an LLM or API key.

    Pipeline:
        1. Builds a structured OperationPlan from the typed parameters.
        2. Validates the plan (missing params, invalid values -> errors).
        3. Calls the Fanuc postprocessor to generate conservative G-code.
        4. Returns a structured result with ok, gcode, warnings, errors.

    Args:
        origin_x: X position of the lower-left corner of the pocket.
        origin_y: Y position of the lower-left corner of the pocket.
        width: Pocket width along X (must be > 0, in units).
        height: Pocket height along Y (must be > 0, in units).
        depth: Total cutting depth as a positive number (e.g. 3 -> cuts to Z=-3).
               Negative values are accepted and interpreted as target Z.
        tool_diameter: End mill diameter (must be > 0, in units).
        step_down: Z depth per pass (must be > 0). None -> error, no G-code generated.
        step_over: Radial step-over per raster row (must be > 0).
                   Values > tool_diameter produce a warning (may leave uncut material).
                   None -> error, no G-code generated.
        safe_z: Safe retract height above the workpiece. Filled from profile if None.
        feedrate: Cutting feedrate in units/min. None -> error, no G-code generated.
        spindle_speed: Spindle speed in RPM. None -> M03 skipped (with warning).
        units: "mm" (default) or "inch".
        work_coordinate_system: WCS code, e.g. "G54".
        material: Optional material description (informational).
        machine_profile: Built-in machine profile name (e.g. "generic_mill_mm").
        postprocessor: "fanuc" (default). Other values reserved for future use.

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

    Safety note:
        Generated G-code is for review and simulation only.
        Never run on a real machine without expert verification.
    """
    try:
        return generate_milling_pocket_gcode_from_params(
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
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "machine_type": "mill",
            "operation_plan": {},
            "gcode": "",
            "validation": {"ok": False, "errors": [str(exc)], "warnings": []},
            "warnings": [],
            "errors": [f"generate_milling_pocket_gcode: unexpected error: {exc}"],
            "postprocessor": postprocessor,
            "machine_profile": machine_profile,
        }


# ---------------------------------------------------------------------------
# Tool 12: analyze_gcode_safety_report  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def analyze_gcode_safety_report(
    gcode: str,
    machine_type: str = "mill",
    expected_units: str | None = None,
    safe_z: float | None = None,
    max_depth: float | None = None,
    allowed_commands: list[str] | None = None,
) -> dict:
    """Run the G-code Safety Analyzer and return a structured safety report.

    This deterministic tool does NOT use an LLM. It performs static analysis
    of a G-code program and returns a structured report with risk level,
    individual findings (with severity and line numbers), and a program summary.

    It does NOT simulate machine motion and does NOT replace expert review.
    All results are advisory only.

    Args:
        gcode:             G-code program text to analyze.
        machine_type:      Target machine type (mill, drill, lathe, laser, 3d_printer).
                           Affects machine-specific checks (spindle, laser, hotend temp).
        expected_units:    "mm" or "inch". If set, error if program declares other units.
        safe_z:            Expected safe retract height. Used for heuristic Z-range checks.
        max_depth:         Maximum allowed cutting depth (positive number).
                           Error if program cuts deeper than this.
        allowed_commands:  If set, error on any G/M command not in this list.

    Returns:
        {
          "ok": bool,
          "risk_level": "low" | "medium" | "high",
          "errors": list[str],
          "warnings": list[str],
          "summary": {
            "machine_type": str,
            "units": str,
            "positioning_mode": str,
            "work_coordinate_system": str | None,
            "has_program_end": bool,
            "has_feedrate": bool,
            "has_spindle_start": bool,
            "has_spindle_stop": bool,
            "line_count": int,
            "motion_line_count": int,
            "min_z": float | None,
            "max_z": float | None,
            "feedrates": list[float],
            "spindle_speeds": list[float],
            "unsupported_commands": list[str],
          },
          "findings": list[{
            "severity": "info" | "warning" | "error",
            "code": str,
            "line": int | None,
            "message": str,
            "text": str | None,
          }],
        }

    Safety note:
        Static analysis only. No machine motion is simulated.
        Always review and simulate G-code before running on a real machine.
    """
    try:
        from cnc.tools.safety_tools import analyze_gcode
        return analyze_gcode(
            gcode=gcode,
            machine_type=machine_type,
            expected_units=expected_units,
            safe_z=safe_z,
            max_depth=max_depth,
            allowed_commands=allowed_commands,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "risk_level": "high",
            "errors": [f"Safety analyzer raised unexpected exception: {exc}"],
            "warnings": [],
            "summary": {},
            "findings": [],
        }


# ---------------------------------------------------------------------------
# Shared helper — agent invocation
# ---------------------------------------------------------------------------


async def _invoke_cnc_agent(
    prompt: str,
    machine_type: str | None,
) -> tuple[object | None, dict | None]:
    """Build the CNC agent and invoke it with *prompt*.

    Returns:
        ``(raw_result, None)`` on success.
        ``(None, error_dict)`` if the agent cannot be built or invoked.
    """
    from cnc.agent import build_cnc_agent

    user_msg = prompt
    if machine_type:
        user_msg = f"{prompt}\nPreferred machine type: {machine_type}"

    try:
        agent = build_cnc_agent()
    except NotImplementedError:
        return None, _error_response(
            errors=["This tool requires the CNC DeepAgent (ANTHROPIC_API_KEY)."],
            warnings=["DeepAgent builder is not implemented yet."],
            machine_type=machine_type,
        )
    except RuntimeError as exc:
        return None, _error_response(
            errors=[f"Agent initialisation failed: {exc}"],
            machine_type=machine_type,
        )
    except Exception as exc:  # noqa: BLE001
        return None, _error_response(
            errors=[f"Unexpected error building agent: {exc}"],
            machine_type=machine_type,
        )

    try:
        if hasattr(agent, "ainvoke"):
            raw = await agent.ainvoke(user_msg)
        elif hasattr(agent, "run"):
            raw = agent.run(user_msg)
        elif hasattr(agent, "invoke"):
            raw = agent.invoke(user_msg)
        else:
            return None, _error_response(
                errors=["Agent has no callable invoke/run/ainvoke method."],
                machine_type=machine_type,
            )
    except Exception as exc:  # noqa: BLE001
        return None, _error_response(
            errors=[f"Agent invocation failed: {exc}"],
            machine_type=machine_type,
        )

    return raw, None


# ---------------------------------------------------------------------------
# Tool 13: plan_operation  (LLM-backed, requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


@mcp.tool()
async def plan_operation(
    prompt: str,
    machine_type: str | None = None,
) -> dict:
    """Plan a CNC operation from natural language and return a structured OperationPlan.

    This tool does NOT generate final G-code. It uses the CNC Supervisor Agent
    to extract and validate a structured OperationPlan from a natural language
    description. The resulting plan can be passed to ``postprocess_plan`` to
    produce G-code deterministically.

    Supported MVP operations:
    - Drill single hole
    - Drill multi-hole pattern
    - Milling facing (rectangular surface milling)
    - Milling straight slot (along X or Y)
    - Milling rectangular pocket

    Args:
        prompt: Natural language manufacturing description.
                Include material, dimensions, tooling, units, and operations when known.
        machine_type: Optional hint (``"drill"`` or ``"mill"``).

    Returns:
        {
          "ok": bool,
          "operation_plan": dict | None,
          "validation": dict,
          "warnings": list[str],
          "errors": list[str],
          "missing_info": list[str],
          "machine_type": str | None,
        }

    Safety note:
        Freeform agent text is never treated as G-code.
        If ``missing_info`` is non-empty, the plan is incomplete and no G-code
        should be generated from it.
    """
    from cnc.tools.agent_result_tools import (
        extract_operation_plan_from_agent_result,
        is_operation_plan_like,
        normalize_agent_operation_plan,
    )

    # A) Invoke agent
    raw, agent_err = await _invoke_cnc_agent(prompt, machine_type)
    if agent_err is not None:
        return {
            "ok": False,
            "operation_plan": None,
            "validation": agent_err.get("validation", {}),
            "warnings": agent_err.get("warnings", []),
            "errors": agent_err.get("errors", []),
            "missing_info": [],
            "machine_type": machine_type,
        }

    # B) Extract OperationPlan
    plan_result = extract_operation_plan_from_agent_result(raw)
    if not is_operation_plan_like(plan_result):
        return {
            "ok": False,
            "operation_plan": None,
            "validation": {"ok": False, "errors": plan_result.get("errors", []), "warnings": []},
            "warnings": plan_result.get("warnings", []),
            "errors": plan_result.get("errors", [
                "Agent returned unstructured output. Refusing to treat it as an OperationPlan."
            ]),
            "missing_info": [],
            "machine_type": machine_type,
        }

    # C) Normalize
    operation_plan = normalize_agent_operation_plan(
        plan_result, preferred_machine_type=machine_type
    )
    mt = operation_plan.get("machine_type") or machine_type

    # D) Return immediately if missing_info is non-empty
    missing_info = operation_plan.get("missing_info", [])
    if missing_info:
        return {
            "ok": False,
            "operation_plan": operation_plan,
            "validation": {
                "ok": False,
                "errors": ["Missing required manufacturing information."],
                "warnings": operation_plan.get("warnings", []),
            },
            "warnings": operation_plan.get("warnings", []),
            "errors": ["Missing required manufacturing information."],
            "missing_info": missing_info,
            "machine_type": mt,
        }

    # E) Validate plan
    try:
        plan_val = validate_operation_plan(operation_plan)
    except Exception as exc:  # noqa: BLE001
        plan_val = {"ok": False, "errors": [f"Plan validator raised exception: {exc}"], "warnings": []}

    return {
        "ok": plan_val.get("ok", False),
        "operation_plan": operation_plan,
        "validation": plan_val,
        "warnings": list(operation_plan.get("warnings", [])) + list(plan_val.get("warnings", [])),
        "errors": plan_val.get("errors", []),
        "missing_info": [],
        "machine_type": mt,
    }


# ---------------------------------------------------------------------------
# Tool 14: generate_gcode  (LLM-backed, requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


@mcp.tool()
async def generate_gcode(prompt: str, machine_type: str | None = None) -> dict:
    """Generate G-code from a natural language manufacturing description.

    Full pipeline:
    1. CNC DeepAgent parses the prompt and plans a structured OperationPlan.
    2. OperationPlan is extracted and normalized from the agent result.
    3. If ``missing_info`` is non-empty, no G-code is produced.
    4. OperationPlan is validated.
    5. Postprocessor generates deterministic G-code.
    6. Safety Analyzer validates the G-code.

    Freeform agent text is NEVER treated as final G-code.
    Only structured OperationPlans from the validation pipeline are accepted.

    Args:
        prompt: Natural language manufacturing description.
                Include material, dimensions, tooling, units, and operations when known.
        machine_type: Optional hint (``"drill"`` or ``"mill"``).
                      Agent infers from prompt if not provided.

    Returns:
        {
          "ok": bool,
          "gcode": str,
          "operation_plan": dict | None,
          "assumptions": list[str],
          "warnings": list[str],
          "errors": list[str],
          "missing_info": list[str],
          "validation": dict,
          "safety_report": dict | None,
          "machine_type": str | None,
          "postprocessor": str,
        }

    Safety note:
        Requires ANTHROPIC_API_KEY. Generated G-code is for review and
        simulation only. Never run on a real machine without expert verification.
    """
    from cnc.tools.agent_result_tools import (
        extract_operation_plan_from_agent_result,
        is_operation_plan_like,
        normalize_agent_operation_plan,
    )

    # A) Invoke agent
    raw, agent_err = await _invoke_cnc_agent(prompt, machine_type)
    if agent_err is not None:
        return agent_err

    # B) Extract OperationPlan — reject freeform / unstructured output
    plan_result = extract_operation_plan_from_agent_result(raw)
    if not is_operation_plan_like(plan_result):
        return {
            "ok": False,
            "gcode": "",
            "operation_plan": None,
            "assumptions": [],
            "warnings": plan_result.get("warnings", []),
            "errors": plan_result.get("errors", [
                "Agent returned unstructured output. "
                "Refusing to treat it as final G-code."
            ]),
            "missing_info": [],
            "validation": {
                "ok": False,
                "errors": plan_result.get("errors", []),
                "warnings": [],
                "machine_type": machine_type or "unknown",
            },
            "safety_report": None,
            "machine_type": machine_type,
            "postprocessor": "fanuc",
        }

    # C) Normalize
    operation_plan = normalize_agent_operation_plan(
        plan_result, preferred_machine_type=machine_type
    )
    mt = operation_plan.get("machine_type") or machine_type or "mill"

    # D) Block on missing_info
    missing_info = operation_plan.get("missing_info", [])
    if missing_info:
        return {
            "ok": False,
            "gcode": "",
            "operation_plan": operation_plan,
            "assumptions": operation_plan.get("assumptions", []),
            "warnings": operation_plan.get("warnings", []),
            "errors": ["Missing required manufacturing information."],
            "missing_info": missing_info,
            "validation": {
                "ok": False,
                "errors": ["Missing required manufacturing information."],
                "warnings": operation_plan.get("warnings", []),
                "machine_type": mt,
            },
            "safety_report": None,
            "machine_type": mt,
            "postprocessor": "fanuc",
        }

    # E+F) Validate + deterministic G-code regeneration via shared pipeline.
    # Agent-provided gcode is not used here — the pipeline always regenerates
    # from operation_plan via validate_operation_plan → postprocess_operations.
    from cnc.tools.gcode_pipeline import regenerate_gcode_from_operation_plan

    pp_result = regenerate_gcode_from_operation_plan(
        {"operation_plan": operation_plan},
        default_postprocessor="fanuc",
    )

    plan_warnings = list(operation_plan.get("warnings", []))
    combined_warnings = plan_warnings + pp_result.get("warnings", [])

    if pp_result.get("errors"):
        return {
            "ok": False,
            "gcode": "",
            "operation_plan": operation_plan,
            "assumptions": operation_plan.get("assumptions", []),
            "warnings": combined_warnings,
            "errors": pp_result.get("errors", []),
            "missing_info": [],
            "validation": pp_result.get("validation", {
                "ok": False,
                "errors": pp_result.get("errors", []),
                "warnings": [],
            }),
            "safety_report": None,
            "machine_type": mt,
            "postprocessor": pp_result.get("postprocessor", "fanuc"),
        }

    val = pp_result.get("validation", {})
    return {
        "ok": pp_result.get("ok", False),
        "gcode": pp_result.get("gcode", ""),
        "operation_plan": operation_plan,
        "assumptions": operation_plan.get("assumptions", []),
        "warnings": combined_warnings,
        "errors": pp_result.get("errors", []),
        "missing_info": [],
        "validation": val,
        "safety_report": {
            "risk_level": val.get("risk_level", "low"),
            "summary": val.get("summary", {}),
            "findings": val.get("findings", []),
        },
        "machine_type": mt,
        "postprocessor": pp_result.get("postprocessor", "fanuc"),
    }


# ---------------------------------------------------------------------------
# Tool 15: list_available_materials  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def list_available_materials() -> list[dict]:
    """List all built-in material library entries.

    Returns informational context about workpiece materials: category,
    machinability, notes, and caution warnings. Does NOT return cutting
    data — feedrate, spindle speed, step_down, and step_over must always
    be supplied explicitly.

    Returns:
        List of material dicts, each with: id, name, category, machinability,
        notes, warnings, supported_operations.
    """
    return list_materials()


# ---------------------------------------------------------------------------
# Tool 16: get_material_info  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_material_info(material_id: str) -> dict:
    """Get one built-in material library entry by ID.

    Args:
        material_id: Library ID, e.g. "aluminum_6061", "mild_steel".

    Returns:
        {"ok": True, "material": dict} on success.
        {"ok": False, "error": str, "material": None} if not found.
    """
    material = get_material(material_id)
    if material is None:
        return {
            "ok": False,
            "error": (
                f"Unknown material_id: {material_id!r}. "
                "Use list_available_materials() to see available materials."
            ),
            "material": None,
        }
    return {
        "ok": True,
        "material": material,
    }


# ---------------------------------------------------------------------------
# Tool 17: search_materials  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def search_materials(
    category: str | None = None,
    operation_type: str | None = None,
    machinability: str | None = None,
) -> list[dict]:
    """Search built-in material library entries.

    Filters are additive (AND). Omitting a filter means 'any'.

    Args:
        category:       Material category to filter by, e.g. "aluminum", "steel",
                        "stainless_steel", "plastic", "wood", "brass".
        operation_type: Only return materials that support this operation type,
                        e.g. "drill", "pocket", "slot", "facing".
        machinability:  Filter by machinability: "easy", "medium", or "hard".

    Returns:
        List of matching material dicts (may be empty).
    """
    return find_materials(
        category=category,
        operation_type=operation_type,
        machinability=machinability,
    )


# ---------------------------------------------------------------------------
# Tool 18: evaluate_operation_guardrails  (deterministic, no LLM required)
# ---------------------------------------------------------------------------


@mcp.tool()
def evaluate_operation_guardrails(
    operation_plan: dict,
    material: str | None = None,
) -> dict:
    """Evaluate parameter plausibility and material context for an OperationPlan.

    Does NOT generate or modify G-code. Does NOT derive cutting parameters.
    Reports missing values, unusual combinations, and material-specific cautions.

    Args:
        operation_plan: OperationPlan dict to evaluate.
        material:       Optional material name or library ID to evaluate against
                        (e.g. "aluminum_6061", "Mild steel"). Overrides
                        ``operation_plan.get("material")`` if set.

    Returns:
        {
          "ok":       bool,
          "errors":   list[str],
          "warnings": list[str],
          "info":     list[str],
          "material": dict | None,
          "findings": list[{"severity", "code", "message", "operation_index"}],
        }
    """
    try:
        return evaluate_parameter_guardrails(
            operation_plan=operation_plan,
            material=material,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [f"evaluate_operation_guardrails: unexpected error: {exc}"],
            "warnings": [],
            "info": [],
            "material": None,
            "findings": [],
        }


# ---------------------------------------------------------------------------
# Job Import/Export tools (Tools 19–23)
# ---------------------------------------------------------------------------


@mcp.tool()
def create_job(
    operation_plan: dict,
    name: str | None = None,
    description: str | None = None,
    machine_profile: str | None = None,
    material: str | None = None,
    tool_ids: list[str] | None = None,
    postprocessor: str = "fanuc",
    metadata: dict | None = None,
) -> dict:
    """Create a reproducible JSON CNC job spec from an OperationPlan.

    Bundles the OperationPlan with machine_profile, material, tool_ids,
    postprocessor, and metadata into a single serialisable job spec.
    Does NOT generate G-code.

    Args:
        operation_plan:  OperationPlan dict (must not contain G-code).
        name:            Human-readable job name.
        description:     Optional description.
        machine_profile: Machine profile name (e.g. "generic_mill_mm").
        material:        Material name or library ID (e.g. "aluminum_6061").
        tool_ids:        List of tool IDs referenced in the job.
        postprocessor:   Postprocessor dialect for G-code regeneration.
        metadata:        Arbitrary key-value metadata (no secrets).

    Returns:
        CNCJobSpec-compatible dict with schema_version, operation_plan, etc.
    """
    try:
        return create_job_spec(
            operation_plan=operation_plan,
            name=name,
            description=description,
            machine_profile=machine_profile,
            material=material,
            tool_ids=tool_ids,
            postprocessor=postprocessor,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "0.1",
            "ok": False,
            "errors": [f"create_job: unexpected error: {exc}"],
        }


@mcp.tool()
def validate_job(job: dict) -> dict:
    """Validate a JSON CNC job spec without generating G-code.

    Checks schema_version, operation_plan presence and validity,
    machine_type consistency, machine_profile, material, and tool_ids.
    Runs validate_operation_plan and evaluate_parameter_guardrails internally.

    Args:
        job: CNCJobSpec dict to validate.

    Returns:
        {
          "ok": bool,
          "errors": list[str],
          "warnings": list[str],
          "job": dict | None,
          "operation_plan_validation": dict | None,
          "guardrails": dict | None,
        }
    """
    try:
        return validate_job_spec(job)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [f"validate_job: unexpected error: {exc}"],
            "warnings": [],
            "job": None,
            "operation_plan_validation": None,
            "guardrails": None,
        }


@mcp.tool()
def generate_gcode_from_job(job: dict) -> dict:
    """Regenerate deterministic G-code from a JSON CNC job spec.

    Any stored ``gcode`` field in the job is ignored.
    G-code is always produced by the postprocessor pipeline from
    ``operation_plan``.

    Args:
        job: CNCJobSpec dict (from create_job, load_job, or JSON file).

    Returns:
        {
          "ok": bool,
          "gcode": str,
          "job": dict,
          "validation": dict,
          "warnings": list[str],
          "errors": list[str],
          "postprocessor": str,
          "safety_report": dict | None,
        }
    """
    try:
        return job_spec_to_gcode(job)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gcode": "",
            "job": job,
            "validation": {},
            "warnings": [],
            "errors": [f"generate_gcode_from_job: unexpected error: {exc}"],
            "postprocessor": "fanuc",
            "safety_report": None,
        }


@mcp.tool()
def save_job(job: dict, path: str) -> dict:
    """Save a JSON CNC job spec to a local file path.

    The file is written as UTF-8 JSON with 2-space indentation.
    The path must be accessible to the server process.
    Do not store secrets (API keys, passwords) in job specs.

    Args:
        job:  CNCJobSpec dict to save.
        path: Absolute or relative file path (e.g. "examples/jobs/my_job.json").

    Returns:
        {"ok": bool, "path": str, "errors": list[str], "warnings": list[str]}
    """
    try:
        return save_job_spec(job, path)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "path": path,
            "errors": [f"save_job: unexpected error: {exc}"],
            "warnings": [],
        }


@mcp.tool()
def load_job(path: str) -> dict:
    """Load a JSON CNC job spec from a local file path.

    The path must be accessible to the server process.
    Any stored ``gcode`` field in the loaded job will be flagged with a warning.

    Args:
        path: Absolute or relative path to a .json job spec file.

    Returns:
        {
          "ok": bool,
          "job": dict | None,
          "path": str,
          "errors": list[str],
          "warnings": list[str],
        }
    """
    try:
        return load_job_spec(path)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "job": None,
            "path": path,
            "errors": [f"load_job: unexpected error: {exc}"],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# Job Run & Report tools (Tools 24–26)
# ---------------------------------------------------------------------------


@mcp.tool()
def run_cnc_job(
    job: dict,
    save_gcode_path: str | None = None,
    save_report_path: str | None = None,
) -> dict:
    """Run a JSON CNC job spec through validation, postprocessing, and safety analysis.

    Does NOT call an LLM. G-code is always regenerated deterministically
    from the job's ``operation_plan``. Any stored ``gcode`` field is ignored.

    Args:
        job:              CNCJobSpec dict (from ``create_job``, ``load_job``, or a JSON file).
        save_gcode_path:  Optional local path to save the generated G-code (e.g. "outputs/gcode/my_job.nc").
        save_report_path: Optional local path to save the full run report JSON.

    Returns:
        {
          "ok": bool,
          "run_report": dict,
          "gcode": str,
          "warnings": list[str],
          "errors": list[str],
          "artifacts": list[dict],
        }
    """
    try:
        return run_job(
            job=job,
            save_gcode_path=save_gcode_path,
            save_report_path=save_report_path,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "run_report": {},
            "gcode": "",
            "warnings": [],
            "errors": [f"run_cnc_job: unexpected error: {exc}"],
            "artifacts": [],
        }


@mcp.tool()
def save_run(run_report: dict, path: str) -> dict:
    """Save a CNC run report to a local JSON file.

    Args:
        run_report: Run report dict (from ``run_cnc_job``).
        path:       Local file path (e.g. "outputs/runs/my_run.json").

    Returns:
        {"ok": bool, "path": str, "errors": list[str], "warnings": list[str]}
    """
    try:
        return save_run_report(run_report, path)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "path": path,
            "errors": [f"save_run: unexpected error: {exc}"],
            "warnings": [],
        }


@mcp.tool()
def load_run(path: str) -> dict:
    """Load a CNC run report from a local JSON file.

    Args:
        path: Local file path to a run report JSON file.

    Returns:
        {
          "ok": bool,
          "run_report": dict | None,
          "path": str,
          "errors": list[str],
          "warnings": list[str],
        }
    """
    try:
        return load_run_report(path)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "run_report": None,
            "path": path,
            "errors": [f"load_run: unexpected error: {exc}"],
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
