"""Tests for cnc/tools/machine_profiles.py — built-in profile registry."""

import pytest
from cnc.tools.machine_profiles import list_machine_profiles, get_machine_profile


# ---------------------------------------------------------------------------
# A) list_machine_profiles
# ---------------------------------------------------------------------------


def test_list_machine_profiles_returns_list():
    result = list_machine_profiles()
    assert isinstance(result, list)


def test_list_machine_profiles_not_empty():
    result = list_machine_profiles()
    assert len(result) > 0


def test_list_machine_profiles_contains_generic_drill_mm():
    names = [p["name"] for p in list_machine_profiles()]
    assert "generic_drill_mm" in names


def test_list_machine_profiles_contains_generic_drill_inch():
    names = [p["name"] for p in list_machine_profiles()]
    assert "generic_drill_inch" in names


def test_list_machine_profiles_returns_copies():
    profiles = list_machine_profiles()
    profiles[0]["name"] = "mutated"
    # Second call must return original, unmodified name
    second = list_machine_profiles()
    assert second[0]["name"] != "mutated"


def test_list_machine_profiles_have_required_keys():
    for p in list_machine_profiles():
        for key in ("name", "machine_type", "units", "work_coordinate_system",
                    "default_safe_z", "default_feedrate", "default_spindle_speed",
                    "default_postprocessor", "notes"):
            assert key in p, f"Profile '{p.get('name')}' missing key '{key}'"


# ---------------------------------------------------------------------------
# B) get_machine_profile — known profiles
# ---------------------------------------------------------------------------


def test_get_profile_generic_drill_mm_not_none():
    result = get_machine_profile("generic_drill_mm")
    assert result is not None


def test_get_profile_generic_drill_mm_machine_type():
    result = get_machine_profile("generic_drill_mm")
    assert result["machine_type"] == "drill"


def test_get_profile_generic_drill_mm_units():
    result = get_machine_profile("generic_drill_mm")
    assert result["units"] == "mm"


def test_get_profile_generic_drill_mm_safe_z():
    result = get_machine_profile("generic_drill_mm")
    assert result["default_safe_z"] == 5.0


def test_get_profile_generic_drill_mm_feedrate_is_none():
    result = get_machine_profile("generic_drill_mm")
    assert result["default_feedrate"] is None


def test_get_profile_generic_drill_mm_spindle_is_none():
    result = get_machine_profile("generic_drill_mm")
    assert result["default_spindle_speed"] is None


def test_get_profile_generic_drill_mm_postprocessor():
    result = get_machine_profile("generic_drill_mm")
    assert result["default_postprocessor"] == "fanuc"


def test_get_profile_generic_drill_inch_not_none():
    result = get_machine_profile("generic_drill_inch")
    assert result is not None


def test_get_profile_generic_drill_inch_units():
    result = get_machine_profile("generic_drill_inch")
    assert result["units"] == "inch"


def test_get_profile_generic_drill_inch_safe_z():
    result = get_machine_profile("generic_drill_inch")
    assert result["default_safe_z"] == 0.2


def test_get_profile_returns_copy():
    result = get_machine_profile("generic_drill_mm")
    result["name"] = "mutated"
    second = get_machine_profile("generic_drill_mm")
    assert second["name"] == "generic_drill_mm"


# ---------------------------------------------------------------------------
# C) get_machine_profile — unknown profile
# ---------------------------------------------------------------------------


def test_get_profile_unknown_returns_none():
    result = get_machine_profile("unknown_profile_xyz")
    assert result is None


def test_get_profile_empty_string_returns_none():
    result = get_machine_profile("")
    assert result is None


def test_get_profile_case_sensitive():
    # Profile names are case-sensitive
    result = get_machine_profile("GENERIC_DRILL_MM")
    assert result is None
