"""Issue Resolution — collect, deduplicate, and resolve interactive issues.

This module provides:
  - collect_interactive_issues(): gather warnings/errors from all pipeline stages
  - build_issue_choices(): generate context-aware resolution options
  - apply_resolution_decision(): apply a user's choice to the result/plan

Core pipeline modules remain non-interactive. All user interaction is driven
by the CLI layer (cnc/cli_interaction.py).
"""

from __future__ import annotations

import re
import copy
from typing import Any

# ---------------------------------------------------------------------------
# Metric ISO thread table — coarse pitch (DIN 13)
# tap_drill_mm: core hole diameter for tapping
# clearance_mm: medium-fit clearance hole (ISO 273 / DIN EN 20273)
# ---------------------------------------------------------------------------

_METRIC_THREAD_TABLE: dict[str, dict[str, float]] = {
    "M3":  {"tap_drill_mm": 2.5,  "clearance_mm": 3.4},
    "M4":  {"tap_drill_mm": 3.3,  "clearance_mm": 4.5},
    "M5":  {"tap_drill_mm": 4.2,  "clearance_mm": 5.5},
    "M6":  {"tap_drill_mm": 5.0,  "clearance_mm": 6.6},
    "M8":  {"tap_drill_mm": 6.8,  "clearance_mm": 9.0},
    "M10": {"tap_drill_mm": 8.5,  "clearance_mm": 11.0},
    "M12": {"tap_drill_mm": 10.2, "clearance_mm": 13.5},
    "M14": {"tap_drill_mm": 12.0, "clearance_mm": 15.5},
    "M16": {"tap_drill_mm": 14.0, "clearance_mm": 17.5},
    "M20": {"tap_drill_mm": 17.5, "clearance_mm": 22.0},
}

_BOLT_SIZE_PATTERN = re.compile(r"\bM(\d+)\b")


def _detect_bolt_size(op: dict) -> str | None:
    """Try to detect bolt size (e.g. 'M8') from tool descriptions."""
    for t in op.get("tools", []):
        if isinstance(t, dict):
            desc = t.get("description", "")
            m = _BOLT_SIZE_PATTERN.search(desc)
            if m:
                return f"M{m.group(1)}"
    return None


# ---------------------------------------------------------------------------
# Issue code constants
# ---------------------------------------------------------------------------

UNKNOWN_TOOL_ID = "UNKNOWN_TOOL_ID"
MISSING_TOOL = "MISSING_TOOL"
TOOL_DIAMETER_MISMATCH = "TOOL_DIAMETER_MISMATCH"
UNSUPPORTED_TOOL_OPERATION = "UNSUPPORTED_TOOL_OPERATION"

MISSING_MATERIAL = "MISSING_MATERIAL"
UNKNOWN_MATERIAL = "UNKNOWN_MATERIAL"

MISSING_FEEDRATE = "MISSING_FEEDRATE"
ASSUMED_FEEDRATE = "ASSUMED_FEEDRATE"
MISSING_SPINDLE_SPEED = "MISSING_SPINDLE_SPEED"
MISSING_SAFE_Z = "MISSING_SAFE_Z"

MISSING_BOLT_CIRCLE_CENTER = "MISSING_BOLT_CIRCLE_CENTER"
MISSING_BOLT_CIRCLE_START_ANGLE = "MISSING_BOLT_CIRCLE_START_ANGLE"
MISSING_BOLT_CIRCLE_HOLE_TYPE = "MISSING_BOLT_CIRCLE_HOLE_TYPE"
MISSING_Z_REFERENCE = "MISSING_Z_REFERENCE"

RELATIVE_POSITIONING = "RELATIVE_POSITIONING"
RELATIVE_NEGATIVE_Z = "RELATIVE_NEGATIVE_Z"
UNSUPPORTED_COMMAND = "UNSUPPORTED_COMMAND"

AGENT_GCODE_DISCARDED = "AGENT_GCODE_DISCARDED"
POSTPROCESSOR_WARNING = "POSTPROCESSOR_WARNING"
GENERAL_WARNING = "GENERAL_WARNING"
VALIDATION_ERROR = "VALIDATION_ERROR"

# Assumed default issue codes
ASSUMED_POSTPROCESSOR = "ASSUMED_POSTPROCESSOR"
ASSUMED_UNITS = "ASSUMED_UNITS"
ASSUMED_WCS = "ASSUMED_WCS"
ASSUMED_MACHINE_TYPE = "ASSUMED_MACHINE_TYPE"

# ---------------------------------------------------------------------------
# Message classification patterns
# ---------------------------------------------------------------------------

# Pattern → (code, category, title, actionable, blocking)
_MESSAGE_PATTERNS: list[tuple[re.Pattern[str], str, str, str, bool, bool]] = [
    (re.compile(r"tool_id='([^']+)'.*not in the built-in tool library", re.I),
     UNKNOWN_TOOL_ID, "tool", "Unknown tool reference", True, False),
    (re.compile(r"references tool_id='([^']+)'.*not in the.*tool", re.I),
     UNKNOWN_TOOL_ID, "tool", "Unknown tool reference", True, False),
    (re.compile(r"Tool ID '([^']+)' is not in the built-in tool library", re.I),
     UNKNOWN_TOOL_ID, "tool", "Unknown tool reference", True, False),
    (re.compile(r"no tool_number or tool_id", re.I),
     MISSING_TOOL, "tool", "Missing tool reference", True, True),
    (re.compile(r"tool.*diameter.*mismatch|diameter.*tool.*mismatch", re.I),
     TOOL_DIAMETER_MISMATCH, "tool", "Tool diameter mismatch", True, False),
    (re.compile(r"does not support operation type", re.I),
     UNSUPPORTED_TOOL_OPERATION, "tool", "Unsupported tool operation", True, True),

    (re.compile(r"Material was not specified", re.I),
     MISSING_MATERIAL, "material", "Material not specified", True, False),
    (re.compile(r"Unknown material:", re.I),
     UNKNOWN_MATERIAL, "material", "Unknown material", True, False),

    (re.compile(r"missing.*feedrate|no feedrate|feedrate.*missing", re.I),
     MISSING_FEEDRATE, "parameter", "Missing feedrate", True, True),
    (re.compile(r"feedrate.*(?:was |been )?assumed|assumed.*feedrate", re.I),
     ASSUMED_FEEDRATE, "parameter", "Feedrate assumed by agent", True, True),
    (re.compile(r"no spindle_speed|spindle.*missing|missing.*spindle", re.I),
     MISSING_SPINDLE_SPEED, "parameter", "Missing spindle speed", True, False),
    (re.compile(r"Missing required field: safe_z", re.I),
     MISSING_SAFE_Z, "parameter", "Missing safe Z", True, True),

    (re.compile(r"missing.*'center_[xy]'.*bolt circle|bolt circle center.*not specified", re.I),
     MISSING_BOLT_CIRCLE_CENTER, "geometry", "Bolt circle center not specified", True, True),
    (re.compile(r"missing.*'start_angle_deg'.*bolt circle|bolt circle start angle.*not specified", re.I),
     MISSING_BOLT_CIRCLE_START_ANGLE, "geometry", "Bolt circle start angle not specified", True, True),
    (re.compile(r"missing.*'hole_type'|hole type.*not specified", re.I),
     MISSING_BOLT_CIRCLE_HOLE_TYPE, "geometry", "Hole type not specified", True, True),

    (re.compile(r"G91 relative positioning detected", re.I),
     RELATIVE_POSITIONING, "safety", "Relative positioning detected", False, False),
    (re.compile(r"Relative positioning.*G91.*combined with negative Z|G91.*negative Z", re.I),
     RELATIVE_NEGATIVE_Z, "safety", "Relative negative Z move", False, False),
    (re.compile(r"Scoped G91.*G28", re.I),
     RELATIVE_POSITIONING, "safety", "Scoped G91 for G28 return", False, False),
    (re.compile(r"Unrecogni[sz]ed commands found", re.I),
     UNSUPPORTED_COMMAND, "safety", "Unsupported commands", False, False),

    (re.compile(r"Agent.*gcode was discarded|gcode.*discarded.*deterministically", re.I),
     AGENT_GCODE_DISCARDED, "info", "Agent G-code discarded", False, False),
]

# Patterns for extracting operation index from messages
_OP_INDEX_PATTERN = re.compile(r"Operation\s+(\d+)")
_TOOL_ID_PATTERN = re.compile(r"tool_id='([^']+)'")


def _extract_op_index(msg: str) -> int | None:
    m = _OP_INDEX_PATTERN.search(msg)
    return int(m.group(1)) if m else None


def _extract_tool_id(msg: str) -> str | None:
    m = _TOOL_ID_PATTERN.search(msg)
    if m:
        return m.group(1)
    m2 = re.search(r"Tool ID '([^']+)'", msg)
    return m2.group(1) if m2 else None


