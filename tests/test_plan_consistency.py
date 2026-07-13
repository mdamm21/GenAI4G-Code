"""Tests for plan consistency after resolution.

Covers four bugs:
1. Duplicate fields: feedrate/feedrate_mmpm, spindle_rpm/spindle_speed, diameter/diameter_mm
2. missing_info not cleaned after resolution
3. warnings not cleaned after resolution
4. Validation rejects contradictory state (value set + still in missing_info)
"""

import pytest
from cnc.tools.issue_resolution import (
    collect_interactive_issues,
    build_issue_choices,
    apply_resolution_decision,
    MISSING_FEEDRATE,
    MISSING_SPINDLE_SPEED,
    MISSING_SAFE_Z,
    MISSING_MATERIAL,
)
from cnc.tools.validation_tools import validate_operation_plan
from cnc.tools.operation_plan_tools import normalize_operation_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drill_plan_missing_feedrate_spindle() -> dict:
    """Drill plan where feedrate and spindle are missing (as subagent would emit)."""
    return {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "material": "mild_steel",
        "tools": [
            {"tool_number": 1, "description": "8.5mm drill", "diameter_mm": 8.5, "type": "drill"}
        ],
        "operations": [
            {
                "name": "Drill hole",
                "type": "drill",
                "tool_number": 1,
                "parameters": {"x": 0, "y": 0, "z": -10},
            }
        ],
        "assumptions": [],
        "warnings": [
            "Feedrate not specified by user.",
            "Spindle speed not specified by user.",
        ],
        "missing_info": ["feedrate", "spindle_speed"],
    }


def _result_from_plan(plan: dict) -> dict:
    val = validate_operation_plan(plan)
    return {
        "operation_plan": plan,
        "warnings": list(plan.get("warnings", [])),
        "errors": [],
        "validation": val,
    }


def _resolve_first_issue(result: dict, code: str, decision: dict) -> dict:
    """Find the first issue with the given code and apply a decision."""
    issues = collect_interactive_issues(result)
    issue = next(i for i in issues if i["code"] == code)
    return apply_resolution_decision(result, issue, decision)


# ---------------------------------------------------------------------------
# 1) No duplicate fields after resolution
# ---------------------------------------------------------------------------


class TestNoDuplicateFields:
    def test_feedrate_only_canonical_field(self):
        """After SET_FEEDRATE, operation has feedrate_mmpm but NOT feedrate."""
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_FEEDRATE, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })
        op = result["operation_plan"]["operations"][0]
        assert op["feedrate_mmpm"] == 115
        assert "feedrate" not in op

    def test_spindle_only_canonical_field(self):
        """After SET_SPINDLE_SPEED, operation has spindle_rpm but NOT spindle_speed."""
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_SPINDLE_SPEED, {
            "action": "SET_SPINDLE_SPEED", "payload": {"spindle_speed": 1300},
        })
        op = result["operation_plan"]["operations"][0]
        assert op["spindle_rpm"] == 1300
        assert "spindle_speed" not in op

    def test_feedrate_replaces_existing_deprecated(self):
        """If operation already has deprecated 'feedrate', it gets removed."""
        plan = _drill_plan_missing_feedrate_spindle()
        plan["operations"][0]["feedrate"] = 50  # deprecated field pre-existing
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_FEEDRATE, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })
        op = result["operation_plan"]["operations"][0]
        assert op["feedrate_mmpm"] == 115
        assert "feedrate" not in op

    def test_diameter_only_canonical_field(self):
        """After SET_CUSTOM_DIAMETER, tool has diameter_mm but NOT diameter."""
        from cnc.tools.issue_resolution import TOOL_DIAMETER_MISMATCH
        plan = _drill_plan_missing_feedrate_spindle()
        # Give it feedrate/spindle so we don't hit those issues
        plan["operations"][0]["feedrate_mmpm"] = 100
        plan["operations"][0]["spindle_rpm"] = 1200
        plan["missing_info"] = []
        plan["warnings"] = []

        # Simulate a tool with both old and new diameter fields
        plan["tools"][0]["diameter"] = 8.5  # deprecated
        result = _result_from_plan(plan)

        # Directly test the _apply_diameter function
        from cnc.tools.issue_resolution import _apply_diameter
        issue = {"affected_operations": [0], "context": {"tool_id": "1"}}
        log_entry = {}
        _apply_diameter(result["operation_plan"], issue, 10.0, log_entry)

        tool = result["operation_plan"]["tools"][0]
        assert tool["diameter_mm"] == 10.0
        assert "diameter" not in tool


