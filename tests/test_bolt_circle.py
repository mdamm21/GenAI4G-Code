"""Tests for bolt circle (Lochkreis) handling.

Bolt circles MUST be expanded into individual "drill" operations.
The operation type "bolt_circle" must NEVER appear in a final plan.

Covers:
1. Coordinate calculation via calculate_bolt_circle_positions
2. bolt_circle operation type is rejected by validation (unsupported)
3. Pipeline blocks on unsupported operation types (no TODO in G-code)
4. HITL issue codes still work for missing bolt circle params in missing_info
5. Post-resolution stale warnings are cleaned up
6. G-code output contains actual drill moves for each hole
"""

import math
import pytest

from cnc.tools.drill_tools import calculate_bolt_circle_positions
from cnc.tools.validation_tools import validate_operation_plan
from cnc.tools.gcode_pipeline import regenerate_gcode_from_operation_plan
from cnc.tools.issue_resolution import (
    collect_interactive_issues,
    build_issue_choices,
    apply_resolution_decision,
    MISSING_BOLT_CIRCLE_CENTER,
    MISSING_BOLT_CIRCLE_START_ANGLE,
    MISSING_BOLT_CIRCLE_HOLE_TYPE,
    MISSING_Z_REFERENCE,
    MISSING_FEEDRATE,
    MISSING_SPINDLE_SPEED,
    MISSING_MATERIAL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expanded_bolt_circle_plan(
    center_x: float = 0.0,
    center_y: float = 0.0,
    radius: float = 40.0,
    num_holes: int = 6,
    start_angle_deg: float = 0.0,
    depth: float = 18.0,
    feedrate: float | None = 115.0,
    spindle_rpm: int | None = 1287,
) -> dict:
    """Build a plan with bolt circle expanded into individual drill operations."""
    positions = calculate_bolt_circle_positions(
        center_x, center_y, radius, num_holes, start_angle_deg,
    )
    operations = []
    for i, pos in enumerate(positions):
        op: dict = {
            "name": f"Bolt circle hole {i + 1}/{num_holes}",
            "type": "drill",
            "tool_number": 1,
            "parameters": {"x": pos["x"], "y": pos["y"], "z": -depth},
        }
        if feedrate is not None:
            op["feedrate_mmpm"] = feedrate
        if spindle_rpm is not None:
            op["spindle_rpm"] = spindle_rpm
        operations.append(op)

    return {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "material": "mild_steel",
        "tools": [
            {"tool_number": 1, "description": "8.5mm HSS twist drill",
             "diameter_mm": 8.5, "type": "drill"}
        ],
        "operations": operations,
        "assumptions": [],
        "warnings": [],
        "missing_info": [],
    }


def _bolt_circle_type_plan() -> dict:
    """Plan with the FORBIDDEN 'bolt_circle' operation type."""
    return {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [
            {"tool_number": 1, "description": "drill", "diameter_mm": 8.5, "type": "drill"}
        ],
        "operations": [
            {
                "name": "Bolt circle",
                "type": "bolt_circle",
                "tool_number": 1,
                "feedrate_mmpm": 115,
                "spindle_rpm": 1287,
                "parameters": {
                    "center_x": 0, "center_y": 0, "radius": 40,
                    "num_holes": 6, "start_angle_deg": 0,
                    "hole_type": "through", "depth": 18,
                },
            }
        ],
        "assumptions": [],
        "warnings": [],
        "missing_info": [],
    }


def _result_from_plan(plan: dict) -> dict:
    val = validate_operation_plan(plan)
    return {
        "operation_plan": plan,
        "warnings": list(plan.get("warnings", [])),
        "errors": [],
        "validation": val,
    }


# ---------------------------------------------------------------------------
# 1) Coordinate calculation
# ---------------------------------------------------------------------------


class TestBoltCirclePositions:
    def test_six_holes_at_origin_start_0(self):
        """Standard 6-hole bolt circle at X0/Y0, R=40, start=0°."""
        pos = calculate_bolt_circle_positions(0, 0, 40, 6, 0)
        assert len(pos) == 6

        expected = [
            (40.0, 0.0),
            (20.0, 34.641),
            (-20.0, 34.641),
            (-40.0, 0.0),
            (-20.0, -34.641),
            (20.0, -34.641),
        ]
        for actual, (ex, ey) in zip(pos, expected):
            assert abs(actual["x"] - ex) < 0.01, f"x mismatch: {actual['x']} vs {ex}"
            assert abs(actual["y"] - ey) < 0.01, f"y mismatch: {actual['y']} vs {ey}"

    def test_four_holes_with_offset_center(self):
        pos = calculate_bolt_circle_positions(50, 50, 25, 4, 0)
        assert len(pos) == 4
        assert abs(pos[0]["x"] - 75.0) < 0.01
        assert abs(pos[0]["y"] - 50.0) < 0.01
        assert abs(pos[1]["x"] - 50.0) < 0.01
        assert abs(pos[1]["y"] - 75.0) < 0.01

    def test_start_angle_rotates(self):
        pos_0 = calculate_bolt_circle_positions(0, 0, 40, 6, 0)
        pos_30 = calculate_bolt_circle_positions(0, 0, 40, 6, 30)
        # First hole should be at different positions
        assert abs(pos_0[0]["x"] - pos_30[0]["x"]) > 1.0

    def test_returns_correct_count(self):
        for n in (2, 3, 8, 12):
            pos = calculate_bolt_circle_positions(0, 0, 50, n, 0)
            assert len(pos) == n


# ---------------------------------------------------------------------------
# 2) bolt_circle op type is rejected by validation
# ---------------------------------------------------------------------------


class TestBoltCircleTypeRejected:
    def test_bolt_circle_type_is_validation_error(self):
        plan = _bolt_circle_type_plan()
        result = validate_operation_plan(plan)
        assert result["ok"] is False
        assert any("unsupported operation type" in e.lower() for e in result["errors"])
        assert any("bolt_circle" in e for e in result["errors"])

    def test_other_unsupported_types_also_rejected(self):
        for bad_type in ("hole_pattern", "drilling_pattern", "magic_op"):
            plan = _bolt_circle_type_plan()
            plan["operations"][0]["type"] = bad_type
            result = validate_operation_plan(plan)
            assert result["ok"] is False
            assert any(bad_type in e for e in result["errors"])


# ---------------------------------------------------------------------------
# 3) Expanded drill plan passes validation
# ---------------------------------------------------------------------------


class TestExpandedPlanValid:
    def test_six_drill_ops_pass_validation(self):
        plan = _expanded_bolt_circle_plan()
        result = validate_operation_plan(plan)
        assert result["ok"] is True
        assert result["errors"] == []

    def test_all_ops_are_type_drill(self):
        plan = _expanded_bolt_circle_plan()
        for op in plan["operations"]:
            assert op["type"] == "drill"

    def test_exactly_six_operations(self):
        plan = _expanded_bolt_circle_plan()
        assert len(plan["operations"]) == 6


# ---------------------------------------------------------------------------
# 4) Pipeline blocks on unsupported op type, G-code is empty
# ---------------------------------------------------------------------------


class TestPipelineBlocksUnsupported:
    def test_bolt_circle_type_blocks_pipeline(self):
        plan = _bolt_circle_type_plan()
        result = regenerate_gcode_from_operation_plan({"operation_plan": plan})
        assert result["ok"] is False
        assert result["gcode"] == ""
        assert any("bolt_circle" in e.lower() for e in result.get("errors", []))

    def test_no_todo_in_gcode(self):
        """G-code must NEVER contain TODO: OPERATION TYPE."""
        plan = _expanded_bolt_circle_plan()
        result = regenerate_gcode_from_operation_plan({"operation_plan": plan})
        assert result["ok"] is True
        assert "TODO" not in result["gcode"]
        assert "NOT YET IMPLEMENTED" not in result["gcode"]

    def test_gcode_empty_on_unsupported(self):
        for bad_type in ("bolt_circle", "hole_pattern", "custom_weird"):
            plan = _expanded_bolt_circle_plan()
            plan["operations"][0]["type"] = bad_type
            result = regenerate_gcode_from_operation_plan({"operation_plan": plan})
            assert result["ok"] is False
            assert result["gcode"] == ""


# ---------------------------------------------------------------------------
# 5) G-code contains 6 actual drill moves
# ---------------------------------------------------------------------------


class TestGcodeContainsDrillMoves:
    def test_six_xy_rapid_moves(self):
        plan = _expanded_bolt_circle_plan()
        result = regenerate_gcode_from_operation_plan({"operation_plan": plan})
        assert result["ok"] is True
        gcode = result["gcode"]
        # Count G00 XY moves (rapid to hole position)
        import re
        xy_rapids = re.findall(r"G00\s+X[\d.-]+\s+Y[\d.-]+", gcode)
        assert len(xy_rapids) >= 6

    def test_six_plunge_moves(self):
        plan = _expanded_bolt_circle_plan()
        result = regenerate_gcode_from_operation_plan({"operation_plan": plan})
        gcode = result["gcode"]
        # Count G01 Z-18 plunges
        import re
        plunges = re.findall(r"G01\s+Z-18\.000", gcode)
        assert len(plunges) == 6


# ---------------------------------------------------------------------------
# 6) HITL still works for missing bolt circle params via missing_info
# ---------------------------------------------------------------------------


class TestBoltCircleHITL:
    def test_missing_center_in_missing_info_yields_issue(self):
        plan = _expanded_bolt_circle_plan()
        plan["operations"] = []  # empty because params are missing
        plan["missing_info"] = ["Bolt circle center (center_x, center_y) not specified."]
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_CENTER in codes

    def test_missing_start_angle_in_missing_info_yields_issue(self):
        plan = _expanded_bolt_circle_plan()
        plan["operations"] = []
        plan["missing_info"] = ["Bolt circle start angle (start_angle_deg) not specified."]
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_START_ANGLE in codes

    def test_missing_hole_type_in_missing_info_yields_issue(self):
        plan = _expanded_bolt_circle_plan()
        plan["operations"] = []
        plan["missing_info"] = ["Hole type (hole_type: through | pilot) not specified."]
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_HOLE_TYPE in codes


# ---------------------------------------------------------------------------
# 7) Post-resolution stale warnings cleaned up
# ---------------------------------------------------------------------------


class TestPostResolutionCleanup:
    def test_feedrate_warning_gone_after_resolution(self):
        plan = _expanded_bolt_circle_plan(feedrate=None)
        plan["warnings"] = ["Feedrate not specified by user."]
        plan["missing_info"] = ["feedrate"]
        result = _result_from_plan(plan)

        issues = collect_interactive_issues(result)
        fr_issue = next(i for i in issues if i["code"] == MISSING_FEEDRATE)
        result = apply_resolution_decision(result, fr_issue, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })

        # missing_info and warnings cleaned
        assert not any("feedrate" in str(m).lower()
                       for m in result["operation_plan"]["missing_info"])
        assert not any("feedrate" in str(w).lower()
                       for w in result["operation_plan"]["warnings"])

    def test_spindle_warning_gone_after_resolution(self):
        plan = _expanded_bolt_circle_plan(spindle_rpm=None)
        plan["warnings"] = ["Spindle speed not specified by user."]
        plan["missing_info"] = ["spindle_speed"]
        result = _result_from_plan(plan)

        issues = collect_interactive_issues(result)
        sp_issue = next(i for i in issues if i["code"] == MISSING_SPINDLE_SPEED)
        result = apply_resolution_decision(result, sp_issue, {
            "action": "SET_SPINDLE_SPEED", "payload": {"spindle_speed": 1300},
        })

        assert not any("spindle" in str(m).lower()
                       for m in result["operation_plan"]["missing_info"])
        assert not any("spindle" in str(w).lower()
                       for w in result["operation_plan"]["warnings"])

    def test_material_warning_gone_after_set(self):
        plan = _expanded_bolt_circle_plan()
        plan.pop("material", None)
        result = _result_from_plan(plan)

        issues = collect_interactive_issues(result)
        mat_issue = next((i for i in issues if i["code"] == MISSING_MATERIAL), None)
        if mat_issue:
            result = apply_resolution_decision(result, mat_issue, {
                "action": "SET_MATERIAL", "payload": {"material_id": "mild_steel"},
            })
            # Material warning should be gone from operation_plan warnings
            assert not any("material" in str(w).lower()
                           for w in result["operation_plan"].get("warnings", []))

    def test_resolved_decisions_in_log(self):
        plan = _expanded_bolt_circle_plan(feedrate=None, spindle_rpm=None)
        plan["warnings"] = [
            "Feedrate not specified by user.",
            "Spindle speed not specified by user.",
        ]
        plan["missing_info"] = ["feedrate", "spindle_speed"]
        result = _result_from_plan(plan)
        result.setdefault("resolution_log", [])

        issues = collect_interactive_issues(result)
        fr_issue = next(i for i in issues if i["code"] == MISSING_FEEDRATE)
        result = apply_resolution_decision(result, fr_issue, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })

        log = result["resolution_log"]
        assert any(e["action"] == "SET_FEEDRATE" for e in log)

    def test_validation_ok_not_reported_for_untranslated_ops(self):
        """Validation must NOT return ok=True if an operation can't be translated."""
        plan = _bolt_circle_type_plan()
        result = validate_operation_plan(plan)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# 8) Bolt circle pattern detection triggers HITL for unconfirmed assumptions