def _classify_message(msg: str) -> tuple[str, str, str, bool, bool]:
    """Return (code, category, title, actionable, blocking) for a message."""
    for pat, code, cat, title, actionable, blocking in _MESSAGE_PATTERNS:
        if pat.search(msg):
            return code, cat, title, actionable, blocking
    return GENERAL_WARNING, "general", "Warning", False, False


# ---------------------------------------------------------------------------
# Assumed-default detection
# ---------------------------------------------------------------------------

# Patterns to match assumption strings from normalize_operation_plan / gcode_pipeline
_ASSUMPTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Assumed postprocessor:", re.I), ASSUMED_POSTPROCESSOR),
    (re.compile(r"Assumed units:", re.I), ASSUMED_UNITS),
    (re.compile(r"Assumed work coordinate system:", re.I), ASSUMED_WCS),
    (re.compile(r"Machine type not specified", re.I), ASSUMED_MACHINE_TYPE),
]


def _detect_assumed_defaults(result: dict, groups: dict[str, dict]) -> None:
    """Detect assumed defaults from operation_plan assumptions list and add issues."""
    op = result.get("operation_plan", {})
    if not isinstance(op, dict):
        return

    assumptions = op.get("assumptions", [])
    if not assumptions:
        return

    for assumption in assumptions:
        if not isinstance(assumption, str):
            continue

        for pat, code in _ASSUMPTION_PATTERNS:
            if pat.search(assumption):
                if code in groups:
                    break  # already have this issue

                current_value = None
                if code == ASSUMED_POSTPROCESSOR:
                    current_value = result.get("postprocessor") or op.get("postprocessor") or "fanuc"
                    title = "Postprocessor assumed"
                    message = f"No postprocessor specified. Using default: {current_value}"
                    category = "defaults"
                elif code == ASSUMED_UNITS:
                    current_value = op.get("units", "mm")
                    title = "Units assumed"
                    message = f"No units specified. Using default: {current_value}"
                    category = "defaults"
                elif code == ASSUMED_WCS:
                    current_value = op.get("work_coordinate_system", "G54")
                    title = "Work coordinate system assumed"
                    message = f"No work coordinate system specified. Using default: {current_value}"
                    category = "defaults"
                elif code == ASSUMED_MACHINE_TYPE:
                    current_value = op.get("machine_type")
                    title = "Machine type not specified"
                    message = "No machine type specified in the operation plan."
                    category = "defaults"
                else:
                    break

                groups[code] = {
                    "id": f"issue_{len(groups)}",
                    "code": code,
                    "severity": "warning",
                    "category": category,
                    "title": title,
                    "message": message,
                    "actionable": True,
                    "blocking": False,
                    "source_messages": [assumption],
                    "affected_operations": [],
                    "context": {"current_value": current_value},
                    "choices": [],
                }
                break


# ---------------------------------------------------------------------------
# Bolt circle pattern detection
# ---------------------------------------------------------------------------

_BOLT_CIRCLE_NAME_PATTERN = re.compile(
    r"bolt.?circle|lochkreis|\bat\s+\d+\s*deg", re.I,
)


def _detect_bolt_circle_params_from_ops(
    operations: list[dict],
) -> dict | None:
    """Detect bolt circle geometry from drill operations.

    Returns a dict with detected center, radius, start_angle, num_holes
    if the operations look like a bolt circle pattern, or None.
    """
    import math

    drill_ops = [
        o for o in operations
        if isinstance(o, dict) and o.get("type") == "drill"
        and isinstance(o.get("parameters"), dict)
        and "x" in o["parameters"] and "y" in o["parameters"]
    ]

    if len(drill_ops) < 3:
        return None

    # Check if operation names suggest a bolt circle
    bc_named = sum(
        1 for o in drill_ops
        if _BOLT_CIRCLE_NAME_PATTERN.search(o.get("name", ""))
    )
    if bc_named < 2:
        return None

    # Extract positions
    positions = [(o["parameters"]["x"], o["parameters"]["y"]) for o in drill_ops]
    n = len(positions)

    # Compute centroid
    cx = sum(x for x, _ in positions) / n
    cy = sum(y for _, y in positions) / n

    # Compute radius from centroid to first hole
    r = math.sqrt((positions[0][0] - cx) ** 2 + (positions[0][1] - cy) ** 2)
    if r < 0.01:
        return None

    # Verify all holes are at approximately the same radius
    for x, y in positions:
        ri = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        if abs(ri - r) > 0.5:
            return None

    # Start angle of first hole
    start_angle = math.degrees(
        math.atan2(positions[0][1] - cy, positions[0][0] - cx)
    )

    return {
        "center_x": round(cx, 3),
        "center_y": round(cy, 3),
        "radius": round(r, 3),
        "num_holes": n,
        "start_angle_deg": round(start_angle, 3),
    }


def _detect_undocumented_bolt_circle(
    result: dict, groups: dict[str, dict],
) -> None:
    """Add issues for bolt circle patterns with undocumented assumptions.

    If the plan contains drill operations arranged in a circular pattern
    but the center point, start angle, or hole type were not explicitly
    confirmed, create blocking HITL issues for each.
    """
    op = result.get("operation_plan", {})
    if not isinstance(op, dict):
        return

    operations = op.get("operations", [])
    detected = _detect_bolt_circle_params_from_ops(operations)
    if detected is None:
        return

    assumptions = [str(a) for a in op.get("assumptions", [])]
    resolution_log = result.get("resolution_log", [])
    resolved_codes = {
        e.get("issue_code")
        for e in resolution_log
        if e.get("action") not in ("ACKNOWLEDGED", "IGNORE_ONCE")
    }

    # Only assumptions that start with "Confirmed" count as user-confirmed.
    # Agent-generated assumptions like "Bolt circle center at X0/Y0" are
    # NOT confirmations — they are exactly what we need the user to confirm.
    confirmed = [a for a in assumptions if a.lower().startswith("confirmed")]

    n_ops = len(operations)

    # Center
    center_confirmed = (
        any("center" in a.lower() for a in confirmed)
        or MISSING_BOLT_CIRCLE_CENTER in resolved_codes
    )
    if not center_confirmed and MISSING_BOLT_CIRCLE_CENTER not in groups:
        groups[MISSING_BOLT_CIRCLE_CENTER] = {
            "id": f"issue_{len(groups)}",
            "code": MISSING_BOLT_CIRCLE_CENTER,
            "severity": "warning",
            "category": "geometry",
            "title": "Bolt circle center not confirmed",
            "message": (
                f"Bolt circle center not specified by user. "
                f"Plan uses X{detected['center_x']} / Y{detected['center_y']} "
                f"— confirm or enter manually."
            ),
            "actionable": True,
            "blocking": True,
            "source_messages": [
                "Bolt circle center assumed without operator confirmation."
            ],
            "affected_operations": list(range(n_ops)),
            "context": {
                "detected_center_x": detected["center_x"],
                "detected_center_y": detected["center_y"],
                "bolt_circle_params": detected,
            },
            "choices": [],
        }

    # Start angle
    angle_confirmed = (
        any("start" in a.lower() and "angle" in a.lower() for a in confirmed)
        or MISSING_BOLT_CIRCLE_START_ANGLE in resolved_codes
    )
    if not angle_confirmed and MISSING_BOLT_CIRCLE_START_ANGLE not in groups:
        groups[MISSING_BOLT_CIRCLE_START_ANGLE] = {
            "id": f"issue_{len(groups)}",
            "code": MISSING_BOLT_CIRCLE_START_ANGLE,
            "severity": "warning",
            "category": "geometry",
            "title": "Bolt circle start angle not confirmed",
            "message": (
                f"Bolt circle start angle not specified by user. "
                f"Plan uses {detected['start_angle_deg']}° "
                f"— confirm or enter manually."
            ),
            "actionable": True,
            "blocking": True,
            "source_messages": [
                "Bolt circle start angle assumed without operator confirmation."
            ],
            "affected_operations": list(range(n_ops)),
            "context": {
                "detected_start_angle_deg": detected["start_angle_deg"],
                "bolt_circle_params": detected,
            },
            "choices": [],
        }

    # Hole type
    hole_type_confirmed = (
        any("hole" in a.lower() and ("type" in a.lower() or "purpose" in a.lower())
            for a in confirmed)
        or MISSING_BOLT_CIRCLE_HOLE_TYPE in resolved_codes
    )
    if not hole_type_confirmed and MISSING_BOLT_CIRCLE_HOLE_TYPE not in groups:
        groups[MISSING_BOLT_CIRCLE_HOLE_TYPE] = {
            "id": f"issue_{len(groups)}",
            "code": MISSING_BOLT_CIRCLE_HOLE_TYPE,
            "severity": "warning",
            "category": "geometry",
            "title": "Hole type not specified",
            "message": (
                "Hole type not specified for bolt circle. "
                "This determines the correct drill diameter."
            ),
            "actionable": True,
            "blocking": True,
            "source_messages": [
                "Hole type not specified for bolt circle."
            ],
            "affected_operations": list(range(n_ops)),
            "context": {"bolt_circle_params": detected},
            "choices": [],
        }

    # Z reference — applies to any plan with negative-Z drill targets
    _detect_unconfirmed_z_reference(op, result, resolved_codes, confirmed,
                                     operations, groups)


