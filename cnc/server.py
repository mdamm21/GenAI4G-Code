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
from cnc.tools.drill_tools import generate_drill_gcode_from_params

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
        "machine_type": machine_type,
        "validation": {
            "ok": False,
            "errors": errors,
            "warnings": warnings or [],
            "machine_type": mt,
        },
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
# Tool 6: generate_gcode  (LLM-backed, requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


@mcp.tool()
async def generate_gcode(prompt: str, machine_type: str | None = None) -> dict:
    """Generate G-code from a natural language manufacturing description.

    Delegates to the CNC DeepAgent (cnc.agent.build_cnc_agent) which orchestrates:
    1. Request parsing and JobSpec extraction.
    2. Machine-specific subagent planning (OperationPlan).
    3. Deterministic postprocessing (G-code generation).
    4. G-code validation before returning.

    NOTE: If the DeepAgent is not yet implemented, returns a structured error.
    No unsafe direct prompt-to-G-code generation is performed.

    Args:
        prompt: Natural language manufacturing description.
                Include material, dimensions, tooling, units, and operations when known.
        machine_type: Optional hint (mill, lathe, laser, 3d_printer, drill, grinder).
                      Agent will infer from prompt if not provided.

    Returns:
        Dict with keys: ok, gcode, operation_plan, assumptions, warnings,
                        errors, machine_type, validation.
    """
    from cnc.agent import build_cnc_agent

    # Build the user message
    user_msg = prompt
    if machine_type:
        user_msg = f"{prompt}\nPreferred machine type: {machine_type}"

    # --- Try to build and invoke the agent ---
    try:
        agent = build_cnc_agent()
    except NotImplementedError:
        return _error_response(
            errors=["generate_gcode requires the DeepAgent implementation from the next step."],
            warnings=["DeepAgent builder is not implemented yet."],
            machine_type=machine_type,
        )
    except RuntimeError as exc:
        return _error_response(
            errors=[f"Agent initialisation failed: {exc}"],
            machine_type=machine_type,
        )
    except Exception as exc:  # noqa: BLE001
        return _error_response(
            errors=[f"Unexpected error building agent: {exc}"],
            machine_type=machine_type,
        )

    # --- Invoke: prefer async, fall back to sync ---
    try:
        if hasattr(agent, "ainvoke"):
            raw = await agent.ainvoke(user_msg)
        elif hasattr(agent, "run"):
            raw = agent.run(user_msg)
        elif hasattr(agent, "invoke"):
            raw = agent.invoke(user_msg)
        else:
            return _error_response(
                errors=["Agent has no callable invoke/run/ainvoke method."],
                machine_type=machine_type,
            )
    except Exception as exc:  # noqa: BLE001
        return _error_response(
            errors=[f"Agent invocation failed: {exc}"],
            machine_type=machine_type,
        )

    return _normalize_agent_result(raw, machine_type=machine_type)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
