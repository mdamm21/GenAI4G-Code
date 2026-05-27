"""Common helper functions shared by all postprocessors.

Keep this module simple — small utilities only.  No operation-specific logic here.
"""

from __future__ import annotations


def fmt(value: float | int, precision: int = 3) -> str:
    """Format a numeric value as a fixed-decimal string.

    Examples:
        fmt(5)        → "5.000"
        fmt(5.12345)  → "5.123"
    """
    return f"{float(value):.{precision}f}"


def get_units_code(units: str) -> str:
    """Return the G-code unit modal code.

    "mm"   → "G21"
    "inch" → "G20"
    other  → "G21"  (safe default)
    """
    if units == "inch":
        return "G20"
    return "G21"


def get_safe_z(operation_plan: dict) -> float | None:
    """Return safe_z from the plan as float, or None if not specified."""
    raw = operation_plan.get("safe_z")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def get_work_coordinate_system(operation_plan: dict) -> str:
    """Return the work coordinate system code, defaulting to G54."""
    return operation_plan.get("work_coordinate_system", "G54")


def iter_operations(operation_plan: dict) -> list[dict]:
    """Return the operations list from the plan (empty list if absent)."""
    return operation_plan.get("operations", [])


def operation_comment(text: str) -> str:
    """Return a safe G-code comment string.

    Removes newlines and replaces parentheses that would break parsing.
    Format: "(text)"
    """
    cleaned = (
        str(text)
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("(", "[")
        .replace(")", "]")
    )
    return f"({cleaned})"
