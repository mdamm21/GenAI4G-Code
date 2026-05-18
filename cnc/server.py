"""CNC MCP Server — outer tool API for the CNC G-code generation system.

Exposes CNC tools via the Model Context Protocol (MCP).
The DeepAgent (cnc.agent) is the internal orchestrator — never called directly by users.

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

import os
from pathlib import Path

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

mcp = FastMCP("genai4g-cnc")

# ---------------------------------------------------------------------------
# Tool: list_supported_machines
# ---------------------------------------------------------------------------


@mcp.tool()
def list_supported_machines() -> list[str]:
    """List all supported CNC machine types.

    Returns:
        List of supported machine type identifiers.
    """
    return ["mill", "lathe", "grinder", "drill", "3d_printer", "laser"]


# ---------------------------------------------------------------------------
# Tool: validate_gcode
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
    from cnc.validators.gcode_validator import validate_gcode_text
    return validate_gcode_text(gcode, machine_type=machine_type)


# ---------------------------------------------------------------------------
# Tool: generate_gcode
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_gcode(prompt: str, machine_type: str | None = None) -> dict:
    """Generate G-code from a natural language manufacturing description.

    Uses the CNC DeepAgent to:
    1. Parse the manufacturing request.
    2. Delegate to the appropriate machine-specific subagent.
    3. Generate a structured OperationPlan.
    4. Run the operation plan through a postprocessor to produce G-code.
    5. Validate the G-code before returning.

    Args:
        prompt: Natural language description of the manufacturing job.
                Include material, dimensions, tools, operations, and units when known.
        machine_type: Optional machine type hint (mill, lathe, laser, 3d_printer, drill, grinder).
                      If None, the agent will attempt to infer it from the prompt.

    Returns:
        Structured dict with keys:
        - gcode: str — final G-code program (empty string if generation failed)
        - operation_plan: dict | None — structured operation plan
        - assumptions: list[str] — all assumptions made
        - warnings: list[str] — warnings about missing or uncertain data
        - validation: dict — validation result (ok, errors, warnings)
        - machine_type: str | None — inferred or specified machine type
    """
    from cnc.agent import build_cnc_agent

    full_prompt = prompt
    if machine_type:
        full_prompt = f"[Machine type: {machine_type}]\n{prompt}"

    try:
        agent = build_cnc_agent()
        result = agent.run(full_prompt)
    except RuntimeError as exc:
        return {
            "gcode": "",
            "operation_plan": None,
            "assumptions": [],
            "warnings": [str(exc)],
            "validation": {
                "ok": False,
                "errors": ["Agent not available — check installation."],
                "warnings": [],
                "machine_type": machine_type or "mill",
            },
            "machine_type": machine_type,
        }
    except Exception as exc:
        return {
            "gcode": "",
            "operation_plan": None,
            "assumptions": [],
            "warnings": [f"Unexpected error: {exc}"],
            "validation": {
                "ok": False,
                "errors": [f"Agent error: {exc}"],
                "warnings": [],
                "machine_type": machine_type or "mill",
            },
            "machine_type": machine_type,
        }

    # Ensure machine_type is in result
    if machine_type and not result.get("machine_type"):
        result["machine_type"] = machine_type

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