# ---------------------------------------------------------------------------
# 2) missing_info cleaned after resolution
# ---------------------------------------------------------------------------


class TestMissingInfoCleanup:
    def test_feedrate_removed_from_missing_info(self):
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_FEEDRATE, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })
        mi = result["operation_plan"]["missing_info"]
        assert not any("feedrate" in str(m).lower() for m in mi)

    def test_spindle_removed_from_missing_info(self):
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_SPINDLE_SPEED, {
            "action": "SET_SPINDLE_SPEED", "payload": {"spindle_speed": 1300},
        })
        mi = result["operation_plan"]["missing_info"]
        assert not any("spindle" in str(m).lower() for m in mi)

    def test_unrelated_missing_info_preserved(self):
        """Resolving feedrate must NOT remove spindle from missing_info."""
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_FEEDRATE, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })
        mi = result["operation_plan"]["missing_info"]
        # spindle_speed should still be there
        assert any("spindle" in str(m).lower() for m in mi)

    def test_safe_z_removed_from_missing_info(self):
        plan = _drill_plan_missing_feedrate_spindle()
        plan["safe_z"] = None
        plan["missing_info"].append("safe_z")
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_SAFE_Z, {
            "action": "SET_SAFE_Z", "payload": {"safe_z": 5.0},
        })
        mi = result["operation_plan"]["missing_info"]
        assert not any("safe_z" in str(m).lower() for m in mi)

    def test_ignore_once_does_not_clean_missing_info(self):
        """IGNORE_ONCE must leave missing_info intact."""
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        feedrate_issue = next(i for i in issues if i["code"] == MISSING_FEEDRATE)
        result = apply_resolution_decision(result, feedrate_issue, {
            "action": "IGNORE_ONCE", "payload": {},
        })
        mi = result["operation_plan"]["missing_info"]
        assert any("feedrate" in str(m).lower() for m in mi)


# ---------------------------------------------------------------------------
# 3) warnings cleaned after resolution
# ---------------------------------------------------------------------------


class TestWarningsCleanup:
    def test_feedrate_warning_removed(self):
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_FEEDRATE, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })
        ws = result["operation_plan"]["warnings"]
        assert not any("feedrate" in str(w).lower() for w in ws)

    def test_spindle_warning_removed(self):
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_SPINDLE_SPEED, {
            "action": "SET_SPINDLE_SPEED", "payload": {"spindle_speed": 1300},
        })
        ws = result["operation_plan"]["warnings"]
        assert not any("spindle" in str(w).lower() for w in ws)

    def test_unrelated_warning_preserved(self):
        """Resolving feedrate must NOT remove spindle warning."""
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)
        result = _resolve_first_issue(result, MISSING_FEEDRATE, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })
        ws = result["operation_plan"]["warnings"]
        assert any("spindle" in str(w).lower() for w in ws)


# ---------------------------------------------------------------------------
# 4) Validation rejects contradictory state
# ---------------------------------------------------------------------------


class TestContradictoryStateValidation:
    def test_feedrate_set_but_in_missing_info_is_error(self):
        plan = _drill_plan_missing_feedrate_spindle()
        plan["operations"][0]["feedrate_mmpm"] = 115  # value set...
        # but missing_info still says "feedrate"  → contradiction
        result = validate_operation_plan(plan)
        assert result["ok"] is False
        assert any("contradictory" in e.lower() for e in result["errors"])

    def test_spindle_set_but_in_missing_info_is_error(self):
        plan = _drill_plan_missing_feedrate_spindle()
        plan["operations"][0]["spindle_rpm"] = 1300
        # missing_info has "spindle_speed"
        result = validate_operation_plan(plan)
        assert result["ok"] is False
        assert any("contradictory" in e.lower() and "spindle" in e.lower()
                    for e in result["errors"])

    def test_safe_z_set_but_in_missing_info_is_error(self):
        plan = _drill_plan_missing_feedrate_spindle()
        plan["missing_info"].append("safe_z")
        # safe_z is already 5.0 on the plan → contradiction
        result = validate_operation_plan(plan)
        assert result["ok"] is False
        assert any("contradictory" in e.lower() and "safe_z" in e.lower()
                    for e in result["errors"])

    def test_no_contradiction_when_consistent(self):
        """Plan with value set and missing_info empty must pass."""
        plan = _drill_plan_missing_feedrate_spindle()
        plan["operations"][0]["feedrate_mmpm"] = 115
        plan["operations"][0]["spindle_rpm"] = 1300
        plan["missing_info"] = []  # cleaned
        plan["warnings"] = []
        result = validate_operation_plan(plan)
        contradiction_errors = [e for e in result["errors"] if "contradictory" in e.lower()]
        assert contradiction_errors == []

    def test_no_contradiction_when_truly_missing(self):
        """Plan with missing value and missing_info listing it must NOT flag contradiction."""
        plan = _drill_plan_missing_feedrate_spindle()
        # feedrate is truly missing — no contradiction
        result = validate_operation_plan(plan)
        contradiction_errors = [e for e in result["errors"] if "contradictory" in e.lower()]
        assert contradiction_errors == []


