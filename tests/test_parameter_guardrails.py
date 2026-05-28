"""Tests for cnc/tools/parameter_guardrails.py — no LLM, no API key required."""

from __future__ import annotations

import pytest

from cnc.tools.parameter_guardrails import evaluate_parameter_guardrails


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_pocket_plan(material: str | None = None) -> dict:
    plan = {
        "machine_type": "mill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5.0,
        "tools": [{"id": "T1", "diameter": 5.0}],
        "operations": [
            {
                "type": "pocket",
                "feedrate": 150.0,
                "spindle_speed": 3000.0,
                "parameters": {
                    "origin_x": 0.0,
                    "origin_y": 0.0,
                    "width": 20.0,
                    "height": 10.0,
                    "target_z": -3.0,
                    "step_down": 1.0,
                    "step_over": 2.0,
                    "tool_diameter": 5.0,
                },
            }
        ],
        "assumptions": [],
        "warnings": [],
    }
    if material:
        plan["material"] = material
    return plan


def _valid_drill_plan(material: str | None = None) -> dict:
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5.0,
        "tools": [{"id": "T1", "diameter": 5.0}],
        "operations": [
            {
                "type": "drill",
                "feedrate": 100.0,
                "spindle_speed": 1200.0,
                "parameters": {"x": 0.0, "y": 0.0, "z": -5.0},
            }
        ],
        "assumptions": [],
        "warnings": [],
    }
    if material:
        plan["material"] = material
    return plan


# ---------------------------------------------------------------------------
# A) Valid milling pocket plan with aluminum_6061
# ---------------------------------------------------------------------------


def test_valid_pocket_with_aluminum_ok():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="aluminum_6061"
    )
    assert result["ok"] is True


def test_valid_pocket_with_aluminum_no_errors():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="aluminum_6061"
    )
    assert result["errors"] == []


def test_valid_pocket_with_aluminum_material_resolved():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="aluminum_6061"
    )
    assert result["material"] is not None
    assert result["material"]["id"] == "aluminum_6061"


def test_valid_pocket_with_aluminum_warnings_allowed():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="aluminum_6061"
    )
    # Warnings are allowed — ok should still be True
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# B) Plan without material → warning
# ---------------------------------------------------------------------------


def test_plan_without_material_ok_true():
    """Missing material is a warning, not an error — ok stays True."""
    result = evaluate_parameter_guardrails(_valid_pocket_plan())
    assert result["ok"] is True


def test_plan_without_material_has_warning():
    result = evaluate_parameter_guardrails(_valid_pocket_plan())
    warnings_text = " ".join(result.get("warnings", []))
    assert "Material was not specified" in warnings_text


def test_plan_without_material_finding_code():
    result = evaluate_parameter_guardrails(_valid_pocket_plan())
    codes = [f["code"] for f in result.get("findings", [])]
    assert "NO_MATERIAL" in codes


# ---------------------------------------------------------------------------
# C) Stainless steel → caution warning
# ---------------------------------------------------------------------------


def test_stainless_steel_warning():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="stainless_steel_generic"
    )
    warnings_text = " ".join(result.get("warnings", []))
    assert "stainless" in warnings_text.lower() or "conservative" in warnings_text.lower()


def test_stainless_steel_finding_code():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="stainless_steel_generic"
    )
    codes = [f["code"] for f in result.get("findings", [])]
    assert "STAINLESS_STEEL_CAUTION" in codes


def test_stainless_steel_ok_true_no_errors():
    """Stainless steel warning must not become an error."""
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="stainless_steel_generic"
    )
    assert result["ok"] is True
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# D) Pocket with step_over > tool_diameter
# ---------------------------------------------------------------------------


def test_step_over_exceeds_diameter_warning():
    plan = _valid_pocket_plan()
    plan["operations"][0]["parameters"]["step_over"] = 10.0  # > tool_diameter=5
    result = evaluate_parameter_guardrails(plan, material="aluminum_6061")
    warnings_text = " ".join(result.get("warnings", []))
    assert "step_over" in warnings_text.lower() or "uncut" in warnings_text.lower()


def test_step_over_exceeds_diameter_finding():
    plan = _valid_pocket_plan()
    plan["operations"][0]["parameters"]["step_over"] = 10.0
    result = evaluate_parameter_guardrails(plan)
    codes = [f["code"] for f in result.get("findings", [])]
    assert "STEP_OVER_EXCEEDS_DIAMETER" in codes


