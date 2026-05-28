"""Tests for cnc/tools/material_library.py — no LLM, no API key required."""

from __future__ import annotations

import pytest

from cnc.tools.material_library import (
    find_materials,
    get_material,
    list_materials,
    normalize_material,
)


# ---------------------------------------------------------------------------
# A) list_materials
# ---------------------------------------------------------------------------


def test_list_materials_returns_list():
    result = list_materials()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_materials_contains_aluminum_6061():
    ids = [m["id"] for m in list_materials()]
    assert "aluminum_6061" in ids


def test_list_materials_contains_mild_steel():
    ids = [m["id"] for m in list_materials()]
    assert "mild_steel" in ids


def test_list_materials_contains_stainless_steel():
    ids = [m["id"] for m in list_materials()]
    assert "stainless_steel_generic" in ids


def test_list_materials_each_has_required_keys():
    for m in list_materials():
        for key in ("id", "name", "category", "machinability", "notes", "warnings"):
            assert key in m, f"Material {m.get('id')!r} missing key {key!r}"


def test_list_materials_returns_deep_copies():
    mats = list_materials()
    mats[0]["name"] = "MODIFIED"
    mats2 = list_materials()
    assert mats2[0]["name"] != "MODIFIED", "list_materials must return deep copies"


# ---------------------------------------------------------------------------
# B) get_material
# ---------------------------------------------------------------------------


def test_get_material_aluminum_6061():
    m = get_material("aluminum_6061")
    assert m is not None
    assert m["id"] == "aluminum_6061"
    assert m["category"] == "aluminum"


def test_get_material_mild_steel_machinability():
    m = get_material("mild_steel")
    assert m is not None
    assert m["machinability"] == "medium"


def test_get_material_stainless_steel_machinability():
    m = get_material("stainless_steel_generic")
    assert m is not None
    assert m["machinability"] == "hard"


def test_get_material_unknown_returns_none():
    assert get_material("unknown") is None


def test_get_material_nonexistent_returns_none():
    assert get_material("not_a_real_material") is None


def test_get_material_returns_deep_copy():
    m = get_material("aluminum_6061")
    m["name"] = "HACKED"
    m2 = get_material("aluminum_6061")
    assert m2["name"] != "HACKED", "get_material must return deep copies"


# ---------------------------------------------------------------------------
# C) find_materials
# ---------------------------------------------------------------------------


def test_find_materials_by_category_aluminum():
    results = find_materials(category="aluminum")
    assert len(results) > 0
    for m in results:
        assert m["category"] == "aluminum"


def test_find_materials_aluminum_contains_6061():
    ids = [m["id"] for m in find_materials(category="aluminum")]
    assert "aluminum_6061" in ids


def test_find_materials_by_operation_pocket():
    results = find_materials(operation_type="pocket")
    ids = [m["id"] for m in results]
    assert "aluminum_6061" in ids


def test_find_materials_by_operation_drill():
    results = find_materials(operation_type="drill")
    assert len(results) > 0


def test_find_materials_wood_no_facing():
    # Plywood doesn't support facing
    results = find_materials(category="wood", operation_type="facing")
    for m in results:
        assert "facing" in m.get("supported_operations", [])


def test_find_materials_stainless_is_hard():
    results = find_materials(category="stainless_steel")
    for m in results:
        assert m["machinability"] == "hard"


def test_find_materials_no_filters_returns_all():
    all_mats = find_materials()
    listed = list_materials()
    assert len(all_mats) == len(listed)


def test_find_materials_no_match_returns_empty():
    results = find_materials(category="unknown_category_xyz")
    assert results == []


# ---------------------------------------------------------------------------
# D) normalize_material
# ---------------------------------------------------------------------------


def test_normalize_material_exact_id():
    result = normalize_material("aluminum_6061")
    assert result["ok"] is True
    assert result["material_id"] == "aluminum_6061"
    assert result["material"] is not None


def test_normalize_material_case_insensitive_name():
    result = normalize_material("Aluminum 6061")
    assert result["ok"] is True
    assert result["material_id"] == "aluminum_6061"


def test_normalize_material_lowercase_name():
    result = normalize_material("aluminum 6061")
    assert result["ok"] is True


def test_normalize_material_mild_steel():
    result = normalize_material("Mild steel")
    assert result["ok"] is True
    assert result["material_id"] == "mild_steel"


def test_normalize_material_unknown():
    result = normalize_material("not_real_material")
    assert result["ok"] is False
    assert result["material"] is None
    assert result["material_id"] is None
    assert result["warnings"]


def test_normalize_material_none():
    result = normalize_material(None)
    assert result["ok"] is False
    assert "Material was not specified" in " ".join(result["warnings"])


def test_normalize_material_empty_string():
    result = normalize_material("")
    assert result["ok"] is False


def test_normalize_material_unknown_warning_text():
    result = normalize_material("FakeUnobtainium")
    assert any("Unknown material" in w for w in result["warnings"])


def test_normalize_material_returns_dict():
    for val in [None, "", "aluminum_6061", "Mild steel", "bogus"]:
        r = normalize_material(val)
        assert isinstance(r, dict), f"Expected dict for input {val!r}"
        for key in ("ok", "material", "material_id", "warnings", "errors"):
            assert key in r, f"Missing key {key!r} for input {val!r}"
