"""Tests for tool-ID resolution integration across cnc/* modules."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# A) machine_profiles — default_tool_ids
# ---------------------------------------------------------------------------


def test_drill_profile_has_default_tool_ids():
    from cnc.tools.machine_profiles import get_machine_profile
    profile = get_machine_profile("generic_drill_mm")
    assert "default_tool_ids" in profile
    assert isinstance(profile["default_tool_ids"], list)
    assert len(profile["default_tool_ids"]) > 0


def test_drill_profile_default_tools_are_drills():
    from cnc.tools.machine_profiles import get_machine_profile
    profile = get_machine_profile("generic_drill_mm")
    for tid in profile["default_tool_ids"]:
        assert "drill" in tid


def test_mill_profile_has_default_tool_ids():
    from cnc.tools.machine_profiles import get_machine_profile
    profile = get_machine_profile("generic_mill_mm")
    assert "default_tool_ids" in profile
    assert len(profile["default_tool_ids"]) > 0


def test_mill_profile_includes_endmill():
    from cnc.tools.machine_profiles import get_machine_profile
    profile = get_machine_profile("generic_mill_mm")
    assert any("endmill" in tid for tid in profile["default_tool_ids"])


def test_all_profiles_have_default_tool_ids():
    from cnc.tools.machine_profiles import list_machine_profiles
    for profile in list_machine_profiles():
        assert "default_tool_ids" in profile, (
            f"Profile '{profile['name']}' missing default_tool_ids"
        )


# ---------------------------------------------------------------------------
# B) drill_tools — tool_id parameter
# ---------------------------------------------------------------------------


def test_build_drill_plan_default_tool_id():
    from cnc.tools.drill_tools import build_drill_operation_plan
    plan = build_drill_operation_plan(
        x=0, y=0, depth=5, tool_diameter=5.0, safe_z=5.0, feedrate=100
    )
    assert plan["tools"][0]["id"] == "T1"
    assert plan["operations"][0]["tool_id"] == "T1"


def test_build_drill_plan_custom_tool_id():
    from cnc.tools.drill_tools import build_drill_operation_plan
    plan = build_drill_operation_plan(
        x=0, y=0, depth=5, tool_diameter=5.0, safe_z=5.0, feedrate=100,
        tool_id="drill_5mm",
    )
    assert plan["tools"][0]["id"] == "drill_5mm"
    assert plan["operations"][0]["tool_id"] == "drill_5mm"


def test_build_drill_pattern_plan_custom_tool_id():
    from cnc.tools.drill_tools import build_drill_pattern_operation_plan
    holes = [{"x": 0, "y": 0, "depth": 5}, {"x": 10, "y": 0, "depth": 5}]
    plan = build_drill_pattern_operation_plan(
        holes=holes, tool_diameter=5.0, safe_z=5.0, feedrate=100,
        tool_id="drill_3mm",
    )
    assert plan["tools"][0]["id"] == "drill_3mm"
    for op in plan["operations"]:
        assert op["tool_id"] == "drill_3mm"


# ---------------------------------------------------------------------------
# C) milling_tools — tool_id parameter
# ---------------------------------------------------------------------------


def test_build_facing_plan_default_tool_id():
    from cnc.tools.milling_tools import build_milling_facing_operation_plan
    plan = build_milling_facing_operation_plan(
        origin_x=0, origin_y=0, width=50, height=50,
        depth=1, step_over=4, tool_diameter=5.0,
        safe_z=5.0, feedrate=500,
    )
    assert plan["tools"][0]["id"] == "T1"
    assert plan["operations"][0]["tool_id"] == "T1"


def test_build_facing_plan_custom_tool_id():
    from cnc.tools.milling_tools import build_milling_facing_operation_plan
    plan = build_milling_facing_operation_plan(
        origin_x=0, origin_y=0, width=50, height=50,
        depth=1, step_over=4, tool_diameter=5.0,
        safe_z=5.0, feedrate=500,
        tool_id="endmill_5mm_flat",
    )
    assert plan["tools"][0]["id"] == "endmill_5mm_flat"
    assert plan["operations"][0]["tool_id"] == "endmill_5mm_flat"


def test_build_slot_plan_custom_tool_id():
    from cnc.tools.milling_tools import build_milling_slot_operation_plan
    plan = build_milling_slot_operation_plan(
        start_x=0, start_y=0, length=30, depth=2,
        tool_diameter=5.0, safe_z=5.0, feedrate=300,
        step_down=1.0,
        tool_id="endmill_5mm_flat",
    )
    assert plan["tools"][0]["id"] == "endmill_5mm_flat"
    assert plan["operations"][0]["tool_id"] == "endmill_5mm_flat"


def test_build_pocket_plan_custom_tool_id():
    from cnc.tools.milling_tools import build_milling_pocket_operation_plan
    plan = build_milling_pocket_operation_plan(
        origin_x=0, origin_y=0, width=20, height=20,
        depth=3, tool_diameter=5.0,
        step_down=1.0, step_over=3.0,
        safe_z=5.0, feedrate=400,
        tool_id="endmill_3mm_flat",
    )
    assert plan["tools"][0]["id"] == "endmill_3mm_flat"
    assert plan["operations"][0]["tool_id"] == "endmill_3mm_flat"


# ---------------------------------------------------------------------------
# D) validation_tools — tool library integration
# ---------------------------------------------------------------------------


def test_validate_plan_unknown_tool_id_is_warning():
    from cnc.tools.validation_tools import validate_operation_plan
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [{"id": "T1", "diameter": 5.0}],
        "operations": [
            {
                "type": "drill",
                "tool_id": "T1",
                "feedrate": 100,
                "parameters": {"x": 0, "y": 0, "z": -5},
            }
        ],
        "material": "aluminum",
    }
    result = validate_operation_plan(plan)
    # Unknown tool_id → warning, not error
    assert result["ok"] is True
    assert any("T1" in w for w in result["warnings"])


def test_validate_plan_known_tool_correct_op_no_error():
    from cnc.tools.validation_tools import validate_operation_plan
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [{"id": "drill_5mm", "diameter": 5.0}],
        "operations": [
            {
                "type": "drill",
                "tool_id": "drill_5mm",
                "feedrate": 100,
                "parameters": {"x": 0, "y": 0, "z": -5},
            }
        ],
        "material": "aluminum",
    }
    result = validate_operation_plan(plan)
    assert result["ok"] is True
    # No errors about tool incompatibility
    assert not any("drill_5mm" in e for e in result["errors"])


def test_validate_plan_known_tool_wrong_op_is_error():
    from cnc.tools.validation_tools import validate_operation_plan
    # drill_5mm does not support "facing"
    plan = {
        "machine_type": "mill",
        "units": "mm",
        "safe_z": 5.0,
        "tools": [{"id": "drill_5mm", "diameter": 5.0}],
        "operations": [
            {
                "type": "facing",
                "tool_id": "drill_5mm",
                "feedrate": 500,
                "parameters": {
                    "origin_x": 0, "origin_y": 0,
                    "width": 50, "height": 50,
                    "target_z": -1, "step_over": 4,
                    "tool_diameter": 5.0,
                },
            }
        ],
        "material": "aluminum",
    }
    result = validate_operation_plan(plan)
    # Known tool used for unsupported op → error
    assert result["ok"] is False
    assert any("drill_5mm" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# E) job_io — tool resolution integration
# ---------------------------------------------------------------------------


def test_job_spec_validate_with_known_tool_id():
    from cnc.tools.job_io import validate_job_spec
    from cnc.tools.drill_tools import build_drill_operation_plan

    plan = build_drill_operation_plan(
        x=10, y=10, depth=5, tool_diameter=5.0,
        safe_z=5.0, feedrate=100, tool_id="drill_5mm",
    )
    job = {
        "schema_version": "0.1",
        "machine_type": "drill",
        "postprocessor": "fanuc",
        "tool_ids": ["drill_5mm"],
        "operation_plan": plan,
    }
    result = validate_job_spec(job)
    # known + compatible tool should not add errors
    assert result["ok"] is True


def test_job_spec_validate_unknown_tool_id_is_warning():
    from cnc.tools.job_io import validate_job_spec
    from cnc.tools.drill_tools import build_drill_operation_plan

    plan = build_drill_operation_plan(
        x=10, y=10, depth=5, tool_diameter=5.0,
        safe_z=5.0, feedrate=100,
    )
    job = {
        "schema_version": "0.1",
        "machine_type": "drill",
        "postprocessor": "fanuc",
        "tool_ids": ["T1"],
        "operation_plan": plan,
    }
    result = validate_job_spec(job)
    assert result["ok"] is True  # unknown tool → warning, not error
    assert any("T1" in w or "tool" in w.lower() for w in result["warnings"])