# ---------------------------------------------------------------------------


class TestBoltCirclePatternDetection:
    def test_detects_unconfirmed_center(self):
        """When ops look like a bolt circle, missing center confirmation
        should generate a MISSING_BOLT_CIRCLE_CENTER issue."""
        plan = _expanded_bolt_circle_plan()
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_CENTER in codes

    def test_detects_unconfirmed_start_angle(self):
        plan = _expanded_bolt_circle_plan()
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_START_ANGLE in codes

    def test_detects_unconfirmed_hole_type(self):
        plan = _expanded_bolt_circle_plan()
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_HOLE_TYPE in codes

    def test_no_detection_when_center_confirmed(self):
        """Once center is confirmed in assumptions, no issue should appear."""
        plan = _expanded_bolt_circle_plan()
        plan["assumptions"].append("Confirmed bolt circle center: X0.0 / Y0.0")
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_CENTER not in codes

    def test_no_detection_when_angle_confirmed(self):
        plan = _expanded_bolt_circle_plan()
        plan["assumptions"].append("Confirmed bolt circle start angle: 0.0°")
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_START_ANGLE not in codes

    def test_no_detection_when_hole_type_confirmed(self):
        plan = _expanded_bolt_circle_plan()
        plan["assumptions"].append("Confirmed hole type: through")
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_HOLE_TYPE not in codes

    def test_agent_assumption_does_not_suppress_detection(self):
        """An agent-generated assumption (without 'Confirmed' prefix) must
        NOT suppress the HITL confirmation."""
        plan = _expanded_bolt_circle_plan()
        plan["assumptions"].append(
            "Bolt circle center at work coordinate origin (X0, Y0) per G54"
        )
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_CENTER in codes

    def test_z_reference_detected(self):
        """Unconfirmed Z0 reference should trigger MISSING_Z_REFERENCE."""
        plan = _expanded_bolt_circle_plan()
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_Z_REFERENCE in codes

    def test_z_reference_suppressed_when_confirmed(self):
        plan = _expanded_bolt_circle_plan()
        plan["assumptions"].append("Confirmed Z reference: Z0 at top of workpiece")
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_Z_REFERENCE not in codes

    def test_no_detection_for_non_bolt_circle_ops(self):
        """Random drill operations without bolt circle names should not trigger."""
        plan = _expanded_bolt_circle_plan()
        for op in plan["operations"]:
            op["name"] = "Simple drill hole"  # no bolt circle indicators
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        codes = {i["code"] for i in issues}
        assert MISSING_BOLT_CIRCLE_CENTER not in codes
        assert MISSING_BOLT_CIRCLE_START_ANGLE not in codes
        assert MISSING_BOLT_CIRCLE_HOLE_TYPE not in codes

    def test_confirm_center_adds_assumption(self):
        """CONFIRM_BOLT_CIRCLE_CENTER should log confirmation as assumption."""
        plan = _expanded_bolt_circle_plan()
        result = _result_from_plan(plan)
        result.setdefault("resolution_log", [])
        issues = collect_interactive_issues(result)
        center_issue = next(i for i in issues if i["code"] == MISSING_BOLT_CIRCLE_CENTER)
        result = apply_resolution_decision(result, center_issue, {
            "action": "CONFIRM_BOLT_CIRCLE_CENTER",
            "payload": {"center_x": 0.0, "center_y": 0.0},
        })
        assert any("Confirmed bolt circle center" in a
                    for a in result["operation_plan"]["assumptions"])

    def test_set_center_recalculates_positions(self):
        """SET_BOLT_CIRCLE_CENTER with new values should recalculate positions."""
        plan = _expanded_bolt_circle_plan()
        result = _result_from_plan(plan)
        result.setdefault("resolution_log", [])
        issues = collect_interactive_issues(result)
        center_issue = next(i for i in issues if i["code"] == MISSING_BOLT_CIRCLE_CENTER)

        # Original first hole is at X=40, Y=0 (center=0,0, radius=40)
        assert abs(plan["operations"][0]["parameters"]["x"] - 40.0) < 0.01
        assert abs(plan["operations"][0]["parameters"]["y"] - 0.0) < 0.01

        # Move center to X=10, Y=10
        result = apply_resolution_decision(result, center_issue, {
            "action": "SET_BOLT_CIRCLE_CENTER",
            "payload": {"center_x": 10.0, "center_y": 10.0},
        })
        # First hole should now be at X=50, Y=10 (center=10,10, radius=40, angle=0)
        assert abs(result["operation_plan"]["operations"][0]["parameters"]["x"] - 50.0) < 0.01
        assert abs(result["operation_plan"]["operations"][0]["parameters"]["y"] - 10.0) < 0.01