# ---------------------------------------------------------------------------
# 5) Normalization removes deprecated aliases
# ---------------------------------------------------------------------------


class TestNormalizationCanonicalFields:
    def test_operation_feedrate_becomes_feedrate_mmpm_only(self):
        raw = {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "tools": [{"id": "T1", "name": "drill", "diameter": 5.0, "feedrate": 100}],
            "operations": [
                {"type": "drill", "tool_id": "T1", "feedrate": 100,
                 "parameters": {"x": 0, "y": 0, "z": -5}}
            ],
        }
        normalized = normalize_operation_plan(raw)
        op = normalized["operations"][0]
        assert op["feedrate_mmpm"] == 100
        assert "feedrate" not in op

    def test_operation_spindle_becomes_spindle_rpm_only(self):
        raw = {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "tools": [{"id": "T1", "name": "drill", "diameter": 5.0, "spindle_speed": 1200}],
            "operations": [
                {"type": "drill", "tool_id": "T1", "spindle_speed": 1200,
                 "parameters": {"x": 0, "y": 0, "z": -5}}
            ],
        }
        normalized = normalize_operation_plan(raw)
        op = normalized["operations"][0]
        assert op["spindle_rpm"] == 1200
        assert "spindle_speed" not in op

    def test_tool_diameter_becomes_diameter_mm_only(self):
        raw = {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "tools": [{"id": "T1", "name": "drill", "diameter": 8.5}],
            "operations": [],
        }
        normalized = normalize_operation_plan(raw)
        tool = normalized["tools"][0]
        assert tool["diameter_mm"] == 8.5
        assert "diameter" not in tool

    def test_canonical_fields_not_removed(self):
        """If input already uses canonical names, they must be preserved."""
        raw = {
            "machine_type": "drill",
            "units": "mm",
            "safe_z": 5.0,
            "tools": [{"tool_number": 1, "description": "drill", "diameter_mm": 8.5}],
            "operations": [
                {"type": "drill", "tool_number": 1, "feedrate_mmpm": 100, "spindle_rpm": 1200,
                 "parameters": {"x": 0, "y": 0, "z": -5}}
            ],
        }
        normalized = normalize_operation_plan(raw)
        op = normalized["operations"][0]
        assert op["feedrate_mmpm"] == 100
        assert op["spindle_rpm"] == 1200
        tool = normalized["tools"][0]
        assert tool["diameter_mm"] == 8.5


# ---------------------------------------------------------------------------
# 6) Full round-trip: resolve → validate → no contradictions
# ---------------------------------------------------------------------------


class TestFullRoundTrip:
    def test_resolve_feedrate_then_validate_passes(self):
        """After resolving feedrate, re-validation must not find contradictions."""
        plan = _drill_plan_missing_feedrate_spindle()
        result = _result_from_plan(plan)

        # Resolve feedrate
        result = _resolve_first_issue(result, MISSING_FEEDRATE, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })
        # Resolve spindle
        result = _resolve_first_issue(result, MISSING_SPINDLE_SPEED, {
            "action": "SET_SPINDLE_SPEED", "payload": {"spindle_speed": 1300},
        })

        # Re-validate
        val = validate_operation_plan(result["operation_plan"])
        contradiction_errors = [e for e in val["errors"] if "contradictory" in e.lower()]
        assert contradiction_errors == []

        # Check plan is clean
        op = result["operation_plan"]["operations"][0]
        assert op["feedrate_mmpm"] == 115
        assert "feedrate" not in op
        assert op["spindle_rpm"] == 1300
        assert "spindle_speed" not in op
        assert result["operation_plan"]["missing_info"] == []
        assert result["operation_plan"]["warnings"] == []
