"""Tests for cnc/postprocessors/fanuc.py — conservative Fanuc G-code generation."""

import pytest
from cnc.postprocessors.fanuc import generate_gcode_from_operations
from cnc.tools.operation_plan_tools import normalize_operation_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gen(plan: dict) -> str:
    return generate_gcode_from_operations(plan)


# ---------------------------------------------------------------------------
# A) Full drill plan produces correct G-code structure
# ---------------------------------------------------------------------------


def test_drill_gcode_starts_with_percent(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert gcode.startswith("%")


def test_drill_gcode_ends_with_percent(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert gcode.strip().endswith("%")


def test_drill_gcode_has_g21_mm(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "G21" in gcode


def test_drill_gcode_has_g90_absolute(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "G90" in gcode


def test_drill_gcode_has_wcs(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "G54" in gcode


def test_drill_gcode_has_safe_z_retract(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "Z5.000" in gcode or "Z5.0" in gcode


def test_drill_gcode_has_spindle_start(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "S1200" in gcode
    assert "M03" in gcode


def test_drill_gcode_has_rapid_to_hole(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "X0.000" in gcode
    assert "Y0.000" in gcode


def test_drill_gcode_has_g1_plunge(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "G01" in gcode or "G1 " in gcode


def test_drill_gcode_has_negative_z(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "Z-5.000" in gcode or "Z-5" in gcode


def test_drill_gcode_has_feedrate(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "F100" in gcode


def test_drill_gcode_has_spindle_stop(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "M05" in gcode


def test_drill_gcode_has_m30(normalized_drill_plan):
    gcode = _gen(normalized_drill_plan)
    assert "M30" in gcode


def test_drill_gcode_no_g1_before_spindle(normalized_drill_plan):
    """Spindle (M03) must appear before any G01 plunge."""
    gcode = _gen(normalized_drill_plan)
    lines = gcode.splitlines()
    m03_idx = next((i for i, l in enumerate(lines) if "M03" in l), None)
    g01_idx = next((i for i, l in enumerate(lines) if "G01" in l), None)
    if m03_idx is not None and g01_idx is not None:
        assert m03_idx < g01_idx, "M03 must appear before G01 plunge"


# ---------------------------------------------------------------------------
# B) Missing safe_z — no risky movement, comment instead
# ---------------------------------------------------------------------------


def test_missing_safe_z_no_crash():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        # safe_z omitted
        "tools": [],
        "operations": [
            {
                "type": "drill",
                "name": "test drill",
                "parameters": {"x": 0, "y": 0, "z": -5},
                "feedrate": 100,
                "spindle_speed": 1200,
            }
        ],
    }
    gcode = _gen(plan)  # must not raise
    assert isinstance(gcode, str)


def test_missing_safe_z_produces_warning_comment():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        # safe_z omitted
        "tools": [],
        "operations": [
            {
                "type": "drill",
                "name": "no safe z",
                "parameters": {"x": 0, "y": 0, "z": -5},
                "feedrate": 100,
                "spindle_speed": 1200,
            }
        ],
    }
    gcode = _gen(plan)
    assert "NOT DEFINED" in gcode or "NOT SPECIFIED" in gcode or "WARNING" in gcode


# ---------------------------------------------------------------------------
# C) Missing drill parameters — operation is skipped, no crash
# ---------------------------------------------------------------------------


def test_missing_x_skips_operation_without_crash():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5,
        "tools": [],
        "operations": [
            {
                "type": "drill",
                "name": "incomplete drill",
                "parameters": {"y": 0, "z": -5},  # x missing
                "feedrate": 100,
                "spindle_speed": 1200,
            }
        ],
    }
    gcode = _gen(plan)
    assert isinstance(gcode, str)
    # No G01 plunge since coordinates are incomplete
    assert "G01" not in gcode or "SKIPPED" in gcode


def test_missing_feedrate_skips_plunge():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5,
        "tools": [],
        "operations": [
            {
                "type": "drill",
                "name": "no feedrate",
                "parameters": {"x": 0, "y": 0, "z": -5},
                # feedrate omitted
                "spindle_speed": 1200,
            }
        ],
    }
    gcode = _gen(plan)
    assert isinstance(gcode, str)
    # Should NOT have a bare G01 Z without F
    assert "G01 Z" not in gcode or "SKIPPED" in gcode


def test_no_operations_produces_skeleton():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5,
        "tools": [],
        "operations": [],
    }
    gcode = _gen(plan)
    assert "NO OPERATIONS" in gcode
    assert "M30" in gcode


# ---------------------------------------------------------------------------
# D) Unit handling
# ---------------------------------------------------------------------------


def test_inch_units_produces_g20():
    plan = {
        "machine_type": "drill",
        "units": "inch",
        "work_coordinate_system": "G54",
        "safe_z": 0.5,
        "tools": [],
        "operations": [],
    }
    gcode = _gen(plan)
    assert "G20" in gcode
    assert "G21" not in gcode


def test_mm_units_produces_g21():
    plan = {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5,
        "tools": [],
        "operations": [],
    }
    gcode = _gen(plan)
    assert "G21" in gcode


# ---------------------------------------------------------------------------
# E) Milling regression — face_mill still works
# ---------------------------------------------------------------------------


def test_milling_face_mill_still_works(valid_mill_plan):
    gcode = _gen(valid_mill_plan)
    assert "G21" in gcode
    assert "G90" in gcode
    assert "M30" in gcode
    assert "G01" in gcode or "G1 " in gcode


# ---------------------------------------------------------------------------
# F) Facing operation — rectangular passes
# ---------------------------------------------------------------------------

_FACING_PLAN = {
    "machine_type": "mill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"id": "T1", "name": "5mm end mill", "diameter": 5.0}],
    "operations": [
        {
            "type": "facing",
            "description": "Face 20x10 area",
            "tool_id": "T1",
            "parameters": {
                "origin_x": 0.0,
                "origin_y": 0.0,
                "width": 20.0,
                "height": 10.0,
                "target_z": -1.0,
                "step_over": 4.0,
                "tool_diameter": 5.0,
            },
            "feedrate": 150.0,
            "spindle_speed": 3000.0,
        }
    ],
    "assumptions": [],
    "warnings": [],
}


def test_facing_no_crash():
    gcode = _gen(_FACING_PLAN)
    assert isinstance(gcode, str)


def test_facing_has_m30():
    gcode = _gen(_FACING_PLAN)
    assert "M30" in gcode


def test_facing_has_spindle_start():
    gcode = _gen(_FACING_PLAN)
    assert "M03" in gcode


def test_facing_has_g1_x_moves():
    gcode = _gen(_FACING_PLAN)
    assert "G01 X" in gcode


def test_facing_has_negative_z():
    gcode = _gen(_FACING_PLAN)
    assert "Z-1.000" in gcode


def test_facing_multiple_y_passes():
    # height=10, step_over=4 → should generate at least 3 passes
    gcode = _gen(_FACING_PLAN)
    assert gcode.count("G01 X") >= 3


def test_facing_no_crash_missing_feedrate():
    plan = {**_FACING_PLAN}
    op = {**_FACING_PLAN["operations"][0]}
    op.pop("feedrate", None)
    plan = {**plan, "operations": [op]}
    gcode = _gen(plan)  # must not raise
    assert isinstance(gcode, str)
    assert "SKIPPED" in gcode or "NO FEEDRATE" in gcode


# ---------------------------------------------------------------------------
# F) Slot operation
# ---------------------------------------------------------------------------

_SLOT_PLAN = {
    "machine_type": "mill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"tool_number": 1, "name": "end mill 5mm", "diameter_mm": 5.0}],
    "operations": [
        {
            "type": "slot",
            "name": "slot_x",
            "tool_number": 1,
            "parameters": {
                "start_x": 0.0,
                "start_y": 0.0,
                "length": 20.0,
                "target_z": -3.0,
                "direction": "x",
                "step_down": 1.0,
                "tool_diameter": 5.0,
            },
            "feedrate": 150.0,
            "spindle_speed": 3000.0,
        }
    ],
    "assumptions": [],
    "warnings": [],
}


def test_slot_no_crash():
    gcode = _gen(_SLOT_PLAN)
    assert isinstance(gcode, str)


def test_slot_has_m30():
    gcode = _gen(_SLOT_PLAN)
    assert "M30" in gcode


def test_slot_has_spindle_start():
    gcode = _gen(_SLOT_PLAN)
    assert "M03" in gcode


def test_slot_three_passes_depth3_step1():
    """depth=3, step_down=1 -> three Z plunges at Z-1, Z-2, Z-3."""
    gcode = _gen(_SLOT_PLAN)
    assert "Z-1.000" in gcode
    assert "Z-2.000" in gcode
    assert "Z-3.000" in gcode


def test_slot_three_plunge_comments():
    gcode = _gen(_SLOT_PLAN)
    assert gcode.count("PLUNGE TO DEPTH") == 3


def test_slot_has_x_cut_move():
    gcode = _gen(_SLOT_PLAN)
    assert "G01 X20.000" in gcode


def test_slot_no_crash_missing_feedrate():
    plan = {**_SLOT_PLAN}
    op = {**_SLOT_PLAN["operations"][0]}
    op.pop("feedrate", None)
    plan = {**plan, "operations": [op]}
    gcode = _gen(plan)
    assert isinstance(gcode, str)
    assert "SKIPPED" in gcode or "NO FEEDRATE" in gcode


# ---------------------------------------------------------------------------
# G) Pocket operation
# ---------------------------------------------------------------------------

_POCKET_PLAN = {
    "machine_type": "mill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5.0,
    "tools": [{"tool_number": 1, "name": "end mill 5mm", "diameter_mm": 5.0}],
    "operations": [
        {
            "type": "pocket",
            "name": "pocket_rect",
            "tool_number": 1,
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
            "feedrate": 150.0,
            "spindle_speed": 3000.0,
        }
    ],
    "assumptions": [],
    "warnings": [],
}


def test_pocket_no_crash():
    gcode = _gen(_POCKET_PLAN)
    assert isinstance(gcode, str)


def test_pocket_has_m30():
    gcode = _gen(_POCKET_PLAN)
    assert "M30" in gcode


def test_pocket_has_spindle_start():
    gcode = _gen(_POCKET_PLAN)
    assert "M03" in gcode


def test_pocket_three_z_passes_depth3_step1():
    """depth=3, step_down=1 -> three Z passes at Z-1, Z-2, Z-3."""
    gcode = _gen(_POCKET_PLAN)
    assert "Z-1.000" in gcode
    assert "Z-2.000" in gcode
    assert "Z-3.000" in gcode


def test_pocket_raster_rows_present():
    """Raster rows should be present."""
    gcode = _gen(_POCKET_PLAN)
    assert "CUT ROW" in gcode


def test_pocket_multiple_rows():
    """height=10, step_over=2 -> at least 5 rows per Z pass."""
    gcode = _gen(_POCKET_PLAN)
    assert gcode.count("CUT ROW") >= 5


def test_pocket_no_crash_missing_feedrate():
    plan = {**_POCKET_PLAN}
    op = {**_POCKET_PLAN["operations"][0]}
    op.pop("feedrate", None)
    plan = {**plan, "operations": [op]}
    gcode = _gen(plan)
    assert isinstance(gcode, str)
    assert "SKIPPED" in gcode or "NO FEEDRATE" in gcode