def _detect_unconfirmed_z_reference(
    op: dict,
    result: dict,
    resolved_codes: set,
    confirmed: list[str],
    operations: list[dict],
    groups: dict[str, dict],
) -> None:
    """Add issue for unconfirmed Z0 workpiece reference."""
    if MISSING_Z_REFERENCE in resolved_codes:
        return
    if MISSING_Z_REFERENCE in groups:
        return
    if any("z" in a.lower() and "reference" in a.lower() for a in confirmed):
        return
    if any("z0" in a.lower() and "confirmed" in a.lower() for a in confirmed):
        return

    # Only trigger if there are drill operations with negative Z targets
    has_negative_z = any(
        isinstance(o, dict) and o.get("type") == "drill"
        and isinstance(o.get("parameters"), dict)
        and (o["parameters"].get("z", 0) < 0)
        for o in operations
    )
    if not has_negative_z:
        return

    # Find the target Z from first drill op for display
    first_z = None
    for o in operations:
        if isinstance(o, dict) and o.get("type") == "drill":
            first_z = o.get("parameters", {}).get("z")
            if first_z is not None:
                break

    groups[MISSING_Z_REFERENCE] = {
        "id": f"issue_{len(groups)}",
        "code": MISSING_Z_REFERENCE,
        "severity": "warning",
        "category": "geometry",
        "title": "Workpiece Z reference not confirmed",
        "message": (
            f"Plan assumes Z0 at top of workpiece (target Z = {first_z}). "
            f"Confirm or specify another Z reference."
        ),
        "actionable": True,
        "blocking": True,
        "source_messages": [
            "Z0 workpiece reference assumed without operator confirmation."
        ],
        "affected_operations": list(range(len(operations))),
        "context": {"detected_target_z": first_z},
        "choices": [],
    }


# ---------------------------------------------------------------------------
# Collect and deduplicate
# ---------------------------------------------------------------------------


def _gather_messages(result: dict) -> list[tuple[str, str]]:
    """Gather all warning/error messages from result dict.

    Returns list of (message, severity) tuples.
    """
    messages: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(msg: str, severity: str) -> None:
        if msg and msg not in seen:
            seen.add(msg)
            messages.append((msg, severity))

    # Top-level warnings / errors
    for w in result.get("warnings", []):
        _add(w, "warning")
    for e in result.get("errors", []):
        _add(e, "error")

    # validation sub-dict
    val = result.get("validation", {})
    if isinstance(val, dict):
        for w in val.get("warnings", []):
            _add(w, "warning")
        for e in val.get("errors", []):
            _add(e, "error")
        for f in val.get("findings", []):
            if isinstance(f, dict) and f.get("message"):
                sev = f.get("severity", "warning")
                if sev == "info":
                    continue
                _add(f["message"], sev)

    # safety_report sub-dict
    sr = result.get("safety_report", {})
    if isinstance(sr, dict):
        for w in sr.get("warnings", []):
            _add(w, "warning")
        for e in sr.get("errors", []):
            _add(e, "error")
        for f in sr.get("findings", []):
            if isinstance(f, dict) and f.get("message"):
                sev = f.get("severity", "warning")
                if sev == "info":
                    continue
                _add(f["message"], sev)

    # guardrails sub-dict
    gr = result.get("guardrails", {})
    if isinstance(gr, dict):
        for w in gr.get("warnings", []):
            _add(w, "warning")
        for e in gr.get("errors", []):
            _add(e, "error")

    # operation_plan warnings / missing_info
    op = result.get("operation_plan", {})
    if isinstance(op, dict):
        for w in op.get("warnings", []):
            _add(w, "warning")
        for mi in op.get("missing_info", []):
            _add(mi, "warning")

    return messages


def collect_interactive_issues(
    result: dict,
    prompt: str | None = None,
) -> list[dict]:
    """Collect and deduplicate all warnings/errors into canonical issues.

    Groups messages with the same issue code and context (e.g. same tool_id)
    into a single issue with merged affected_operations.

    Returns a list of issue dicts (plain dicts, not Pydantic models, for
    easy serialization and pipeline compatibility).
    """
    messages = _gather_messages(result)

    # Group by (code, context_key) where context_key depends on the code
    groups: dict[str, dict] = {}

    if not messages:
        # No warning messages, but may still have assumed defaults
        # or undocumented bolt circle assumptions
        _detect_assumed_defaults(result, groups)
        _detect_undocumented_bolt_circle(result, groups)
        issues = list(groups.values())
        for idx, issue in enumerate(issues):
            issue["id"] = f"issue_{idx}"
        return issues

    for msg, severity in messages:
        code, category, title, actionable, blocking = _classify_message(msg)
        op_idx = _extract_op_index(msg)
        tool_id = _extract_tool_id(msg)

        # Build a group key to merge similar issues
        if code == UNKNOWN_TOOL_ID and tool_id:
            group_key = f"{code}:{tool_id}"
        elif code in (MISSING_MATERIAL, MISSING_SAFE_Z, AGENT_GCODE_DISCARDED,
                      RELATIVE_POSITIONING, RELATIVE_NEGATIVE_Z,
                      MISSING_SPINDLE_SPEED, MISSING_FEEDRATE,
                      ASSUMED_FEEDRATE,
                      MISSING_BOLT_CIRCLE_CENTER,
                      MISSING_BOLT_CIRCLE_START_ANGLE,
                      MISSING_BOLT_CIRCLE_HOLE_TYPE):
            group_key = code
        else:
            # Use the full message as key for non-groupable issues
            group_key = f"{code}:{msg}"

        if group_key not in groups:
            # Determine effective severity
            effective_severity = severity
            if code == AGENT_GCODE_DISCARDED:
                effective_severity = "info"

            context: dict[str, Any] = {}
            if tool_id:
                context["tool_id"] = tool_id

            issue_message = msg
            issue_title = title
            # For grouped warnings, create a cleaner message
            if code == UNKNOWN_TOOL_ID and tool_id:
                issue_message = f"tool_id='{tool_id}' is not in the built-in tool library."
            elif code == MISSING_SPINDLE_SPEED:
                issue_message = (
                    "No spindle_speed/spindle_rpm specified. "
                    "Spindle start (M03) will be skipped."
                )
            elif code == MISSING_FEEDRATE:
                issue_message = "No feedrate specified for operation(s)."
            elif code == MISSING_MATERIAL:
                issue_title = "Material grade not specified"
                issue_message = (
                    "No confirmed material grade. "
                    "Specify a material for guardrail checks and documentation."
                )

            groups[group_key] = {
                "id": f"issue_{len(groups)}",
                "code": code,
                "severity": effective_severity,
                "category": category,
                "title": issue_title,
                "message": issue_message,
                "actionable": actionable,
                "blocking": blocking,
                "source_messages": [msg],
                "affected_operations": [op_idx] if op_idx is not None else [],
                "context": context,
                "choices": [],
            }
        else:
            existing = groups[group_key]
            if msg not in existing["source_messages"]:
                existing["source_messages"].append(msg)
            if op_idx is not None and op_idx not in existing["affected_operations"]:
                existing["affected_operations"].append(op_idx)
            # Upgrade severity if needed
            if severity == "error" and existing["severity"] != "error":
                existing["severity"] = "error"
                existing["blocking"] = True

    # --- Phase 2: Detect assumed defaults from assumptions list ---
    _detect_assumed_defaults(result, groups)

    # --- Phase 3: Detect undocumented bolt circle assumptions ---
    _detect_undocumented_bolt_circle(result, groups)

    # Sort: errors first, then actionable by category
    # (geometry/defaults before cutting parameters), then info.
    # Within actionable: postprocessor → geometry → material → parameters
    _CATEGORY_ORDER = {
        "defaults": 0,   # postprocessor, units, WCS
        "geometry": 1,   # bolt circle center, angle, hole type, Z ref
        "material": 2,
        "tool": 3,
        "parameter": 4,  # feedrate, spindle speed
    }
    issues = list(groups.values())
    issues.sort(key=lambda i: (
        0 if i["severity"] == "error" else 1 if i["actionable"] else 2,
        _CATEGORY_ORDER.get(i.get("category", ""), 5),
        i["code"],
    ))

    # Renumber IDs
    for idx, issue in enumerate(issues):
        issue["id"] = f"issue_{idx}"
        issue["affected_operations"].sort()

    return issues


# ---------------------------------------------------------------------------
# Choice builder
# ---------------------------------------------------------------------------


