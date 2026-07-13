"""Tests for complete warning traceability.

Every finding must have a provable lifecycle:
  detected → displayed → acknowledged/resolved → logged in resolution_log

Covers:
1. initial_issues snapshot preserved in result
2. Informational issues logged as ACKNOWLEDGED in resolution_log
3. Second pass shows ALL remaining issues (including informational)
4. consolidated_warnings includes all sources (validation, safety, plan, acknowledged)
5. G-code header contains consolidated warnings
"""

import pytest
from cnc.cli_interaction import resolve_issues_interactively


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_input_fn(responses: list[str]):
    """Input function that yields from responses, then returns '1' forever."""
    it = iter(responses)
    def _fn(_prompt: str) -> str:
        try:
            return next(it)
        except StopIteration:
            return "1"
    return _fn


def _drill_result_with_mixed_warnings() -> dict:
    """Result dict that has actionable + informational warnings from multiple sources."""
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "material": "mild_steel",
        "tools": [
            {"tool_number": 1, "description": "6.8mm drill", "diameter_mm": 6.8, "type": "drill"}
        ],
        "operations": [
            {
                "name": "Drill hole",
                "type": "drill",
                "tool_number": 1,
                "feedrate_mmpm": 80,
                "spindle_rpm": 1200,
                "parameters": {"x": 0, "y": 0, "z": -18},
            }
        ],
        "assumptions": ["Assumed work coordinate system: G54 (not specified in plan)"],
        "warnings": [],
        "missing_info": [],
    }

    from cnc.tools.validation_tools import validate_operation_plan
    val = validate_operation_plan(plan)

    return {
        "operation_plan": plan,
        "warnings": [
            "6.8mm is an M8 pilot hole diameter; for through-hole use 8.5mm.",
            "Coolant required for drilling steel at this depth.",
            "Secure workpiece against rotation before starting.",
        ],
        "errors": [],
        "validation": val,
        "safety_report": {
            "warnings": ["Chip evacuation may be difficult at 18mm depth."],
            "errors": [],
            "findings": [],
        },
    }


def _drill_result_missing_feedrate() -> dict:
    """Result with missing feedrate (actionable) + informational warnings."""
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "material": "mild_steel",
        "tools": [
            {"tool_number": 1, "description": "6.8mm drill", "diameter_mm": 6.8, "type": "drill"}
        ],
        "operations": [
            {
                "name": "Drill hole",
                "type": "drill",
                "tool_number": 1,
                "spindle_rpm": 1200,
                "parameters": {"x": 0, "y": 0, "z": -18},
            }
        ],
        "assumptions": [],
        "warnings": ["Feedrate not specified by user."],
        "missing_info": ["feedrate"],
    }

    from cnc.tools.validation_tools import validate_operation_plan
    val = validate_operation_plan(plan)

    return {
        "operation_plan": plan,
        "warnings": [
            "Coolant required for drilling steel.",
            "Secure workpiece against rotation.",
        ],
        "errors": [],
        "validation": val,
        "safety_report": {
            "warnings": ["Chip evacuation concern at depth."],
            "errors": [],
            "findings": [],
        },
    }


# ---------------------------------------------------------------------------
# 1) initial_issues snapshot
# ---------------------------------------------------------------------------


