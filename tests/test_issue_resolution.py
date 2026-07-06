"""Tests for cnc/tools/issue_resolution.py — issue collection, deduplication, and resolution."""

import pytest
from cnc.tools.issue_resolution import (
    collect_interactive_issues,
    build_issue_choices,
    apply_resolution_decision,
    UNKNOWN_TOOL_ID,
    MISSING_MATERIAL,
    MISSING_FEEDRATE,
    MISSING_SPINDLE_SPEED,
    MISSING_SAFE_Z,
    AGENT_GCODE_DISCARDED,
    ASSUMED_POSTPROCESSOR,
    ASSUMED_UNITS,
    ASSUMED_WCS,
    ASSUMED_MACHINE_TYPE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_result_with_tool_warnings(count: int = 6, tool_id: str = "1") -> dict:
    """Simulate result with N duplicate unknown tool warnings."""
    warnings = [
        f"Operation {i} references tool_id='{tool_id}' "
        "which is not in the built-in tool library."
        for i in range(count)
    ]
    return {
        "warnings": warnings,
        "errors": [],
        "validation": {"ok": True, "warnings": [], "errors": []},
        "operation_plan": {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "tools": [
                {
                    "tool_number": 1,
                    "description": "8.5mm HSS twist drill (M8 clearance hole)",
                    "diameter_mm": 8.5,
                    "type": "drill",
                }
            ],
            "operations": [
                {
                    "tool_number": 1,
                    "type": "drill",
                    "feedrate_mmpm": 80,
                    "spindle_rpm": 1200,
                    "parameters": {"x": i * 10, "y": 0, "z": -18},
                }
                for i in range(count)
            ],
        },
    }


def _make_result_with_material_warnings() -> dict:
    """Simulate result with duplicate material warnings from validation and guardrails."""
    mat_msg = "Material was not specified."
    return {
        "warnings": [mat_msg],
        "errors": [],
        "validation": {
            "ok": True,
            "warnings": [
                "Material was not specified. Specify a material for guardrail checks and documentation."
            ],
            "errors": [],
        },
        "guardrails": {
            "ok": True,
            "warnings": ["Material was not specified."],
            "errors": [],
        },
        "operation_plan": {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "material": None,
            "tools": [],
            "operations": [],
        },
    }


# ---------------------------------------------------------------------------
# A) Duplicate unknown tool warnings grouped
# ---------------------------------------------------------------------------


def test_tool_warnings_grouped_into_one_issue():
    result = _make_result_with_tool_warnings(6, "1")
    issues = collect_interactive_issues(result)

    tool_issues = [i for i in issues if i["code"] == UNKNOWN_TOOL_ID]
    assert len(tool_issues) == 1


def test_tool_warnings_affected_operations():
    result = _make_result_with_tool_warnings(6, "1")
    issues = collect_interactive_issues(result)

    tool_issues = [i for i in issues if i["code"] == UNKNOWN_TOOL_ID]
    assert tool_issues[0]["affected_operations"] == [0, 1, 2, 3, 4, 5]


def test_tool_warnings_context_has_tool_id():
    result = _make_result_with_tool_warnings(6, "1")
    issues = collect_interactive_issues(result)

    tool_issues = [i for i in issues if i["code"] == UNKNOWN_TOOL_ID]
    assert tool_issues[0]["context"]["tool_id"] == "1"


def test_tool_warnings_is_actionable():
    result = _make_result_with_tool_warnings(6, "1")
    issues = collect_interactive_issues(result)

    tool_issues = [i for i in issues if i["code"] == UNKNOWN_TOOL_ID]
    assert tool_issues[0]["actionable"] is True


# ---------------------------------------------------------------------------
# B) Duplicate material warnings
# ---------------------------------------------------------------------------


def test_material_warnings_grouped():
    result = _make_result_with_material_warnings()
    issues = collect_interactive_issues(result)

    mat_issues = [i for i in issues if i["code"] == MISSING_MATERIAL]
    assert len(mat_issues) == 1


# ---------------------------------------------------------------------------
# C) Unknown tool choices
# ---------------------------------------------------------------------------


def test_unknown_tool_choices_actions():
    result = _make_result_with_tool_warnings(6, "1")
    issues = collect_interactive_issues(result)
    tool_issue = [i for i in issues if i["code"] == UNKNOWN_TOOL_ID][0]

    choices = build_issue_choices(tool_issue, result)
    actions = {c["action"] for c in choices}

    assert "IGNORE_ONCE" in actions
    assert "SELECT_LIBRARY_TOOL" in actions
    assert "USE_TRANSIENT_CUSTOM_TOOL" in actions
    assert "ENTER_TOOL_ID" in actions
    assert "ABORT" in actions


# ---------------------------------------------------------------------------
# D) Apply transient custom tool
# ---------------------------------------------------------------------------


def test_apply_transient_custom_tool():
    result = _make_result_with_tool_warnings(6, "1")
    issues = collect_interactive_issues(result)
    tool_issue = [i for i in issues if i["code"] == UNKNOWN_TOOL_ID][0]

    decision = {
        "action": "USE_TRANSIENT_CUSTOM_TOOL",
        "payload": {},
    }

    result = apply_resolution_decision(result, tool_issue, decision)
    op = result["operation_plan"]

    # Tool should have a stable local id
    assert op["tools"][0]["id"] == "custom_T1"
    assert op["tools"][0]["source"] == "operation_plan"

    # Operations should reference the custom id
    for o in op["operations"]:
        assert o["tool_id"] == "custom_T1"

    # Re-collecting issues should not produce UNKNOWN_TOOL_ID for custom_T1
    # (since custom_T1 is now a plan-local tool)
    assert "resolution_log" in result
    assert len(result["resolution_log"]) == 1
    assert result["resolution_log"][0]["action"] == "USE_TRANSIENT_CUSTOM_TOOL"


# ---------------------------------------------------------------------------
# E) Material resolution
# ---------------------------------------------------------------------------


def test_set_material():
    result = _make_result_with_material_warnings()
    issues = collect_interactive_issues(result)
    mat_issue = [i for i in issues if i["code"] == MISSING_MATERIAL][0]

    decision = {
        "action": "SET_MATERIAL",
        "payload": {"material_id": "mild_steel"},
    }

    result = apply_resolution_decision(result, mat_issue, decision)
    assert result["operation_plan"]["material"] == "mild_steel"


# ---------------------------------------------------------------------------
# F) Feedrate resolution
# ---------------------------------------------------------------------------


def test_set_feedrate():
    result = {
        "warnings": ["Operation 0 ('drill'): missing required 'feedrate'"],
        "errors": [],
        "operation_plan": {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "tools": [],
            "operations": [
                {"type": "drill", "tool_number": 1, "parameters": {"x": 0, "y": 0, "z": -10}},
            ],
        },
    }

    issues = collect_interactive_issues(result)
    feed_issues = [i for i in issues if i["code"] == MISSING_FEEDRATE]
    assert len(feed_issues) >= 1

    decision = {
        "action": "SET_FEEDRATE",
        "payload": {"feedrate": 80},
    }

    result = apply_resolution_decision(result, feed_issues[0], decision)
    assert result["operation_plan"]["operations"][0]["feedrate_mmpm"] == 80.0


# ---------------------------------------------------------------------------
# G) Abort
# ---------------------------------------------------------------------------


def test_abort():
    result = _make_result_with_tool_warnings(1, "1")
    issues = collect_interactive_issues(result)
    issue = issues[0]

    decision = {"action": "ABORT", "payload": {}}

    result = apply_resolution_decision(result, issue, decision)
    assert result["aborted"] is True


# ---------------------------------------------------------------------------
# H) Agent gcode discarded — info, not actionable
# ---------------------------------------------------------------------------


def test_agent_gcode_discarded_is_info():
    result = {
        "warnings": [
            "Agent-provided gcode was discarded and regenerated deterministically from operation_plan."
        ],
        "errors": [],
        "operation_plan": {"machine_type": "drill", "units": "mm", "safe_z": 5.0,
                           "tools": [], "operations": []},
    }

    issues = collect_interactive_issues(result)
    discard_issues = [i for i in issues if i["code"] == AGENT_GCODE_DISCARDED]

    assert len(discard_issues) == 1
    assert discard_issues[0]["severity"] == "info"
    assert discard_issues[0]["actionable"] is False


# ---------------------------------------------------------------------------
# I) Ignore once
# ---------------------------------------------------------------------------


def test_ignore_once():
    result = _make_result_with_tool_warnings(1, "1")
    issues = collect_interactive_issues(result)
    issue = issues[0]

    decision = {"action": "IGNORE_ONCE", "payload": {}}

    result = apply_resolution_decision(result, issue, decision)
    assert "resolution_log" in result
    assert result["resolution_log"][0]["action"] == "IGNORE_ONCE"
    assert "aborted" not in result


# ---------------------------------------------------------------------------
# J) Material choices include prompt inference
# ---------------------------------------------------------------------------


def test_material_choices_with_steel_prompt():
    result = _make_result_with_material_warnings()
    issues = collect_interactive_issues(result, prompt="Drill holes in steel")
    mat_issue = [i for i in issues if i["code"] == MISSING_MATERIAL][0]

    choices = build_issue_choices(mat_issue, result, prompt="Drill holes in steel")

    # Should offer mild_steel as inferred candidate
    set_material_choices = [c for c in choices if c["action"] == "SET_MATERIAL"]
    assert len(set_material_choices) >= 1
    labels = " ".join(c["label"] for c in set_material_choices)
    assert "mild_steel" in labels


# ---------------------------------------------------------------------------
# K) Spindle speed resolution
# ---------------------------------------------------------------------------


def test_set_spindle_speed():
    result = {
        "warnings": ["Operation 0: no spindle_speed specified."],
        "errors": [],
        "operation_plan": {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "tools": [],
            "operations": [
                {"type": "drill", "tool_number": 1, "feedrate_mmpm": 80,
                 "parameters": {"x": 0, "y": 0, "z": -10}},
            ],
        },
    }

    issues = collect_interactive_issues(result)
    spindle_issues = [i for i in issues if i["code"] == MISSING_SPINDLE_SPEED]

    if spindle_issues:
        decision = {"action": "SET_SPINDLE_SPEED", "payload": {"spindle_speed": 1200}}
        result = apply_resolution_decision(result, spindle_issues[0], decision)
        assert result["operation_plan"]["operations"][0]["spindle_rpm"] == 1200


# ---------------------------------------------------------------------------
# L) Assumed postprocessor detection and resolution
# ---------------------------------------------------------------------------


def _make_result_with_assumed_defaults() -> dict:
    """Result where units, WCS, and postprocessor were defaulted."""
    return {
        "warnings": [],
        "errors": [],
        "operation_plan": {
            "machine_type": "drill",
            "units": "mm",
            "work_coordinate_system": "G54",
            "safe_z": 5.0,
            "tools": [],
            "operations": [],
            "assumptions": [
                "Assumed units: mm (not specified in plan)",
                "Assumed work coordinate system: G54 (not specified in plan)",
                "Assumed postprocessor: fanuc (not specified in plan or result)",
            ],
        },
    }


def test_assumed_postprocessor_detected():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    pp_issues = [i for i in issues if i["code"] == ASSUMED_POSTPROCESSOR]
    assert len(pp_issues) == 1
    assert pp_issues[0]["actionable"] is True
    assert pp_issues[0]["context"]["current_value"] == "fanuc"


def test_assumed_units_detected():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    unit_issues = [i for i in issues if i["code"] == ASSUMED_UNITS]
    assert len(unit_issues) == 1
    assert unit_issues[0]["actionable"] is True


def test_assumed_wcs_detected():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    wcs_issues = [i for i in issues if i["code"] == ASSUMED_WCS]
    assert len(wcs_issues) == 1
    assert wcs_issues[0]["actionable"] is True


def test_assumed_machine_type_detected():
    result = {
        "warnings": [],
        "errors": [],
        "operation_plan": {
            "units": "mm",
            "safe_z": 5.0,
            "tools": [],
            "operations": [],
            "assumptions": [
                "Machine type not specified in plan",
            ],
        },
    }
    issues = collect_interactive_issues(result)
    mt_issues = [i for i in issues if i["code"] == ASSUMED_MACHINE_TYPE]
    assert len(mt_issues) == 1
    assert mt_issues[0]["actionable"] is True


def test_no_assumed_issues_when_explicitly_set():
    """When all values are explicitly set (no assumptions), no assumed-default issues."""
    result = {
        "warnings": [],
        "errors": [],
        "operation_plan": {
            "machine_type": "drill",
            "units": "mm",
            "work_coordinate_system": "G54",
            "postprocessor": "grbl",
            "safe_z": 5.0,
            "tools": [],
            "operations": [],
            "assumptions": [],
        },
    }
    issues = collect_interactive_issues(result)
    assumed_codes = {ASSUMED_POSTPROCESSOR, ASSUMED_UNITS, ASSUMED_WCS, ASSUMED_MACHINE_TYPE}
    assumed_issues = [i for i in issues if i["code"] in assumed_codes]
    assert len(assumed_issues) == 0


# ---------------------------------------------------------------------------
# M) Assumed default choice builders
# ---------------------------------------------------------------------------


def test_assumed_postprocessor_choices():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    pp_issue = [i for i in issues if i["code"] == ASSUMED_POSTPROCESSOR][0]
    choices = build_issue_choices(pp_issue, result)
    actions = {c["action"] for c in choices}
    assert "SET_POSTPROCESSOR" in actions
    assert "ABORT" in actions
    # Should have fanuc, grbl, linuxcnc + abort
    assert len(choices) == 4


def test_assumed_units_choices():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    unit_issue = [i for i in issues if i["code"] == ASSUMED_UNITS][0]
    choices = build_issue_choices(unit_issue, result)
    actions = {c["action"] for c in choices}
    assert "SET_UNITS" in actions
    assert "ABORT" in actions


def test_assumed_machine_type_choices():
    result = {
        "warnings": [],
        "errors": [],
        "operation_plan": {
            "units": "mm",
            "safe_z": 5.0,
            "tools": [],
            "operations": [],
            "assumptions": ["Machine type not specified in plan"],
        },
    }
    issues = collect_interactive_issues(result)
    mt_issue = [i for i in issues if i["code"] == ASSUMED_MACHINE_TYPE][0]
    choices = build_issue_choices(mt_issue, result)
    actions = {c["action"] for c in choices}
    assert "SET_MACHINE_TYPE" in actions
    assert "ABORT" in actions
    # Should have mill, drill, lathe, laser, grinder, 3d_printer + abort
    assert len(choices) == 7


# ---------------------------------------------------------------------------
# N) Apply assumed default resolutions
# ---------------------------------------------------------------------------


def test_apply_set_postprocessor():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    pp_issue = [i for i in issues if i["code"] == ASSUMED_POSTPROCESSOR][0]

    decision = {"action": "SET_POSTPROCESSOR", "payload": {"postprocessor": "grbl"}}
    result = apply_resolution_decision(result, pp_issue, decision)

    assert result["postprocessor"] == "grbl"
    assert result["operation_plan"]["postprocessor"] == "grbl"
    # Assumption should be removed
    assumptions = result["operation_plan"].get("assumptions", [])
    assert not any("Assumed postprocessor:" in a for a in assumptions)


def test_apply_set_units():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    unit_issue = [i for i in issues if i["code"] == ASSUMED_UNITS][0]

    decision = {"action": "SET_UNITS", "payload": {"units": "inch"}}
    result = apply_resolution_decision(result, unit_issue, decision)

    assert result["operation_plan"]["units"] == "inch"
    assumptions = result["operation_plan"].get("assumptions", [])
    assert not any("Assumed units:" in a for a in assumptions)


def test_apply_set_wcs():
    result = _make_result_with_assumed_defaults()
    issues = collect_interactive_issues(result)
    wcs_issue = [i for i in issues if i["code"] == ASSUMED_WCS][0]

    decision = {"action": "SET_WCS", "payload": {"wcs": "G55"}}
    result = apply_resolution_decision(result, wcs_issue, decision)

    assert result["operation_plan"]["work_coordinate_system"] == "G55"
    assumptions = result["operation_plan"].get("assumptions", [])
    assert not any("Assumed work coordinate system:" in a for a in assumptions)


def test_apply_set_machine_type():
    result = {
        "warnings": [],
        "errors": [],
        "operation_plan": {
            "units": "mm",
            "safe_z": 5.0,
            "tools": [],
            "operations": [],
            "assumptions": ["Machine type not specified in plan"],
        },
    }
    issues = collect_interactive_issues(result)
    mt_issue = [i for i in issues if i["code"] == ASSUMED_MACHINE_TYPE][0]

    decision = {"action": "SET_MACHINE_TYPE", "payload": {"machine_type": "lathe"}}
    result = apply_resolution_decision(result, mt_issue, decision)

    assert result["operation_plan"]["machine_type"] == "lathe"
    assert result["machine_type"] == "lathe"
    assumptions = result["operation_plan"].get("assumptions", [])
    assert not any("Machine type not specified" in a for a in assumptions)