def build_issue_choices(
    issue: dict,
    result: dict,
    prompt: str | None = None,
) -> list[dict]:
    """Generate context-aware resolution choices for an issue.

    Returns a list of choice dicts with keys: key, label, description, action, payload.
    """
    code = issue.get("code", "")
    choices: list[dict] = []

    if code == UNKNOWN_TOOL_ID:
        choices = _build_unknown_tool_choices(issue, result, prompt)
    elif code == MISSING_MATERIAL:
        choices = _build_missing_material_choices(issue, result, prompt)
    elif code == UNKNOWN_MATERIAL:
        choices = _build_missing_material_choices(issue, result, prompt)
    elif code == MISSING_FEEDRATE:
        choices = _build_missing_feedrate_choices(issue, result)
    elif code == ASSUMED_FEEDRATE:
        choices = _build_assumed_feedrate_choices(issue, result)
    elif code == MISSING_SPINDLE_SPEED:
        choices = _build_missing_spindle_choices(issue, result)
    elif code == MISSING_SAFE_Z:
        choices = _build_missing_safe_z_choices(issue, result)
    elif code == MISSING_BOLT_CIRCLE_CENTER:
        choices = _build_missing_bolt_circle_center_choices(issue, result)
    elif code == MISSING_BOLT_CIRCLE_START_ANGLE:
        choices = _build_missing_bolt_circle_start_angle_choices(issue, result)
    elif code == MISSING_BOLT_CIRCLE_HOLE_TYPE:
        choices = _build_missing_bolt_circle_hole_type_choices(issue, result)
    elif code == MISSING_Z_REFERENCE:
        choices = _build_missing_z_reference_choices(issue, result)
    elif code == TOOL_DIAMETER_MISMATCH:
        choices = _build_diameter_mismatch_choices(issue, result)
    elif code == ASSUMED_POSTPROCESSOR:
        choices = _build_assumed_postprocessor_choices(issue, result)
    elif code == ASSUMED_UNITS:
        choices = _build_assumed_units_choices(issue, result)
    elif code == ASSUMED_WCS:
        choices = _build_assumed_wcs_choices(issue, result)
    elif code == ASSUMED_MACHINE_TYPE:
        choices = _build_assumed_machine_type_choices(issue, result)
    elif issue.get("actionable"):
        # Generic actionable fallback
        choices = [
            {"key": "1", "label": "Ignore this warning for this run",
             "action": "IGNORE_ONCE", "payload": {}},
            {"key": "2", "label": "Abort",
             "action": "ABORT", "payload": {}},
        ]

    return choices


def _build_unknown_tool_choices(
    issue: dict, result: dict, prompt: str | None = None,
) -> list[dict]:
    """Build choices for UNKNOWN_TOOL_ID."""
    choices: list[dict] = [
        {"key": "1", "label": "Ignore this warning for this run",
         "action": "IGNORE_ONCE", "payload": {}},
    ]

    # Find matching library tools
    try:
        from cnc.tools.tool_library import find_tools
        op_plan = result.get("operation_plan", {})
        machine_type = op_plan.get("machine_type") if isinstance(op_plan, dict) else None

        # Try to determine tool type and diameter from plan
        plan_tool_type = None
        plan_diameter = None
        if isinstance(op_plan, dict):
            for t in op_plan.get("tools", []):
                if isinstance(t, dict):
                    tid = str(t.get("tool_number", t.get("id", "")))
                    ctx_tid = issue.get("context", {}).get("tool_id", "")
                    if tid == ctx_tid or str(t.get("tool_number", "")) == ctx_tid:
                        plan_tool_type = t.get("type")
                        plan_diameter = t.get("diameter_mm") or t.get("diameter")
                        break

        candidates = find_tools(
            machine_type=machine_type,
            tool_type=plan_tool_type,
        )
        if candidates:
            # Sort by diameter proximity if we know the target
            if plan_diameter is not None:
                candidates.sort(key=lambda c: abs((c.get("diameter") or 0) - plan_diameter))

            desc_parts = []
            for c in candidates[:5]:
                d = c.get("diameter", "?")
                desc_parts.append(f"{c['id']} ({d} {c.get('units', 'mm')} {c.get('tool_type', '')})")
            desc = ", ".join(desc_parts)
            choices.append({
                "key": "2", "label": "Select a matching tool from the tool library",
                "description": f"Candidates: {desc}",
                "action": "SELECT_LIBRARY_TOOL",
                "payload": {"candidates": [c["id"] for c in candidates[:5]]},
            })
    except ImportError:
        pass

    choices.append({
        "key": "3",
        "label": "Use the tool described in the OperationPlan as a temporary custom tool",
        "action": "USE_TRANSIENT_CUSTOM_TOOL", "payload": {},
    })
    choices.append({
        "key": "4", "label": "Enter a tool_id manually",
        "action": "ENTER_TOOL_ID", "payload": {},
    })
    choices.append({
        "key": "5", "label": "Abort",
        "action": "ABORT", "payload": {},
    })

    return choices


def _infer_material_candidates(prompt: str | None) -> list[dict]:
    """Try to infer material candidates from the user prompt."""
    if not prompt:
        return []

    from cnc.tools.material_library import BUILTIN_MATERIALS

    prompt_lower = prompt.lower()
    candidates = []

    # Map common keywords to material IDs
    keyword_map = {
        "steel": ["mild_steel", "stainless_steel_generic"],
        "mild steel": ["mild_steel"],
        "stainless": ["stainless_steel_generic"],
        "aluminum": ["aluminum_6061", "aluminum_generic"],
        "aluminium": ["aluminum_6061", "aluminum_generic"],
        "6061": ["aluminum_6061"],
        "acrylic": ["acrylic"],
        "plywood": ["plywood"],
        "wood": ["plywood"],
        "brass": ["brass_generic"],
    }

    for keyword, mat_ids in keyword_map.items():
        if keyword in prompt_lower:
            for mid in mat_ids:
                if mid in BUILTIN_MATERIALS and mid not in [c["id"] for c in candidates]:
                    m = BUILTIN_MATERIALS[mid]
                    candidates.append({"id": mid, "name": m["name"]})

    return candidates


def _build_missing_material_choices(
    issue: dict, result: dict, prompt: str | None = None,
) -> list[dict]:
    """Build choices for MISSING_MATERIAL / UNKNOWN_MATERIAL."""
    choices: list[dict] = []
    candidates = _infer_material_candidates(prompt)

    if candidates:
        first = candidates[0]
        choices.append({
            "key": "1",
            "label": f"Use {first['id']} (inferred candidate from prompt: \"{first['name']}\")",
            "action": "SET_MATERIAL",
            "payload": {"material_id": first["id"]},
        })
        start_key = 2
    else:
        start_key = 1

    choices.append({
        "key": str(start_key),
        "label": "Select another material from library",
        "action": "SET_MATERIAL",
        "payload": {"select_from_library": True},
    })
    choices.append({
        "key": str(start_key + 1),
        "label": "Enter custom material",
        "action": "SET_CUSTOM_MATERIAL",
        "payload": {},
    })
    choices.append({
        "key": str(start_key + 2),
        "label": "Ignore for this run",
        "action": "IGNORE_ONCE",
        "payload": {},
    })
    choices.append({
        "key": str(start_key + 3),
        "label": "Abort",
        "action": "ABORT",
        "payload": {},
    })

    return choices


def _build_missing_feedrate_choices(issue: dict, result: dict) -> list[dict]:
    rec = _feedrate_recommendation(issue, result)

    choices: list[dict] = []
    if rec and rec.get("ok"):
        mid = (rec["feed_low"] + rec["feed_high"]) // 2
        choices.append({
            "key": "1",
            "label": f"Use recommended {mid} mm/min ({rec['note']})",
            "action": "SET_FEEDRATE",
            "payload": {"feedrate": mid},
        })
        choices.append({
            "key": "2", "label": "Enter feedrate manually",
            "action": "SET_FEEDRATE", "payload": {},
        })
        choices.append({
            "key": "3", "label": "Abort",
            "action": "ABORT", "payload": {},
        })
    else:
        choices.append({
            "key": "1", "label": "Enter feedrate manually",
            "action": "SET_FEEDRATE", "payload": {},
        })
        choices.append({
            "key": "2", "label": "Ignore and keep job blocked",
            "action": "IGNORE_ONCE", "payload": {},
        })
        choices.append({
            "key": "3", "label": "Abort",
            "action": "ABORT", "payload": {},
        })

    return choices