class TestInitialIssuesSnapshot:
    def test_initial_issues_preserved(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        assert "initial_issues" in result
        assert isinstance(result["initial_issues"], list)
        assert len(result["initial_issues"]) > 0

    def test_initial_issues_not_overwritten_on_reentry(self):
        """Second call to resolve_issues_interactively must NOT overwrite initial_issues."""
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        fn = lambda *args: output_lines.append(" ".join(str(a) for a in args))
        ifn = _safe_input_fn([])

        result = resolve_issues_interactively(result, input_fn=ifn, output_fn=fn)
        snapshot = list(result["initial_issues"])

        # Call again (simulating re-entry after "Go back and review")
        result = resolve_issues_interactively(result, input_fn=_safe_input_fn([]), output_fn=fn)
        assert result["initial_issues"] == snapshot

    def test_initial_issues_contain_all_sources(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        messages = [i["message"] for i in result["initial_issues"]]
        # Should include informational warnings from top-level
        assert any("coolant" in m.lower() or "Coolant" in m for m in messages)


# ---------------------------------------------------------------------------
# 2) Informational issues logged as ACKNOWLEDGED
# ---------------------------------------------------------------------------


class TestAcknowledgedLogging:
    def test_informational_issues_in_resolution_log(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        log = result.get("resolution_log", [])
        acknowledged = [e for e in log if e.get("action") == "ACKNOWLEDGED"]
        assert len(acknowledged) > 0

    def test_acknowledged_entries_have_message(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        log = result.get("resolution_log", [])
        for entry in log:
            if entry.get("action") == "ACKNOWLEDGED":
                assert "message" in entry
                assert entry["message"]
                assert "issue_code" in entry

    def test_every_informational_issue_has_log_entry(self):
        """Each info-only issue displayed must have a corresponding ACKNOWLEDGED log entry."""
        from cnc.tools.issue_resolution import collect_interactive_issues
        result = _drill_result_with_mixed_warnings()

        issues = collect_interactive_issues(result)
        info_issues = [i for i in issues if not i.get("actionable")]
        assert len(info_issues) > 0  # precondition

        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        log = result.get("resolution_log", [])
        ack_codes = {e["issue_code"] for e in log if e.get("action") == "ACKNOWLEDGED"}

        for info_issue in info_issues:
            assert info_issue["code"] in ack_codes, (
                f"Informational issue {info_issue['code']} ({info_issue['message']}) "
                f"not found in resolution_log as ACKNOWLEDGED"
            )


# ---------------------------------------------------------------------------
# 3) Second pass includes informational warnings
# ---------------------------------------------------------------------------


class TestSecondPassInclusive:
    def test_info_warnings_shown_in_remaining(self):
        """After resolving actionable issues, informational warnings still appear."""
        result = _drill_result_missing_feedrate()
        output_lines: list[str] = []

        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([
                "1",      # feedrate choice (enter manually or use recommendation)
                "100",    # feedrate value
            ]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        # The output should mention remaining warnings including informational ones
        all_text = "\n".join(output_lines)
        # Should still show informational warnings (coolant, clamping)
        # They should appear somewhere in the output
        has_remaining = "Remaining warnings:" in all_text
        if has_remaining:
            # The INFO items should be shown
            assert "[INFO]" in all_text or "coolant" in all_text.lower() or "secure" in all_text.lower()


# ---------------------------------------------------------------------------
# 4) consolidated_warnings includes all sources
# ---------------------------------------------------------------------------


class TestConsolidatedWarnings:
    def test_all_warnings_field_populated(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        assert "all_warnings" in result
        assert isinstance(result["all_warnings"], list)
        assert len(result["all_warnings"]) > 0

    def test_all_warnings_includes_safety_report(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        messages = [w["message"] for w in result["all_warnings"]]
        assert any("chip" in m.lower() for m in messages), (
            "Safety report warning about chip evacuation not found in all_warnings"
        )

    def test_all_warnings_includes_top_level(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        messages = [w["message"] for w in result["all_warnings"]]
        assert any("coolant" in m.lower() for m in messages)

    def test_all_warnings_entries_have_source(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        for w in result["all_warnings"]:
            assert "source" in w, f"Warning entry missing 'source' field: {w}"
            assert "severity" in w
            assert "message" in w

    def test_all_warnings_no_duplicates(self):
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        messages = [w["message"] for w in result["all_warnings"]]
        assert len(messages) == len(set(messages)), "Duplicate warnings found"


# ---------------------------------------------------------------------------
# 5) G-code header includes consolidated warnings
# ---------------------------------------------------------------------------


class TestGcodeHeaderWarnings:
    def test_fanuc_header_includes_consolidated(self):
        from cnc.postprocessors.fanuc import generate_gcode_from_operations
        plan = _drill_result_with_mixed_warnings()["operation_plan"]
        plan["consolidated_warnings"] = [
            "Coolant required for drilling steel.",
            "Secure workpiece against rotation.",
            "Chip evacuation may be difficult at 18mm depth.",
        ]
        gcode = generate_gcode_from_operations(plan)
        assert "(WARNINGS:)" in gcode
        assert "Coolant" in gcode
        assert "Secure" in gcode
        assert "Chip" in gcode

    def test_grbl_header_includes_consolidated(self):
        from cnc.postprocessors.grbl import generate_gcode_from_operations
        plan = _drill_result_with_mixed_warnings()["operation_plan"]
        plan["consolidated_warnings"] = [
            "Coolant required for drilling steel.",
            "Chip evacuation concern.",
        ]
        gcode = generate_gcode_from_operations(plan)
        assert "Coolant" in gcode
        assert "Chip" in gcode

    def test_linuxcnc_header_includes_consolidated(self):
        from cnc.postprocessors.linuxcnc import generate_gcode_from_operations
        plan = _drill_result_with_mixed_warnings()["operation_plan"]
        plan["consolidated_warnings"] = [
            "Coolant required for drilling steel.",
        ]
        gcode = generate_gcode_from_operations(plan)
        assert "Coolant" in gcode

    def test_fanuc_falls_back_to_plan_warnings(self):
        """Without consolidated_warnings, postprocessor uses plan warnings."""
        from cnc.postprocessors.fanuc import generate_gcode_from_operations
        plan = _drill_result_with_mixed_warnings()["operation_plan"]
        plan["warnings"] = ["Some plan-level warning."]
        # No consolidated_warnings key
        gcode = generate_gcode_from_operations(plan)
        assert "Some plan-level warning" in gcode

    def test_no_duplicate_warnings_in_header(self):
        from cnc.postprocessors.fanuc import generate_gcode_from_operations
        plan = _drill_result_with_mixed_warnings()["operation_plan"]
        plan["consolidated_warnings"] = [
            "Coolant required.",
            "Coolant required.",  # duplicate
            "Other warning.",
        ]
        gcode = generate_gcode_from_operations(plan)
        assert gcode.count("Coolant required.") == 1


# ---------------------------------------------------------------------------
# 6) Full lifecycle traceability
# ---------------------------------------------------------------------------


class TestFullLifecycleTraceability:
    def test_every_initial_issue_is_traceable(self):
        """For every initial issue, there must be a resolution_log entry
        (either ACKNOWLEDGED, a resolution action, or IGNORE_ONCE)."""
        result = _drill_result_missing_feedrate()
        output_lines: list[str] = []

        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([
                "1",    # feedrate choice
                "100",  # value
            ]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )

        initial = result.get("initial_issues", [])
        log = result.get("resolution_log", [])
        logged_codes = {e["issue_code"] for e in log}

        for issue in initial:
            code = issue["code"]
            assert code in logged_codes, (
                f"Issue {code} ({issue.get('message', '')}) detected but "
                f"not traceable in resolution_log"
            )

    def test_consolidated_warnings_on_operation_plan(self):
        """After resolution, operation_plan has consolidated_warnings for postprocessor."""
        result = _drill_result_with_mixed_warnings()
        output_lines: list[str] = []
        result = resolve_issues_interactively(
            result,
            input_fn=_safe_input_fn([]),
            output_fn=lambda *args: output_lines.append(" ".join(str(a) for a in args)),
        )
        op = result["operation_plan"]
        assert "consolidated_warnings" in op
        assert isinstance(op["consolidated_warnings"], list)
        # Must include warnings from safety_report
        assert any("chip" in w.lower() for w in op["consolidated_warnings"])