# ---------------------------------------------------------------------------
# 9) Hole type selection atomically updates tool diameter
# ---------------------------------------------------------------------------


class TestHolePurposeAtomicUpdate:
    """SET_BOLT_CIRCLE_HOLE_TYPE must atomically update tool diameter,
    description, and assumption — never leave a mismatch."""

    def _plan_with_m8_tool(self, diameter: float = 8.5) -> dict:
        plan = _expanded_bolt_circle_plan()
        plan["tools"] = [
            {"tool_number": 1,
             "description": f"{diameter}mm HSS twist drill (M8 clearance)",
             "diameter_mm": diameter, "type": "drill"}
        ]
        return plan

    def test_tap_drill_sets_6_8mm(self):
        plan = self._plan_with_m8_tool(8.5)
        result = _result_from_plan(plan)
        result.setdefault("resolution_log", [])
        issues = collect_interactive_issues(result)
        ht_issue = next(i for i in issues if i["code"] == MISSING_BOLT_CIRCLE_HOLE_TYPE)
        result = apply_resolution_decision(result, ht_issue, {
            "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
            "payload": {"hole_type": "tap_drill", "bolt_size": "M8",
                        "diameter_mm": 6.8},
        })
        tool = result["operation_plan"]["tools"][0]
        assert tool["diameter_mm"] == 6.8
        assert "tap drill" in tool["description"].lower()
        assert "clearance" not in tool["description"].lower()

    def test_clearance_sets_9_0mm(self):
        plan = self._plan_with_m8_tool(6.8)
        plan["tools"][0]["description"] = "6.8mm HSS twist drill (M8 tap drill)"
        result = _result_from_plan(plan)
        result.setdefault("resolution_log", [])
        issues = collect_interactive_issues(result)
        ht_issue = next(i for i in issues if i["code"] == MISSING_BOLT_CIRCLE_HOLE_TYPE)
        result = apply_resolution_decision(result, ht_issue, {
            "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
            "payload": {"hole_type": "clearance", "bolt_size": "M8",
                        "diameter_mm": 9.0},
        })
        tool = result["operation_plan"]["tools"][0]
        assert tool["diameter_mm"] == 9.0
        assert "clearance" in tool["description"].lower()
        assert "tap drill" not in tool["description"].lower()

    def test_tap_drill_no_8_5_anywhere_in_plan(self):
        """After selecting tap_drill for M8, 8.5 and 'clearance' must not
        appear anywhere in the plan — tools, assumptions, warnings."""
        plan = self._plan_with_m8_tool(8.5)
        result = _result_from_plan(plan)
        result.setdefault("resolution_log", [])
        issues = collect_interactive_issues(result)
        ht_issue = next(i for i in issues if i["code"] == MISSING_BOLT_CIRCLE_HOLE_TYPE)
        result = apply_resolution_decision(result, ht_issue, {
            "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
            "payload": {"hole_type": "tap_drill", "bolt_size": "M8",
                        "diameter_mm": 6.8},
        })
        op = result["operation_plan"]

        # Check tools
        for t in op["tools"]:
            assert t["diameter_mm"] != 8.5
            assert "clearance" not in t.get("description", "").lower()

        # Check assumptions
        for a in op.get("assumptions", []):
            assert "clearance" not in a.lower() or "tap_drill" in a.lower()

    def test_auto_detects_bolt_size_from_tool(self):
        """If no bolt_size in payload, detect from tool description."""
        plan = self._plan_with_m8_tool(8.5)
        result = _result_from_plan(plan)
        result.setdefault("resolution_log", [])
        issues = collect_interactive_issues(result)
        ht_issue = next(i for i in issues if i["code"] == MISSING_BOLT_CIRCLE_HOLE_TYPE)
        # No bolt_size or diameter_mm in payload — auto-detect
        result = apply_resolution_decision(result, ht_issue, {
            "action": "SET_BOLT_CIRCLE_HOLE_TYPE",
            "payload": {"hole_type": "tap_drill"},
        })
        tool = result["operation_plan"]["tools"][0]
        assert tool["diameter_mm"] == 6.8
        assert "M8" in tool["description"]

    def test_choices_show_correct_diameters(self):
        """Choices must show correct diameters for detected bolt size."""
        plan = self._plan_with_m8_tool(8.5)
        result = _result_from_plan(plan)
        issues = collect_interactive_issues(result)
        ht_issue = next(i for i in issues if i["code"] == MISSING_BOLT_CIRCLE_HOLE_TYPE)
        choices = build_issue_choices(ht_issue, result)
        # First choice should be clearance with D9.0mm
        assert "9.0" in choices[0]["label"]
        assert choices[0]["payload"]["diameter_mm"] == 9.0
        # Second choice should be tap-drill with D6.8mm
        assert "6.8" in choices[1]["label"]
        assert choices[1]["payload"]["diameter_mm"] == 6.8