def _build_missing_spindle_choices(issue: dict, result: dict) -> list[dict]:
    # Try to compute a recommendation from material + tool diameter
    rec = _spindle_recommendation(issue, result)

    choices: list[dict] = []
    if rec and rec.get("ok"):
        mid = (rec["rpm_low"] + rec["rpm_high"]) // 2
        choices.append({
            "key": "1",
            "label": f"Use recommended {mid} RPM ({rec['note']})",
            "action": "SET_SPINDLE_SPEED",
            "payload": {"spindle_speed": mid},
        })
        choices.append({
            "key": "2", "label": "Enter spindle speed manually",
            "action": "SET_SPINDLE_SPEED", "payload": {},
        })
        choices.append({
            "key": "3", "label": "Continue without spindle start if supported",
            "action": "IGNORE_ONCE", "payload": {},
        })
        choices.append({
            "key": "4", "label": "Abort",
            "action": "ABORT", "payload": {},
        })
    else:
        choices.append({
            "key": "1", "label": "Enter spindle speed manually",
            "action": "SET_SPINDLE_SPEED", "payload": {},
        })
        choices.append({
            "key": "2", "label": "Continue without spindle start if supported",
            "action": "IGNORE_ONCE", "payload": {},
        })
        choices.append({
            "key": "3", "label": "Ignore for this run",
            "action": "IGNORE_ONCE", "payload": {},
        })
        choices.append({
            "key": "4", "label": "Abort",
            "action": "ABORT", "payload": {},
        })

    return choices


def _spindle_recommendation(issue: dict, result: dict) -> dict | None:
    """Try to compute an RPM recommendation from the result's material and tool diameter."""
    try:
        from cnc.tools.material_library import recommend_spindle_rpm
    except ImportError:
        return None

    # Find material category
    op_plan = result.get("operation_plan", {})
    material_id = op_plan.get("material") or result.get("material")

    # Find tool diameter from affected operations or tools list
    diameter: float | None = None
    operations = op_plan.get("operations", [])
    affected = issue.get("affected_operations", [])

    # Check affected operations for diameter info
    for idx in affected:
        if 0 <= idx < len(operations):
            op = operations[idx]
            d = op.get("tool_diameter") or op.get("parameters", {}).get("tool_diameter")
            if d:
                diameter = float(d)
                break

    # Fallback: check tools list
    if diameter is None:
        for t in op_plan.get("tools", []):
            d = t.get("diameter_mm") or t.get("diameter")
            if d:
                diameter = float(d)
                break

    return recommend_spindle_rpm(material_id, diameter)


def _build_assumed_feedrate_choices(issue: dict, result: dict) -> list[dict]:
    """Choices for when the agent assumed/invented a feedrate."""
    rec = _feedrate_recommendation(issue, result)

    # Find what the agent assumed
    agent_feedrate: float | None = None
    op_plan = result.get("operation_plan", {})
    operations = op_plan.get("operations", [])
    affected = issue.get("affected_operations", [])
    for idx in (affected or range(len(operations))):
        if 0 <= idx < len(operations):
            op = operations[idx]
            f = op.get("feedrate_mmpm") or op.get("feedrate")
            if f:
                agent_feedrate = float(f)
                break

    choices: list[dict] = []

    if rec and rec.get("ok"):
        mid = (rec["feed_low"] + rec["feed_high"]) // 2
        choices.append({
            "key": "1",
            "label": f"Use recommended {mid} mm/min ({rec['note']})",
            "action": "SET_FEEDRATE",
            "payload": {"feedrate": mid},
        })
        key = "2"
        if agent_feedrate:
            choices.append({
                "key": key,
                "label": f"Keep agent-assumed {int(agent_feedrate)} mm/min",
                "action": "IGNORE_ONCE",
                "payload": {},
            })
            key = "3"
        choices.append({
            "key": key, "label": "Enter feedrate manually",
            "action": "SET_FEEDRATE", "payload": {},
        })
        choices.append({
            "key": str(int(key) + 1), "label": "Abort",
            "action": "ABORT", "payload": {},
        })
    else:
        key_n = 1
        if agent_feedrate:
            choices.append({
                "key": str(key_n),
                "label": f"Keep agent-assumed {int(agent_feedrate)} mm/min",
                "action": "IGNORE_ONCE", "payload": {},
            })
            key_n += 1
        choices.append({
            "key": str(key_n), "label": "Enter feedrate manually",
            "action": "SET_FEEDRATE", "payload": {},
        })
        key_n += 1
        choices.append({
            "key": str(key_n), "label": "Abort",
            "action": "ABORT", "payload": {},
        })

    return choices


def _feedrate_recommendation(issue: dict, result: dict) -> dict | None:
    """Try to compute a feedrate recommendation from material, tool diameter, and RPM."""
    try:
        from cnc.tools.material_library import recommend_drill_feedrate
    except ImportError:
        return None

    op_plan = result.get("operation_plan", {})
    material_id = op_plan.get("material") or result.get("material")

    # Find tool diameter
    diameter: float | None = None
    operations = op_plan.get("operations", [])
    affected = issue.get("affected_operations", [])

    for idx in affected:
        if 0 <= idx < len(operations):
            op = operations[idx]
            d = op.get("tool_diameter") or op.get("parameters", {}).get("tool_diameter")
            if d:
                diameter = float(d)
                break

    if diameter is None:
        for t in op_plan.get("tools", []):
            d = t.get("diameter_mm") or t.get("diameter")
            if d:
                diameter = float(d)
                break

    # Check if spindle RPM is already set on any affected operation
    spindle_rpm: float | None = None
    for idx in affected:
        if 0 <= idx < len(operations):
            op = operations[idx]
            rpm = op.get("spindle_rpm") or op.get("spindle_speed")
            if rpm:
                spindle_rpm = float(rpm)
                break

    return recommend_drill_feedrate(material_id, diameter, spindle_rpm)


def _build_missing_safe_z_choices(issue: dict, result: dict) -> list[dict]:
    choices = [
        {"key": "1", "label": "Enter safe Z manually",
         "action": "SET_SAFE_Z", "payload": {}},
    ]

    # Check for machine profile default
    op = result.get("operation_plan", {})
    if isinstance(op, dict):
        try:
            from cnc.tools.machine_profiles import get_machine_profile
            profile_id = op.get("machine_profile")
            if profile_id:
                profile = get_machine_profile(profile_id)
                if profile and profile.get("defaults", {}).get("safe_z") is not None:
                    sz = profile["defaults"]["safe_z"]
                    choices.append({
                        "key": "2",
                        "label": f"Use machine profile default safe Z ({sz})",
                        "action": "USE_PROFILE_SAFE_Z",
                        "payload": {"safe_z": sz},
                    })
        except (ImportError, Exception):
            pass

    choices.append({
        "key": str(len(choices) + 1), "label": "Abort",
        "action": "ABORT", "payload": {},
    })

    return choices


def _build_missing_bolt_circle_center_choices(
    issue: dict, result: dict,
) -> list[dict]:
    """Build choices for MISSING_BOLT_CIRCLE_CENTER."""
    # If a default center was detected, offer confirmation
    ctx = issue.get("context", {})
    detected_cx = ctx.get("detected_center_x")
    detected_cy = ctx.get("detected_center_y")

    choices: list[dict] = []
    if detected_cx is not None and detected_cy is not None:
        choices.append({
            "key": "1",
            "label": f"Use X{detected_cx} / Y{detected_cy} (detected from plan)",
            "action": "CONFIRM_BOLT_CIRCLE_CENTER",
            "payload": {"center_x": detected_cx, "center_y": detected_cy},
        })
        choices.append({
            "key": "2", "label": "Enter bolt circle center (X, Y)",
            "action": "SET_BOLT_CIRCLE_CENTER", "payload": {},
        })
        choices.append({
            "key": "3", "label": "Abort",
            "action": "ABORT", "payload": {},
        })
    else:
        choices.append({
            "key": "1", "label": "Enter bolt circle center (X, Y)",
            "action": "SET_BOLT_CIRCLE_CENTER", "payload": {},
        })
        choices.append({
            "key": "2", "label": "Abort",
            "action": "ABORT", "payload": {},
        })
    return choices


def _build_missing_bolt_circle_start_angle_choices(
    issue: dict, result: dict,
) -> list[dict]:
    """Build choices for MISSING_BOLT_CIRCLE_START_ANGLE."""
    ctx = issue.get("context", {})
    detected_angle = ctx.get("detected_start_angle_deg")

    choices: list[dict] = []
    if detected_angle is not None:
        choices.append({
            "key": "1",
            "label": f"Use {detected_angle}° (detected from plan)",
            "action": "CONFIRM_BOLT_CIRCLE_START_ANGLE",
            "payload": {"start_angle_deg": detected_angle},
        })
        choices.append({
            "key": "2", "label": "Enter start angle (degrees)",
            "action": "SET_BOLT_CIRCLE_START_ANGLE", "payload": {},
        })
        choices.append({
            "key": "3", "label": "Abort",
            "action": "ABORT", "payload": {},
        })
    else:
        choices.append({
            "key": "1", "label": "Enter start angle (degrees)",
            "action": "SET_BOLT_CIRCLE_START_ANGLE", "payload": {},
        })
        choices.append({
            "key": "2", "label": "Abort",
            "action": "ABORT", "payload": {},
        })
    return choices


