"""Safety tools — thin wrapper for the G-code Safety Analyzer.

Bridges cnc/validators/safety_analyzer.py into the tools layer so the
MCP server and other callers have a consistent import path.
"""

from __future__ import annotations

from cnc.validators.safety_analyzer import analyze_gcode_safety


def analyze_gcode(
    gcode: str,
    machine_type: str = "mill",
    expected_units: str | None = None,
    safe_z: float | None = None,
    max_depth: float | None = None,
    allowed_commands: list[str] | None = None,
) -> dict:
    """Analyze a G-code program for safety and completeness.

    Thin wrapper around :func:`analyze_gcode_safety`.  See that function for
    full parameter and return-value documentation.

    Args:
        gcode:             G-code program text to analyze.
        machine_type:      "mill", "drill", "lathe", "laser", "3d_printer", etc.
        expected_units:    "mm" or "inch" — error if program declares the other unit.
        safe_z:            Expected safe retract height for heuristic Z checks.
        max_depth:         Maximum allowed cutting depth (positive number).
        allowed_commands:  If set, error on any G/M command not in this list.

    Returns:
        {
          "ok": bool,
          "risk_level": "low" | "medium" | "high",
          "errors": list[str],
          "warnings": list[str],
          "summary": dict,
          "findings": list[dict],
        }
    """
    return analyze_gcode_safety(
        gcode=gcode,
        machine_type=machine_type,
        expected_units=expected_units,
        safe_z=safe_z,
        max_depth=max_depth,
        allowed_commands=allowed_commands,
    )