# ---------------------------------------------------------------------------
# 10) Stale top-level warnings cleaned after resolution
# ---------------------------------------------------------------------------


class TestStaleWarningCleanup:
    def test_feedrate_warning_removed_from_result_level(self):
        """After SET_FEEDRATE, feedrate warnings must be removed from
        result['warnings'] before regeneration, not just from op['warnings']."""
        from cnc.cli_interaction import _regenerate_after_resolution

        plan = _expanded_bolt_circle_plan(feedrate=None)
        plan["warnings"] = ["Feedrate not specified by user."]
        plan["missing_info"] = ["feedrate"]
        result = _result_from_plan(plan)
        result["warnings"] = [
            "Feedrate not specified by user.",
            "Coolant required for drilling steel.",
        ]
        result.setdefault("resolution_log", [])

        # Resolve feedrate
        issues = collect_interactive_issues(result)
        fr_issue = next(i for i in issues if i["code"] == MISSING_FEEDRATE)
        result = apply_resolution_decision(result, fr_issue, {
            "action": "SET_FEEDRATE", "payload": {"feedrate": 115},
        })

        # Regenerate
        result = _regenerate_after_resolution(result)

        # Feedrate warning should be gone, coolant should remain
        remaining = result.get("warnings", [])
        assert not any("feedrate" in str(w).lower() for w in remaining)
        assert any("coolant" in str(w).lower() for w in remaining)