def _build_missing_bolt_circle_hole_type_choices(
    issue: dict, result: dict,
) -> list[dict]:
    """Build choices for MISSING_BOLT_CIRCLE_HOLE_TYPE."""
    op = result.get("operation_plan", {})
    bolt_size = _detect_bolt_size(op) if isinstance(op, dict) else None
    thread = _METRIC_THREAD_TABLE.get(bolt_size or "") if bolt_size else None

    if thread and bolt_size:
        cl_d = thread["clearance_mm"]
        td_d = thread["tap_drill_mm"]
        return [
            {"key": "1",
             "label": f"Clearance hole for {bolt_size} bolt (D{cl_d}mm)",
             "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
             "payload": {"hole_type": "clearance", "bolt_size": bolt_size,
                         "diameter_mm": cl_d}},
            {"key": "2",
             "label": f"{bolt_size} tap-drill / core hole (D{td_d}mm)",
             "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
             "payload": {"hole_type": "tap_drill", "bolt_size": bolt_size,
                         "diameter_mm": td_d}},
            {"key": "3", "label": "Enter custom diameter",
             "action": "SET_CUSTOM_DIAMETER", "payload": {}},
            {"key": "4", "label": "Abort",
             "action": "ABORT", "payload": {}},
        ]
    else:
        return [
            {"key": "1", "label": "Clearance hole (Durchgangsbohrung)",
             "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
             "payload": {"hole_type": "clearance"}},
            {"key": "2", "label": "Tap-drill / core hole (Kernloch)",
             "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
             "payload": {"hole_type": "tap_drill"}},
            {"key": "3", "label": "Enter custom diameter",
             "action": "SET_CUSTOM_DIAMETER", "payload": {}},
            {"key": "4", "label": "Abort",
             "action": "ABORT", "payload": {}},
        ]


def _build_missing_z_reference_choices(
    issue: dict, result: dict,
) -> list[dict]:
    """Build choices for MISSING_Z_REFERENCE."""
    target_z = issue.get("context", {}).get("detected_target_z", "?")
    return [
        {"key": "1",
         "label": f"Z0 at top of workpiece (target Z = {target_z})",
         "action": "CONFIRM_Z_REFERENCE",
         "payload": {"z_reference": "top_of_workpiece"}},
        {"key": "2", "label": "Abort",
         "action": "ABORT", "payload": {}},
    ]


def _build_diameter_mismatch_choices(issue: dict, result: dict) -> list[dict]:
    ctx = issue.get("context", {})
    plan_d = ctx.get("plan_diameter", "?")
    lib_d = ctx.get("library_diameter", "?")
    return [
        {"key": "1", "label": f"Keep OperationPlan diameter {plan_d} mm",
         "action": "KEEP_PLAN_DIAMETER", "payload": {}},
        {"key": "2", "label": f"Use registered tool diameter {lib_d} mm",
         "action": "USE_LIBRARY_DIAMETER",
         "payload": {"diameter": lib_d}},
        {"key": "3", "label": "Select another tool",
         "action": "SELECT_LIBRARY_TOOL", "payload": {}},
        {"key": "4", "label": "Enter custom diameter",
         "action": "SET_CUSTOM_DIAMETER", "payload": {}},
        {"key": "5", "label": "Abort",
         "action": "ABORT", "payload": {}},
    ]


def _build_assumed_postprocessor_choices(issue: dict, result: dict) -> list[dict]:
    """Build choices for ASSUMED_POSTPROCESSOR."""
    current = issue.get("context", {}).get("current_value", "fanuc")
    available = ["fanuc", "grbl", "linuxcnc"]
    choices: list[dict] = []

    for i, pp in enumerate(available, 1):
        label = f"Use {pp}"
        if pp == current:
            label += " (current default)"
        choices.append({
            "key": str(i), "label": label,
            "action": "SET_POSTPROCESSOR", "payload": {"postprocessor": pp},
        })

    choices.append({
        "key": str(len(available) + 1), "label": "Abort",
        "action": "ABORT", "payload": {},
    })
    return choices


def _build_assumed_units_choices(issue: dict, result: dict) -> list[dict]:
    """Build choices for ASSUMED_UNITS."""
    current = issue.get("context", {}).get("current_value", "mm")
    options = [("mm", "Millimeters"), ("inch", "Inches")]
    choices: list[dict] = []

    for i, (unit, desc) in enumerate(options, 1):
        label = f"Use {unit} ({desc})"
        if unit == current:
            label += " (current default)"
        choices.append({
            "key": str(i), "label": label,
            "action": "SET_UNITS", "payload": {"units": unit},
        })

    choices.append({
        "key": str(len(options) + 1), "label": "Abort",
        "action": "ABORT", "payload": {},
    })
    return choices


def _build_assumed_wcs_choices(issue: dict, result: dict) -> list[dict]:
    """Build choices for ASSUMED_WCS."""
    current = issue.get("context", {}).get("current_value", "G54")
    wcs_options = ["G54", "G55", "G56", "G57", "G58", "G59"]
    choices: list[dict] = []

    for i, wcs in enumerate(wcs_options, 1):
        label = f"Use {wcs}"
        if wcs == current:
            label += " (current default)"
        choices.append({
            "key": str(i), "label": label,
            "action": "SET_WCS", "payload": {"wcs": wcs},
        })

    choices.append({
        "key": str(len(wcs_options) + 1), "label": "Abort",
        "action": "ABORT", "payload": {},
    })
    return choices


def _build_assumed_machine_type_choices(issue: dict, result: dict) -> list[dict]:
    """Build choices for ASSUMED_MACHINE_TYPE."""
    machine_types = [
        ("mill", "Milling machine"),
        ("drill", "Drilling machine"),
        ("lathe", "Lathe / turning center"),
        ("laser", "Laser cutter"),
        ("grinder", "Grinding machine"),
        ("3d_printer", "3D printer"),
    ]
    choices: list[dict] = []

    for i, (mt, desc) in enumerate(machine_types, 1):
        choices.append({
            "key": str(i), "label": f"{mt} ({desc})",
            "action": "SET_MACHINE_TYPE", "payload": {"machine_type": mt},
        })

    choices.append({
        "key": str(len(machine_types) + 1), "label": "Abort",
        "action": "ABORT", "payload": {},
    })
    return choices


# ---------------------------------------------------------------------------
# Resolution actions
# ---------------------------------------------------------------------------


