"""Natural-language fallback parser — parse simple drill prompts without an LLM.

This module provides a best-effort regex parser for very specific English drill
prompts that include all required parameters explicitly.  It is intentionally
conservative: if any required value is ambiguous or missing the function returns
None so the caller can fall back to the LLM agent.

Limitations:
- Only single-hole drill operations are supported.
- All critical parameters (x, y, depth, tool_diameter, safe_z, feedrate) must
  be explicitly present in the prompt text.
- Units default to mm.  "inch" or "inches" in the prompt switches to inch.
- No unsafe defaults are applied.
"""

from __future__ import annotations

import re


def _find_float(pattern: str, text: str) -> float | None:
    """Return the first float matching *pattern* in *text*, or None."""
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, IndexError):
            return None
    return None


def parse_simple_drill_prompt(prompt: str) -> dict | None:
    """Parse a simple single-hole drill prompt without an LLM.

    The prompt must explicitly state all of the following:
    - ``x`` and ``y`` coordinates  (e.g. "at X0 Y0" or "X=5 Y=10")
    - drill depth                  (e.g. "5mm deep" or "depth 5mm")
    - tool diameter                (e.g. "5mm tool" or "5mm drill" or "tool diameter 5mm")
    - safe Z height                (e.g. "safe Z 5" or "safeZ 5mm")
    - feedrate                     (e.g. "feedrate 100" or "feed 100")

    Optional:
    - spindle speed                (e.g. "spindle 1200" or "rpm 1200")
    - units                        (defaults to ``"mm"``; ``"inch"`` / ``"inches"`` switches)

    Returns:
        A minimal ``OperationPlan``-like dict ready for ``validate_operation_plan``
        and the postprocessor, or ``None`` if the prompt cannot be confidently parsed.

    Example prompt::

        "Drill a 5mm deep hole at X0 Y0 with a 5mm tool, safe Z 5, feedrate 100, spindle 1200"
    """
    p = prompt.strip()
    text = p.lower()

    # Must mention "drill"
    if "drill" not in text:
        return None

    # Units
    units = "inch" if re.search(r"\binch(es)?\b", text) else "mm"

    # X coordinate
    x = _find_float(r'\bx\s*[=:]?\s*(-?[\d.]+)', text)
    if x is None:
        return None

    # Y coordinate
    y = _find_float(r'\by\s*[=:]?\s*(-?[\d.]+)', text)
    if y is None:
        return None

    # Depth: "5mm deep", "depth 5mm", "depth of 5", "5 mm depth"
    depth = (
        _find_float(r'([\d.]+)\s*(?:mm|inch(?:es)?)?\s*deep', text)
        or _find_float(r'depth\s+(?:of\s+)?([\d.]+)', text)
        or _find_float(r'([\d.]+)\s*(?:mm|inch(?:es)?)?\s+depth', text)
    )
    if depth is None or depth <= 0:
        return None

    # Tool diameter: "5mm tool", "5mm drill", "tool diameter 5", "diameter 5mm"
    tool_diameter = (
        _find_float(r'([\d.]+)\s*(?:mm|inch(?:es)?)?\s+(?:tool|drill|bit|cutter)', text)
        or _find_float(r'(?:tool|drill)\s+(?:diameter|dia\.?)\s+([\d.]+)', text)
        or _find_float(r'(?:diameter|dia\.?)\s+([\d.]+)', text)
        or _find_float(r'with\s+a?\s*([\d.]+)\s*(?:mm|inch(?:es)?)', text)
    )
    if tool_diameter is None or tool_diameter <= 0:
        return None

    # Safe Z: "safe Z 5", "safeZ 5mm", "safe z=5", "retract 5"
    safe_z = (
        _find_float(r'safe\s*z\s*[=:]?\s*([\d.]+)', text)
        or _find_float(r'retract\s+(?:to\s+)?([\d.]+)', text)
        or _find_float(r'clearance\s+(?:height\s+)?([\d.]+)', text)
    )
    if safe_z is None or safe_z <= 0:
        return None

    # Feedrate: "feedrate 100", "feed 100", "feed rate 100", "f 100 mm"
    feedrate = (
        _find_float(r'feed\s*rate\s*[=:]?\s*([\d.]+)', text)
        or _find_float(r'feedrate\s*[=:]?\s*([\d.]+)', text)
        or _find_float(r'\bfeed\s+([\d.]+)', text)
    )
    if feedrate is None or feedrate <= 0:
        return None

    # Spindle speed (optional): "spindle 1200", "rpm 1200", "s 1200 rpm"
    spindle_speed = (
        _find_float(r'spindle\s*(?:speed\s*)?[=:]?\s*([\d.]+)', text)
        or _find_float(r'([\d.]+)\s*rpm', text)
        or _find_float(r'\brpm\s*[=:]?\s*([\d.]+)', text)
    )

    # Work coordinate system
    wcs_m = re.search(r'\b(G5[4-9])\b', p, re.IGNORECASE)
    wcs = wcs_m.group(1).upper() if wcs_m else "G54"

    # Build a minimal OperationPlan
    target_z = -abs(depth)

    tool: dict = {
        "tool_number": 1,
        "description": f"{tool_diameter}{units} drill",
        "diameter_mm": tool_diameter if units == "mm" else tool_diameter * 25.4,
        "type": "drill",
    }

    operation: dict = {
        "type": "drill",
        "name": f"Drill hole at X{x} Y{y}",
        "tool_number": 1,
        "feedrate_mmpm": feedrate,
        "parameters": {"x": x, "y": y, "z": target_z},
    }
    if spindle_speed is not None:
        operation["spindle_rpm"] = spindle_speed

    warnings: list[str] = []
    if spindle_speed is None:
        warnings.append(
            "Spindle speed not found in prompt. M03 will be skipped. "
            "Verify spindle is started before running."
        )

    return {
        "machine_type": "drill",
        "units": units,
        "work_coordinate_system": wcs,
        "safe_z": safe_z,
        "tools": [tool],
        "operations": [operation],
        "assumptions": [
            "Parsed from natural language without LLM — review all parameters carefully."
        ],
        "warnings": warnings,
        "missing_info": [],
        "_source": "nl_fallback_parser",
    }
