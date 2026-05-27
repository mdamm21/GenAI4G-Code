"""Tests for postprocessor dialects v0 — GRBL, LinuxCNC, Marlin, unsupported."""

import pytest

from cnc.postprocessors import grbl as grbl_pp
from cnc.postprocessors import linuxcnc as linuxcnc_pp
from cnc.tools.postprocess_tools import postprocess_operations


# ---------------------------------------------------------------------------
# Shared plan builders
# ---------------------------------------------------------------------------

def _drill_plan(postprocessor: str = "fanuc") -> dict:
    return {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5.0,
        "tools": [{"tool_number": 1, "description": "5mm drill", "diameter": 5}],
        "operations": [
            {
                "type": "drill",
                "name": "drill hole",
                "tool_number": 1,
                "feedrate": 100,
                "spindle_speed": 1200,
                "parameters": {"x": 10, "y": 20, "z": -5},
            }
        ],
        "assumptions": [],
        "warnings": [],
    }


def _slot_plan() -> dict:
    return {
        "machine_type": "mill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5.0,
        "tools": [{"tool_number": 1, "description": "6mm end mill", "diameter": 6}],
        "operations": [
            {
                "type": "slot",
                "name": "slot op",
                "tool_number": 1,
                "feedrate": 120,
                "spindle_speed": 3000,
                "parameters": {
                    "start_x": 0,
                    "start_y": 0,
                    "length": 50,
                    "target_z": -4,
                    "direction": "x",
                    "step_down": 2,
                },
            }
        ],
        "assumptions": [],
        "warnings": [],
    }