def apply_resolution_decision(
    result: dict,
    issue: dict,
    decision: dict,
) -> dict:
    """Apply a resolution decision to the result dict.

    Modifies result["operation_plan"] in place as needed and appends to
    result["resolution_log"].

    Returns the updated result dict.
    """
    action = decision.get("action", "")
    result.setdefault("resolution_log", [])

    op = result.get("operation_plan", {})
    if not isinstance(op, dict):
        op = {}

    log_entry: dict[str, Any] = {
        "issue_code": issue.get("code", ""),
        "action": action,
        "affected_operations": list(issue.get("affected_operations", [])),
    }

    if action == "IGNORE_ONCE":
        log_entry["before"] = {"ignored": False}
        log_entry["after"] = {"ignored": True}

    elif action == "ABORT":
        result["aborted"] = True
        log_entry["before"] = {}
        log_entry["after"] = {"aborted": True}

    elif action == "SELECT_LIBRARY_TOOL":
        tool_id = decision.get("payload", {}).get("tool_id", "")
        if tool_id:
            _apply_library_tool(op, issue, tool_id, log_entry)

    elif action == "USE_TRANSIENT_CUSTOM_TOOL":
        _apply_transient_custom_tool(op, issue, log_entry)

    elif action == "ENTER_TOOL_ID":
        tool_id = decision.get("payload", {}).get("tool_id", "")
        if tool_id:
            _apply_entered_tool_id(op, issue, tool_id, log_entry)

    elif action == "SET_MATERIAL":
        material_id = decision.get("payload", {}).get("material_id", "")
        if material_id:
            log_entry["before"] = {"material": op.get("material")}
            op["material"] = material_id
            log_entry["after"] = {"material": material_id}

    elif action == "SET_CUSTOM_MATERIAL":
        material_name = decision.get("payload", {}).get("material_name", "")
        if material_name:
            log_entry["before"] = {"material": op.get("material")}
            op["material"] = material_name
            log_entry["after"] = {"material": material_name}

    elif action == "SET_FEEDRATE":
        feedrate = decision.get("payload", {}).get("feedrate")
        if feedrate is not None:
            _apply_feedrate(op, issue, float(feedrate), log_entry)

    elif action == "SET_SPINDLE_SPEED":
        rpm = decision.get("payload", {}).get("spindle_speed")
        if rpm is not None:
            _apply_spindle_speed(op, issue, float(rpm), log_entry)

    elif action == "SET_SAFE_Z":
        safe_z = decision.get("payload", {}).get("safe_z")
        if safe_z is not None:
            log_entry["before"] = {"safe_z": op.get("safe_z")}
            op["safe_z"] = float(safe_z)
            log_entry["after"] = {"safe_z": float(safe_z)}

    elif action == "USE_PROFILE_SAFE_Z":
        safe_z = decision.get("payload", {}).get("safe_z")
        if safe_z is not None:
            log_entry["before"] = {"safe_z": op.get("safe_z")}
            op["safe_z"] = float(safe_z)
            log_entry["after"] = {"safe_z": float(safe_z)}

    elif action == "KEEP_PLAN_DIAMETER":
        log_entry["before"] = {}
        log_entry["after"] = {"kept_plan_diameter": True}

    elif action == "USE_LIBRARY_DIAMETER":
        diameter = decision.get("payload", {}).get("diameter")
        if diameter is not None:
            _apply_diameter(op, issue, float(diameter), log_entry)

    elif action == "SET_CUSTOM_DIAMETER":
        diameter = decision.get("payload", {}).get("diameter")
        if diameter is not None:
            _apply_diameter(op, issue, float(diameter), log_entry)

    elif action == "CONFIRM_BOLT_CIRCLE_CENTER":
        cx = decision.get("payload", {}).get("center_x")
        cy = decision.get("payload", {}).get("center_y")
        log_entry["before"] = {"center_x": cx, "center_y": cy}
        log_entry["after"] = {"center_x": cx, "center_y": cy, "confirmed": True}
        op.setdefault("assumptions", []).append(
            f"Confirmed bolt circle center: X{cx} / Y{cy}"
        )

    elif action == "SET_BOLT_CIRCLE_CENTER":
        cx = decision.get("payload", {}).get("center_x")
        cy = decision.get("payload", {}).get("center_y")
        if cx is not None and cy is not None:
            _recalculate_bolt_circle(op, issue, log_entry,
                                     new_center_x=float(cx), new_center_y=float(cy))

    elif action == "CONFIRM_BOLT_CIRCLE_START_ANGLE":
        angle = decision.get("payload", {}).get("start_angle_deg")
        log_entry["before"] = {"start_angle_deg": angle}
        log_entry["after"] = {"start_angle_deg": angle, "confirmed": True}
        op.setdefault("assumptions", []).append(
            f"Confirmed bolt circle start angle: {angle}°"
        )

    elif action == "SET_BOLT_CIRCLE_START_ANGLE":
        angle = decision.get("payload", {}).get("start_angle_deg")
        if angle is not None:
            _recalculate_bolt_circle(op, issue, log_entry,
                                     new_start_angle_deg=float(angle))

    elif action == "SET_BOLT_CIRCLE_HOLE_TYPE":
        hole_type = decision.get("payload", {}).get("hole_type")
        if hole_type:
            _apply_hole_purpose(op, hole_type, decision.get("payload", {}),
                                log_entry)

    elif action == "CONFIRM_Z_REFERENCE":
        z_ref = decision.get("payload", {}).get("z_reference", "top_of_workpiece")
        log_entry["before"] = {"z_reference": None}
        log_entry["after"] = {"z_reference": z_ref, "confirmed": True}
        op.setdefault("assumptions", []).append(
            f"Confirmed Z reference: Z0 at {z_ref.replace('_', ' ')}"
        )

    elif action == "SET_POSTPROCESSOR":
        pp = decision.get("payload", {}).get("postprocessor", "fanuc")
        log_entry["before"] = {"postprocessor": result.get("postprocessor")}
        result["postprocessor"] = pp
        op["postprocessor"] = pp
        log_entry["after"] = {"postprocessor": pp}
        # Remove the assumption
        _remove_assumption(op, "Assumed postprocessor:")

    elif action == "SET_UNITS":
        units = decision.get("payload", {}).get("units", "mm")
        log_entry["before"] = {"units": op.get("units")}
        op["units"] = units
        log_entry["after"] = {"units": units}
        _remove_assumption(op, "Assumed units:")

    elif action == "SET_WCS":
        wcs = decision.get("payload", {}).get("wcs", "G54")
        log_entry["before"] = {"work_coordinate_system": op.get("work_coordinate_system")}
        op["work_coordinate_system"] = wcs
        log_entry["after"] = {"work_coordinate_system": wcs}
        _remove_assumption(op, "Assumed work coordinate system:")

    elif action == "SET_MACHINE_TYPE":
        mt = decision.get("payload", {}).get("machine_type", "mill")
        log_entry["before"] = {"machine_type": op.get("machine_type")}
        op["machine_type"] = mt
        result["machine_type"] = mt
        log_entry["after"] = {"machine_type": mt}
        _remove_assumption(op, "Machine type not specified")

    result["operation_plan"] = op
    result["resolution_log"].append(log_entry)

    # Clean up missing_info and warnings that are no longer accurate
    if action not in ("IGNORE_ONCE", "ABORT"):
        _cleanup_resolved_plan_state(op, issue)

    return result


# Issue code → patterns to remove from missing_info and warnings after resolution
_RESOLVED_CLEANUP_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    MISSING_FEEDRATE: [
        re.compile(r"feedrate", re.I),
    ],
    ASSUMED_FEEDRATE: [
        re.compile(r"feedrate.*assumed|assumed.*feedrate", re.I),
    ],
    MISSING_SPINDLE_SPEED: [
        re.compile(r"spindle", re.I),
    ],
    MISSING_SAFE_Z: [
        re.compile(r"safe.?z", re.I),
    ],
    MISSING_MATERIAL: [
        re.compile(r"material", re.I),
    ],
    UNKNOWN_MATERIAL: [
        re.compile(r"material", re.I),
    ],
    MISSING_BOLT_CIRCLE_CENTER: [
        re.compile(r"bolt circle center|center_[xy]", re.I),
    ],
    MISSING_BOLT_CIRCLE_START_ANGLE: [
        re.compile(r"start.?angle|start_angle_deg", re.I),
    ],
    MISSING_BOLT_CIRCLE_HOLE_TYPE: [
        re.compile(r"hole.?type", re.I),
    ],
}


def _cleanup_resolved_plan_state(op: dict, issue: dict) -> None:
    """Remove stale missing_info and warnings entries after a resolution.

    When an issue is resolved (e.g. feedrate set by operator), the original
    warning/missing_info strings that triggered the issue must be removed
    from the plan so that re-validation does not flag them again.
    """
    code = issue.get("code", "")
    patterns = _RESOLVED_CLEANUP_PATTERNS.get(code)
    if not patterns:
        return

    def _matches(text: str) -> bool:
        return any(p.search(text) for p in patterns)

    # Clean missing_info
    mi = op.get("missing_info")
    if isinstance(mi, list):
        op["missing_info"] = [entry for entry in mi if not _matches(str(entry))]

    # Clean warnings
    ws = op.get("warnings")
    if isinstance(ws, list):
        op["warnings"] = [w for w in ws if not _matches(str(w))]


def _apply_library_tool(op: dict, issue: dict, tool_id: str, log_entry: dict) -> None:
    """Apply a library tool selection to the plan."""
    affected = issue.get("affected_operations", [])
    ctx_tool_id = issue.get("context", {}).get("tool_id", "")

    log_entry["before"] = {"tool_id": ctx_tool_id}

    # Update tools list
    tools = op.get("tools", [])
    for t in tools:
        if isinstance(t, dict):
            tid = str(t.get("tool_number", t.get("id", "")))
            if tid == ctx_tool_id:
                t["id"] = tool_id

    # Update operations
    operations = op.get("operations", [])
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            operations[idx]["tool_id"] = tool_id

    log_entry["after"] = {"tool_id": tool_id}


def _apply_transient_custom_tool(op: dict, issue: dict, log_entry: dict) -> None:
    """Create a transient custom tool from the OperationPlan tool description."""
    ctx_tool_id = issue.get("context", {}).get("tool_id", "")
    affected = issue.get("affected_operations", [])

    # Find the plan tool entry
    tools = op.get("tools", [])
    plan_tool = None
    plan_tool_idx = None
    for i, t in enumerate(tools):
        if isinstance(t, dict):
            tid = str(t.get("tool_number", t.get("id", "")))
            if tid == ctx_tool_id:
                plan_tool = t
                plan_tool_idx = i
                break

    if plan_tool is None:
        log_entry["before"] = {"tool_id": ctx_tool_id}
        log_entry["after"] = {"error": "No matching tool found in plan"}
        return

    # Create transient ID
    tool_num = plan_tool.get("tool_number", ctx_tool_id)
    custom_id = f"custom_T{tool_num}"

    description = plan_tool.get("description", plan_tool.get("name", f"Custom tool T{tool_num}"))
    diameter = plan_tool.get("diameter_mm", plan_tool.get("diameter"))
    tool_type = plan_tool.get("type", "unknown")

    log_entry["before"] = {"tool_id": ctx_tool_id, "plan_tool": copy.deepcopy(plan_tool)}

    # Update the tool entry
    plan_tool["id"] = custom_id
    plan_tool["name"] = description
    plan_tool["source"] = "operation_plan"
    if "tool_type" not in plan_tool and tool_type:
        plan_tool["tool_type"] = tool_type

    # Update operations
    operations = op.get("operations", [])
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            operations[idx]["tool_id"] = custom_id
    # Also update any operation that references this tool_number
    for o in operations:
        if isinstance(o, dict):
            tn = o.get("tool_number")
            if tn is not None and str(tn) == str(tool_num):
                o["tool_id"] = custom_id

    log_entry["after"] = {
        "custom_tool_id": custom_id,
        "description": description,
        "diameter": diameter,
        "tool_type": tool_type,
    }