def test_step_over_exceeds_diameter_still_ok():
    """step_over > tool_diameter is a warning — ok must still be True if no other errors."""
    plan = _valid_pocket_plan(material="aluminum_6061")
    plan["operations"][0]["parameters"]["step_over"] = 10.0
    result = evaluate_parameter_guardrails(plan)
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# E) Missing feedrate → error
# ---------------------------------------------------------------------------


def test_missing_feedrate_is_error():
    plan = _valid_pocket_plan()
    del plan["operations"][0]["feedrate"]
    result = evaluate_parameter_guardrails(plan, material="aluminum_6061")
    assert result["ok"] is False
    errors_text = " ".join(result.get("errors", []))
    assert "feedrate" in errors_text.lower()


def test_missing_feedrate_finding():
    plan = _valid_pocket_plan()
    del plan["operations"][0]["feedrate"]
    result = evaluate_parameter_guardrails(plan)
    codes = [f["code"] for f in result.get("findings", [])]
    assert "MISSING_FEEDRATE" in codes


# ---------------------------------------------------------------------------
# F) Missing safe_z → error
# ---------------------------------------------------------------------------


def test_missing_safe_z_is_error():
    plan = _valid_pocket_plan()
    del plan["safe_z"]
    result = evaluate_parameter_guardrails(plan, material="aluminum_6061")
    assert result["ok"] is False
    errors_text = " ".join(result.get("errors", []))
    assert "safe_z" in errors_text.lower()


def test_missing_safe_z_finding():
    plan = _valid_pocket_plan()
    del plan["safe_z"]
    result = evaluate_parameter_guardrails(plan)
    codes = [f["code"] for f in result.get("findings", [])]
    assert "MISSING_SAFE_Z" in codes


# ---------------------------------------------------------------------------
# G) Wood material → fire/dust warning
# ---------------------------------------------------------------------------


def test_wood_material_warning():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="plywood"
    )
    warnings_text = " ".join(result.get("warnings", []))
    assert "dust" in warnings_text.lower() or "fire" in warnings_text.lower()


# ---------------------------------------------------------------------------
# H) Plastic material → heat/chip warning
# ---------------------------------------------------------------------------


def test_plastic_material_warning():
    result = evaluate_parameter_guardrails(
        _valid_pocket_plan(), material="acrylic"
    )
    warnings_text = " ".join(result.get("warnings", []))
    assert "chip" in warnings_text.lower() or "plastic" in warnings_text.lower()


# ---------------------------------------------------------------------------
# I) Result structure
# ---------------------------------------------------------------------------


def test_result_has_required_keys():
    result = evaluate_parameter_guardrails(_valid_pocket_plan())
    for key in ("ok", "errors", "warnings", "info", "material", "findings"):
        assert key in result, f"Missing key {key!r}"


def test_non_dict_plan_returns_error():
    result = evaluate_parameter_guardrails("not a dict")
    assert result["ok"] is False
    assert result["errors"]


def test_unknown_material_warning():
    result = evaluate_parameter_guardrails(_valid_pocket_plan(), material="unobtainium")
    warnings_text = " ".join(result.get("warnings", []))
    assert "unknown material" in warnings_text.lower() or "unobtainium" in warnings_text.lower()


# ---------------------------------------------------------------------------
# J) Spindle missing → warning not error
# ---------------------------------------------------------------------------


def test_missing_spindle_is_warning_not_error():
    plan = _valid_pocket_plan(material="aluminum_6061")
    del plan["operations"][0]["spindle_speed"]
    result = evaluate_parameter_guardrails(plan)
    assert result["ok"] is True  # spindle missing is a warning
    assert "MISSING_SPINDLE" in [f["code"] for f in result.get("findings", [])]


# ---------------------------------------------------------------------------
# K) step_down > depth → warning
# ---------------------------------------------------------------------------


def test_step_down_exceeds_depth_warning():
    plan = _valid_pocket_plan()
    plan["operations"][0]["parameters"]["step_down"] = 10.0  # > depth=3
    result = evaluate_parameter_guardrails(plan, material="aluminum_6061")
    codes = [f["code"] for f in result.get("findings", [])]
    assert "STEP_DOWN_EXCEEDS_DEPTH" in codes
    assert result["ok"] is True  # still a warning, not error
