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
# Issue code constants
# ---------------------------------------------------------------------------

UNKNOWN_TOOL_ID = "UNKNOWN_TOOL_ID"
MISSING_TOOL = "MISSING_TOOL"
TOOL_DIAMETER_MISMATCH = "TOOL_DIAMETER_MISMATCH"
UNSUPPORTED_TOOL_OPERATION = "UNSUPPORTED_TOOL_OPERATION"

MISSING_MATERIAL = "MISSING_MATERIAL"
UNKNOWN_MATERIAL = "UNKNOWN_MATERIAL"

MISSING_FEEDRATE = "MISSING_FEEDRATE"
MISSING_SPINDLE_SPEED = "MISSING_SPINDLE_SPEED"
MISSING_SAFE_Z = "MISSING_SAFE_Z"

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
    (re.compile(r"no spindle_speed|spindle.*missing|missing.*spindle", re.I),
     MISSING_SPINDLE_SPEED, "parameter", "Missing spindle speed", True, False),
    (re.compile(r"Missing required field: safe_z", re.I),
     MISSING_SAFE_Z, "parameter", "Missing safe Z", True, True),

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
        _detect_assumed_defaults(result, groups)
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
                      RELATIVE_POSITIONING, RELATIVE_NEGATIVE_Z):
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
            # For grouped tool warnings, create a cleaner message
            if code == UNKNOWN_TOOL_ID and tool_id:
                issue_message = f"tool_id='{tool_id}' is not in the built-in tool library."

            groups[group_key] = {
                "id": f"issue_{len(groups)}",
                "code": code,
                "severity": effective_severity,
                "category": category,
                "title": title,
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

    # Sort: errors first, then actionable warnings, then info
    issues = list(groups.values())
    issues.sort(key=lambda i: (
        0 if i["severity"] == "error" else 1 if i["actionable"] else 2,
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
    elif code == MISSING_SPINDLE_SPEED:
        choices = _build_missing_spindle_choices(issue, result)
    elif code == MISSING_SAFE_Z:
        choices = _build_missing_safe_z_choices(issue, result)
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
    return [
        {"key": "1", "label": "Enter feedrate manually",
         "action": "SET_FEEDRATE", "payload": {}},
        {"key": "2", "label": "Ignore and keep job blocked",
         "action": "IGNORE_ONCE", "payload": {}},
        {"key": "3", "label": "Abort",
         "action": "ABORT", "payload": {}},
    ]


def _build_missing_spindle_choices(issue: dict, result: dict) -> list[dict]:
    return [
        {"key": "1", "label": "Enter spindle speed manually",
         "action": "SET_SPINDLE_SPEED", "payload": {}},
        {"key": "2", "label": "Continue without spindle start if supported",
         "action": "IGNORE_ONCE", "payload": {}},
        {"key": "3", "label": "Ignore for this run",
         "action": "IGNORE_ONCE", "payload": {}},
        {"key": "4", "label": "Abort",
         "action": "ABORT", "payload": {}},
    ]


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

    return result


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
    """Set feedrate on affected operations."""
    affected = issue.get("affected_operations", [])
    operations = op.get("operations", [])
    before_values = {}
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            before_values[idx] = operations[idx].get("feedrate_mmpm") or operations[idx].get("feedrate")
            operations[idx]["feedrate_mmpm"] = feedrate
            operations[idx]["feedrate"] = feedrate
    # If no specific operations affected, apply to all
    if not affected:
        for i, o in enumerate(operations):
            if isinstance(o, dict) and not o.get("feedrate_mmpm") and not o.get("feedrate"):
                before_values[i] = None
                o["feedrate_mmpm"] = feedrate
                o["feedrate"] = feedrate
    log_entry["before"] = {"feedrates": before_values}
    log_entry["after"] = {"feedrate": feedrate}


def _apply_spindle_speed(op: dict, issue: dict, rpm: float, log_entry: dict) -> None:
    """Set spindle speed on affected operations."""
    affected = issue.get("affected_operations", [])
    operations = op.get("operations", [])
    before_values = {}
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            before_values[idx] = operations[idx].get("spindle_rpm") or operations[idx].get("spindle_speed")
            operations[idx]["spindle_rpm"] = int(rpm)
            operations[idx]["spindle_speed"] = int(rpm)
    if not affected:
        for i, o in enumerate(operations):
            if isinstance(o, dict) and not o.get("spindle_rpm") and not o.get("spindle_speed"):
                before_values[i] = None
                o["spindle_rpm"] = int(rpm)
                o["spindle_speed"] = int(rpm)
    log_entry["before"] = {"spindle_speeds": before_values}
    log_entry["after"] = {"spindle_speed": int(rpm)}


def _apply_diameter(op: dict, issue: dict, diameter: float, log_entry: dict) -> None:
    """Set tool diameter on affected tools and operations."""
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
                t["diameter"] = diameter

    operations = op.get("operations", [])
    for idx in affected:
        if 0 <= idx < len(operations) and isinstance(operations[idx], dict):
            params = operations[idx].get("parameters", {})
            if "tool_diameter" in params:
                params["tool_diameter"] = diameter

    log_entry["after"] = {"diameter": diameter}


def _remove_assumption(op: dict, prefix: str) -> None:
    """Remove an assumption entry whose text starts with prefix."""
    assumptions = op.get("assumptions", [])
    op["assumptions"] = [a for a in assumptions if not a.startswith(prefix)]