def _apply_entered_tool_id(op: dict, issue: dict, tool_id: str, log_entry: dict) -> None:
    """Apply a manually entered tool_id."""
    _apply_library_tool(op, issue, tool_id, log_entry)


def _apply_feedrate(op: dict, issue: dict, feedrate: float, log_entry: dict) -> None:
    """Set feedrate on affected operations (canonical field only)."""
    affected = issue.get("affected_operations", [])
    operations = op.get("operations", [])
    before_values = {}
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            before_values[idx] = operations[idx].get("feedrate_mmpm") or operations[idx].get("feedrate")
            operations[idx]["feedrate_mmpm"] = feedrate
            operations[idx].pop("feedrate", None)  # remove deprecated alias
    # If no specific operations affected, apply to all that lack canonical feedrate
    if not affected:
        for i, o in enumerate(operations):
            if isinstance(o, dict) and not o.get("feedrate_mmpm"):
                before_values[i] = o.get("feedrate")
                o["feedrate_mmpm"] = feedrate
                o.pop("feedrate", None)
    log_entry["before"] = {"feedrates": before_values}
    log_entry["after"] = {"feedrate_mmpm": feedrate}


def _apply_spindle_speed(op: dict, issue: dict, rpm: float, log_entry: dict) -> None:
    """Set spindle speed on affected operations (canonical field only)."""
    affected = issue.get("affected_operations", [])
    operations = op.get("operations", [])
    before_values = {}
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            before_values[idx] = operations[idx].get("spindle_rpm") or operations[idx].get("spindle_speed")
            operations[idx]["spindle_rpm"] = int(rpm)
            operations[idx].pop("spindle_speed", None)  # remove deprecated alias
    if not affected:
        for i, o in enumerate(operations):
            if isinstance(o, dict) and not o.get("spindle_rpm"):
                before_values[i] = o.get("spindle_speed")
                o["spindle_rpm"] = int(rpm)
                o.pop("spindle_speed", None)
    log_entry["before"] = {"spindle_speeds": before_values}
    log_entry["after"] = {"spindle_rpm": int(rpm)}


def _apply_diameter(op: dict, issue: dict, diameter: float, log_entry: dict) -> None:
    """Set tool diameter on affected tools and operations (canonical field only)."""
    affected = issue.get("affected_operations", [])
    ctx_tool_id = issue.get("context", {}).get("tool_id", "")

    log_entry["before"] = {}

    tools = op.get("tools", [])
    for t in tools:
        if isinstance(t, dict):
            tid = str(t.get("tool_number", t.get("id", "")))
            if tid == ctx_tool_id:
                log_entry["before"]["tool_diameter"] = t.get("diameter_mm") or t.get("diameter")
                t["diameter_mm"] = diameter
                t.pop("diameter", None)  # remove deprecated alias

    operations = op.get("operations", [])
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            params = operations[idx].get("parameters", {})
            if "tool_diameter" in params:
                params["tool_diameter"] = diameter

    log_entry["after"] = {"diameter_mm": diameter}


def _apply_bolt_circle_param(
    op: dict, issue: dict, param_name: str, value: Any, log_entry: dict,
) -> None:
    """Set a bolt circle parameter on affected operations."""
    affected = issue.get("affected_operations", [])
    operations = op.get("operations", [])
    before_values: dict[int, Any] = {}

    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            params = operations[idx].setdefault("parameters", {})
            before_values[idx] = params.get(param_name)
            params[param_name] = value

    # If no specific operations affected, apply to all bolt_circle operations
    if not affected:
        for i, o in enumerate(operations):
            if isinstance(o, dict) and o.get("type") == "bolt_circle":
                params = o.setdefault("parameters", {})
                if params.get(param_name) is None:
                    before_values[i] = None
                    params[param_name] = value

    log_entry["before"] = log_entry.get("before", {})
    log_entry["before"][param_name] = before_values
    log_entry["after"] = log_entry.get("after", {})
    log_entry["after"][param_name] = value


def _apply_hole_purpose(
    op: dict,
    hole_type: str,
    payload: dict,
    log_entry: dict,
) -> None:
    """Atomically update tool diameter, description, and assumption
    when the operator confirms the hole purpose.

    This ensures that tap_drill → correct tap-drill diameter, and
    clearance → correct clearance diameter — never a mismatch.
    """
    bolt_size = payload.get("bolt_size") or _detect_bolt_size(op)
    explicit_diameter = payload.get("diameter_mm")

    # Determine target diameter
    if explicit_diameter is not None:
        diameter = float(explicit_diameter)
    elif bolt_size and bolt_size in _METRIC_THREAD_TABLE:
        thread = _METRIC_THREAD_TABLE[bolt_size]
        if hole_type == "tap_drill":
            diameter = thread["tap_drill_mm"]
        elif hole_type == "clearance":
            diameter = thread["clearance_mm"]
        else:
            diameter = None
    else:
        diameter = None

    # Build description
    if bolt_size and diameter is not None:
        if hole_type == "tap_drill":
            desc = f"{diameter}mm HSS twist drill ({bolt_size} tap drill)"
        elif hole_type == "clearance":
            desc = f"{diameter}mm HSS twist drill ({bolt_size} clearance)"
        else:
            desc = f"{diameter}mm drill"
    elif diameter is not None:
        desc = f"{diameter}mm drill ({hole_type})"
    else:
        desc = None

    # Record before state
    tools = op.get("tools", [])
    old_tool_info = {}
    for t in tools:
        if isinstance(t, dict) and t.get("type") == "drill":
            old_tool_info = {
                "diameter_mm": t.get("diameter_mm"),
                "description": t.get("description"),
            }
            break

    log_entry["before"] = {
        "hole_type": None,
        "tool": old_tool_info,
    }

    # Update all drill tools
    if diameter is not None:
        for t in tools:
            if isinstance(t, dict) and t.get("type") == "drill":
                t["diameter_mm"] = diameter
                if desc:
                    t["description"] = desc

    log_entry["after"] = {
        "hole_type": hole_type,
        "bolt_size": bolt_size,
        "diameter_mm": diameter,
        "description": desc,
    }

    op.setdefault("assumptions", []).append(
        f"Confirmed hole purpose: {hole_type}"
        + (f" ({bolt_size} → D{diameter}mm)" if bolt_size and diameter else "")
    )


def _recalculate_bolt_circle(
    op: dict,
    issue: dict,
    log_entry: dict,
    new_center_x: float | None = None,
    new_center_y: float | None = None,
    new_start_angle_deg: float | None = None,
) -> None:
    """Recalculate bolt circle hole positions after a parameter change.

    Detects the current bolt circle parameters from the operations,
    applies the change, and updates all hole coordinates.
    """
    operations = op.get("operations", [])
    detected = _detect_bolt_circle_params_from_ops(operations)
    if detected is None:
        log_entry["before"] = {}
        log_entry["after"] = {"error": "Could not detect bolt circle parameters"}
        return

    # Build new parameters (use detected values as base)
    cx = new_center_x if new_center_x is not None else detected["center_x"]
    cy = new_center_y if new_center_y is not None else detected["center_y"]
    start_angle = (
        new_start_angle_deg if new_start_angle_deg is not None
        else detected["start_angle_deg"]
    )
    radius = detected["radius"]
    num_holes = detected["num_holes"]

    log_entry["before"] = {
        "center_x": detected["center_x"],
        "center_y": detected["center_y"],
        "start_angle_deg": detected["start_angle_deg"],
    }

    # Recalculate positions
    from cnc.tools.drill_tools import calculate_bolt_circle_positions

    new_positions = calculate_bolt_circle_positions(
        cx, cy, radius, num_holes, start_angle,
    )

    # Update operations
    for i, pos in enumerate(new_positions):
        if i < len(operations) and isinstance(operations[i], dict):
            params = operations[i].setdefault("parameters", {})
            params["x"] = pos["x"]
            params["y"] = pos["y"]

    log_entry["after"] = {
        "center_x": cx,
        "center_y": cy,
        "start_angle_deg": start_angle,
        "positions_updated": len(new_positions),
    }

    # Document the confirmed value
    if new_center_x is not None or new_center_y is not None:
        op.setdefault("assumptions", []).append(
            f"Confirmed bolt circle center: X{cx} / Y{cy}"
        )
    if new_start_angle_deg is not None:
        op.setdefault("assumptions", []).append(
            f"Confirmed bolt circle start angle: {start_angle}°"
        )


def _remove_assumption(op: dict, prefix: str) -> None:
    """Remove an assumption entry whose text starts with prefix."""
    assumptions = op.get("assumptions", [])
    op["assumptions"] = [a for a in assumptions if not a.startswith(prefix)]