def _pocket_plan() -> dict:
    return {
        "machine_type": "mill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5.0,
        "tools": [{"tool_number": 1, "description": "6mm end mill", "diameter": 6}],
        "operations": [
            {
                "type": "pocket",
                "name": "pocket op",
                "tool_number": 1,
                "feedrate": 150,
                "spindle_speed": 3000,
                "parameters": {
                    "origin_x": 0,
                    "origin_y": 0,
                    "width": 20,
                    "height": 10,
                    "target_z": -3,
                    "step_down": 1,
                    "step_over": 3,
                },
            }
        ],
        "assumptions": [],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# A) GRBL Drill
# ---------------------------------------------------------------------------

class TestGrblDrill:
    def test_no_crash(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        assert isinstance(gcode, str)

    def test_contains_g21(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        assert "G21" in gcode

    def test_contains_g90(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        assert "G90" in gcode

    def test_contains_g54(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        assert "G54" in gcode

    def test_contains_drill_plunge(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        # Z-5 or Z-5.000
        assert "Z-5" in gcode

    def test_contains_m2(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        assert "M2" in gcode

    def test_no_percent_delimiter(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        assert "%" not in gcode

    def test_contains_feedrate(self):
        gcode = grbl_pp.generate_gcode_from_operations(_drill_plan())
        assert "F100" in gcode or "F100.000" in gcode


# ---------------------------------------------------------------------------
# B) LinuxCNC Drill
# ---------------------------------------------------------------------------

class TestLinuxcncDrill:
    def test_no_crash(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_drill_plan())
        assert isinstance(gcode, str)

    def test_contains_linuxcnc_header(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_drill_plan())
        assert "LinuxCNC-style" in gcode

    def test_contains_g21(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_drill_plan())
        assert "G21" in gcode

    def test_contains_g90(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_drill_plan())
        assert "G90" in gcode

    def test_contains_m2(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_drill_plan())
        assert "M2" in gcode

    def test_no_percent_delimiter(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_drill_plan())
        assert "%" not in gcode

    def test_contains_drill_plunge(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_drill_plan())
        assert "Z-5" in gcode


# ---------------------------------------------------------------------------
# C) GRBL Milling Slot
# ---------------------------------------------------------------------------

class TestGrblSlot:
    def test_no_crash(self):
        gcode = grbl_pp.generate_gcode_from_operations(_slot_plan())
        assert isinstance(gcode, str)

    def test_contains_multiple_z_passes(self):
        gcode = grbl_pp.generate_gcode_from_operations(_slot_plan())
        # step_down=2, depth=4 → 2 Z passes
        assert gcode.count("PASS") >= 2

    def test_contains_m2(self):
        gcode = grbl_pp.generate_gcode_from_operations(_slot_plan())
        assert "M2" in gcode

    def test_no_percent_delimiter(self):
        gcode = grbl_pp.generate_gcode_from_operations(_slot_plan())
        assert "%" not in gcode

    def test_contains_z_plunge(self):
        gcode = grbl_pp.generate_gcode_from_operations(_slot_plan())
        assert "Z-" in gcode


# ---------------------------------------------------------------------------
# D) LinuxCNC Milling Pocket
# ---------------------------------------------------------------------------

class TestLinuxcncPocket:
    def test_no_crash(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_pocket_plan())
        assert isinstance(gcode, str)

    def test_contains_raster_rows(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_pocket_plan())
        # Pocket with height=10, step_over=3 → at least 3 rows
        assert gcode.count("ROW") >= 3

    def test_contains_m2(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_pocket_plan())
        assert "M2" in gcode

    def test_no_percent_delimiter(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_pocket_plan())
        assert "%" not in gcode

    def test_contains_z_levels(self):
        gcode = linuxcnc_pp.generate_gcode_from_operations(_pocket_plan())
        # depth=3, step_down=1 → 3 Z passes
        assert gcode.count("Z PASS") >= 3


# ---------------------------------------------------------------------------
# E) Marlin with machine_type "mill" — postprocess_operations must return ok=False
# ---------------------------------------------------------------------------

class TestMarlinMillRejected:
    def test_ok_is_false(self):
        plan = _drill_plan()
        plan["machine_type"] = "mill"
        result = postprocess_operations(plan, postprocessor="marlin")
        assert result["ok"] is False

    def test_errors_not_empty(self):
        plan = _drill_plan()
        plan["machine_type"] = "mill"
        result = postprocess_operations(plan, postprocessor="marlin")
        assert result["errors"]

    def test_error_mentions_machine_type(self):
        plan = _drill_plan()
        plan["machine_type"] = "mill"
        result = postprocess_operations(plan, postprocessor="marlin")
        error_text = " ".join(result["errors"]).lower()
        assert "marlin" in error_text

    def test_no_cnc_motion_in_gcode(self):
        """Marlin must not generate G0/G1 CNC motion for mill operations."""
        plan = _drill_plan()
        plan["machine_type"] = "mill"
        result = postprocess_operations(plan, postprocessor="marlin")
        gcode = result.get("gcode", "")
        # No actual machine motion lines
        assert "G0 X" not in gcode
        assert "G1 X" not in gcode
        assert "G1 Z" not in gcode

    def test_marlin_drill_also_rejected(self):
        result = postprocess_operations(_drill_plan(), postprocessor="marlin")
        assert result["ok"] is False
        assert result["errors"]


# ---------------------------------------------------------------------------
# F) Unsupported postprocessor
# ---------------------------------------------------------------------------

class TestUnsupportedPostprocessor:
    def test_ok_is_false(self, normalized_drill_plan):
        result = postprocess_operations(normalized_drill_plan, postprocessor="unknown_pp")
        assert result["ok"] is False

    def test_gcode_is_empty(self, normalized_drill_plan):
        result = postprocess_operations(normalized_drill_plan, postprocessor="unknown_pp")
        assert result.get("gcode") == ""

    def test_error_mentions_unsupported(self, normalized_drill_plan):
        result = postprocess_operations(normalized_drill_plan, postprocessor="unknown_pp")
        error_text = " ".join(result.get("errors", [])).lower()
        assert "unsupported" in error_text or "unknown_pp" in error_text


# ---------------------------------------------------------------------------
# G) New machine profiles exist
# ---------------------------------------------------------------------------

class TestNewMachineProfiles:
    def test_grbl_drill_profile_exists(self):
        from cnc.tools.machine_profiles import get_machine_profile
        profile = get_machine_profile("generic_drill_grbl_mm")
        assert profile is not None
        assert profile["default_postprocessor"] == "grbl"

    def test_grbl_mill_profile_exists(self):
        from cnc.tools.machine_profiles import get_machine_profile
        profile = get_machine_profile("generic_mill_grbl_mm")
        assert profile is not None
        assert profile["default_postprocessor"] == "grbl"

    def test_linuxcnc_drill_profile_exists(self):
        from cnc.tools.machine_profiles import get_machine_profile
        profile = get_machine_profile("generic_drill_linuxcnc_mm")
        assert profile is not None
        assert profile["default_postprocessor"] == "linuxcnc"

    def test_linuxcnc_mill_profile_exists(self):
        from cnc.tools.machine_profiles import get_machine_profile
        profile = get_machine_profile("generic_mill_linuxcnc_mm")
        assert profile is not None
        assert profile["default_postprocessor"] == "linuxcnc"

    def test_profiles_have_no_feedrate_defaults(self):
        from cnc.tools.machine_profiles import get_machine_profile
        for name in ("generic_drill_grbl_mm", "generic_mill_grbl_mm",
                     "generic_drill_linuxcnc_mm", "generic_mill_linuxcnc_mm"):
            p = get_machine_profile(name)
            assert p["default_feedrate"] is None, f"{name} must not have feedrate default"
            assert p["default_spindle_speed"] is None, f"{name} must not have spindle default"
