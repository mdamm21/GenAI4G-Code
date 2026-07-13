"""Material Library v0 — context and caution notices for workpiece materials.

This is NOT a cutting data database.
It provides:
  - Material names and IDs for normalisation
  - Informational notes about machining considerations
  - Warnings about risk categories (stainless steel, wood, plastic)
  - Supported operation types per material
  - Reference cutting speeds (Vc) per category for *recommendations only*

Feeding, speeds, step-down, and step-over are NEVER derived from this module.
All machining parameters must be supplied explicitly by the operator.
Reference cutting speeds are used solely to present informational suggestions
that the operator must confirm or override.

Public API:
    list_materials()         → list[dict]
    get_material(id)         → dict | None
    find_materials(...)      → list[dict]
    normalize_material(...)  → dict
"""

from __future__ import annotations

import copy
import math

# ---------------------------------------------------------------------------
# Reference cutting speeds (Vc in m/min) for HSS tooling — informational only.
# These are conservative starting points. Actual values depend on tool
# coating, machine rigidity, coolant, and workpiece condition.
# Keys are material *categories* (not individual material IDs).
# Values are (Vc_low, Vc_high) ranges in m/min for drilling with HSS.
# ---------------------------------------------------------------------------

_REFERENCE_VC_HSS_DRILL: dict[str, tuple[float, float]] = {
    "aluminum":        (60, 100),
    "steel":           (20,  35),
    "stainless_steel": (10,  20),
    "brass":           (40,  70),
    "plastic":         (30,  60),
    "wood":            (50, 100),
    "composite":       (20,  40),
}

# ---------------------------------------------------------------------------
# Reference feed-per-revolution (mm/rev) for HSS drills — informational only.
# Values are (f_low, f_high) conservative ranges.  Actual feed depends on
# drill geometry, coating, coolant, depth/diameter ratio, and machine rigidity.
# Keyed by material *category*.
# Common rule of thumb: f ≈ 0.01 * D  (mm/rev), but varies by material.
# ---------------------------------------------------------------------------

_REFERENCE_FPR_HSS_DRILL: dict[str, tuple[float, float]] = {
    #                      f_low   f_high   (mm/rev, for D ≈ 5-12 mm)
    "aluminum":        (0.10, 0.25),
    "steel":           (0.08, 0.18),
    "stainless_steel": (0.05, 0.12),
    "brass":           (0.10, 0.20),
    "plastic":         (0.10, 0.20),
    "wood":            (0.15, 0.30),
    "composite":       (0.05, 0.15),
}

# ---------------------------------------------------------------------------
# Built-in material registry
# ---------------------------------------------------------------------------

BUILTIN_MATERIALS: dict[str, dict] = {
    "aluminum_6061": {
        "id": "aluminum_6061",
        "name": "Aluminum 6061",
        "category": "aluminum",
        "machinability": "easy",
        "notes": [
            "Common machinable aluminum alloy.",
            "Actual cutting parameters depend on tool, machine rigidity, coolant and setup.",
        ],
        "warnings": [
            "Do not assume feedrate or spindle speed from material alone.",
        ],
        "supported_operations": ["drill", "facing", "slot", "pocket"],
    },
    "aluminum_generic": {
        "id": "aluminum_generic",
        "name": "Aluminum (generic)",
        "category": "aluminum",
        "machinability": "easy",
        "notes": [
            "Generic aluminum placeholder.",
            "Alloy and temper affect machinability significantly.",
        ],
        "warnings": [
            "Verify alloy and temper before selecting cutting parameters.",
        ],
        "supported_operations": ["drill", "facing", "slot", "pocket"],
    },
    "mild_steel": {
        "id": "mild_steel",
        "name": "Mild steel",
        "category": "steel",
        "machinability": "medium",
        "notes": [
            "Generic mild steel placeholder.",
            "Requires machine- and tool-specific cutting parameters.",
        ],
        "warnings": [
            "Do not use aluminum-like cutting assumptions.",
            "Check tool suitability and workholding carefully.",
        ],
        "supported_operations": ["drill", "facing", "slot", "pocket"],
    },
    "stainless_steel_generic": {
        "id": "stainless_steel_generic",
        "name": "Generic stainless steel",
        "category": "stainless_steel",
        "machinability": "hard",
        "notes": [
            "Generic stainless steel placeholder.",
            "Work hardening and tool wear can be significant.",
        ],
        "warnings": [
            "Do not generate cutting parameters automatically.",
            "Expert review required before machining.",
        ],
        "supported_operations": ["drill", "facing", "slot", "pocket"],
    },
    "acrylic": {
        "id": "acrylic",
        "name": "Acrylic",
        "category": "plastic",
        "machinability": "medium",
        "notes": [
            "Plastic material; melting and chip evacuation can be concerns.",
        ],
        "warnings": [
            "Feeds, speeds and chip evacuation must be verified.",
        ],
        "supported_operations": ["drill", "facing", "slot", "pocket"],
    },
    "plywood": {
        "id": "plywood",
        "name": "Plywood",
        "category": "wood",
        "machinability": "easy",
        "notes": [
            "Wood composite material.",
            "Dust extraction and fire risk must be considered.",
        ],
        "warnings": [
            "Verify dust collection and fire safety.",
        ],
        "supported_operations": ["drill", "slot", "pocket"],
    },
    "brass_generic": {
        "id": "brass_generic",
        "name": "Brass (generic)",
        "category": "brass",
        "machinability": "easy",
        "notes": [
            "Generally free-machining. Chips can be stringy depending on alloy.",
        ],
        "warnings": [
            "Verify alloy; some brass grades are less free-machining than others.",
        ],
        "supported_operations": ["drill", "facing", "slot", "pocket"],
    },
}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def list_materials() -> list[dict]:
    """Return all built-in materials as a list of plain dicts (deep copies)."""
    return [copy.deepcopy(m) for m in BUILTIN_MATERIALS.values()]


def get_material(material_id: str) -> dict | None:
    """Return a single material by ID (deep copy), or None if not found."""
    m = BUILTIN_MATERIALS.get(material_id)
    return copy.deepcopy(m) if m is not None else None


def find_materials(
    category: str | None = None,
    operation_type: str | None = None,
    machinability: str | None = None,
) -> list[dict]:
    """Return materials matching all supplied filter criteria.

    Filters are additive (AND). Omitting a filter means 'any'.

    Args:
        category:       Material category, e.g. "aluminum", "steel".
        operation_type: Operation the material must support, e.g. "pocket".
        machinability:  Qualitative difficulty, e.g. "easy", "hard".

    Returns:
        List of matching material dicts (deep copies).
    """
    results: list[dict] = []
    for m in BUILTIN_MATERIALS.values():
        if category is not None and m.get("category") != category:
            continue
        if operation_type is not None:
            if operation_type not in m.get("supported_operations", []):
                continue
        if machinability is not None and m.get("machinability") != machinability:
            continue
        results.append(copy.deepcopy(m))
    return results


def normalize_material(material: str | None) -> dict:
    """Resolve a material name or ID to a known library entry.

    Matching priority:
    1. Exact ID match (case-sensitive).
    2. Case-insensitive ID match.
    3. Case-insensitive name match.

    Args:
        material: Free-text material name or library ID (e.g. "Aluminum 6061",
                  "aluminum_6061", "MILD STEEL", None).

    Returns:
        {
          "ok":          bool,
          "material":    dict | None,
          "material_id": str  | None,
          "warnings":    list[str],
          "errors":      list[str],
        }
    """
    if not material or not material.strip():
        return {
            "ok": False,
            "material": None,
            "material_id": None,
            "warnings": ["Material was not specified."],
            "errors": [],
        }

    material_stripped = material.strip()

    # 1. Exact ID match
    if material_stripped in BUILTIN_MATERIALS:
        m = copy.deepcopy(BUILTIN_MATERIALS[material_stripped])
        return {
            "ok": True,
            "material": m,
            "material_id": m["id"],
            "warnings": [],
            "errors": [],
        }

    # 2. Case-insensitive ID or name match
    material_lower = material_stripped.lower()
    for entry in BUILTIN_MATERIALS.values():
        if (
            entry["id"].lower() == material_lower
            or entry["name"].lower() == material_lower
        ):
            m = copy.deepcopy(entry)
            return {
                "ok": True,
                "material": m,
                "material_id": m["id"],
                "warnings": [],
                "errors": [],
            }

    # No match
    return {
        "ok": False,
        "material": None,
        "material_id": None,
        "warnings": [f"Unknown material: {material_stripped!r}. Check spelling or use list_available_materials()."],
        "errors": [],
    }


def recommend_spindle_rpm(
    material_id_or_category: str | None,
    tool_diameter_mm: float | None,
) -> dict:
    """Return an informational RPM recommendation based on material and tool diameter.

    Uses the simple formula: RPM = Vc * 1000 / (pi * D)
    with conservative HSS reference cutting speeds.

    This is a *suggestion only* — the operator must confirm or override.

    Returns:
        {
            "ok":       bool,        # True if a recommendation could be computed
            "rpm_low":  int | None,  # Lower bound
            "rpm_high": int | None,  # Upper bound
            "vc_low":   float | None,
            "vc_high":  float | None,
            "note":     str,         # Human-readable explanation
        }
    """
    if not tool_diameter_mm or tool_diameter_mm <= 0:
        return {"ok": False, "rpm_low": None, "rpm_high": None,
                "vc_low": None, "vc_high": None,
                "note": "Tool diameter unknown — cannot compute recommendation."}

    # Resolve category
    category: str | None = None
    if material_id_or_category:
        # Direct category match
        if material_id_or_category in _REFERENCE_VC_HSS_DRILL:
            category = material_id_or_category
        else:
            # Look up material entry to get its category
            mat = get_material(material_id_or_category)
            if mat:
                category = mat.get("category")

    if not category or category not in _REFERENCE_VC_HSS_DRILL:
        return {"ok": False, "rpm_low": None, "rpm_high": None,
                "vc_low": None, "vc_high": None,
                "note": "Material category unknown — cannot compute recommendation."}

    vc_low, vc_high = _REFERENCE_VC_HSS_DRILL[category]
    rpm_low = int(vc_low * 1000 / (math.pi * tool_diameter_mm))
    rpm_high = int(vc_high * 1000 / (math.pi * tool_diameter_mm))

    return {
        "ok": True,
        "rpm_low": rpm_low,
        "rpm_high": rpm_high,
        "vc_low": vc_low,
        "vc_high": vc_high,
        "note": (
            f"HSS drill D{tool_diameter_mm}mm in {category}: "
            f"Vc {vc_low}-{vc_high} m/min = {rpm_low}-{rpm_high} RPM (reference only)"
        ),
    }


def recommend_drill_feedrate(
    material_id_or_category: str | None,
    tool_diameter_mm: float | None,
    spindle_rpm: float | None = None,
) -> dict:
    """Return an informational feedrate recommendation for drilling.

    Uses: Feed (mm/min) = feed_per_rev (mm/rev) x RPM
    If RPM is not known, uses the midpoint of the recommended RPM range.

    This is a *suggestion only* -- the operator must confirm or override.

    Returns:
        {
            "ok":           bool,
            "feed_low":     int | None,    # mm/min lower bound
            "feed_high":    int | None,    # mm/min upper bound
            "fpr_low":      float | None,  # feed per rev low
            "fpr_high":     float | None,  # feed per rev high
            "rpm_used":     int | None,    # RPM used for calculation
            "note":         str,
        }
    """
    if not tool_diameter_mm or tool_diameter_mm <= 0:
        return {"ok": False, "feed_low": None, "feed_high": None,
                "fpr_low": None, "fpr_high": None, "rpm_used": None,
                "note": "Tool diameter unknown -- cannot compute recommendation."}

    # Resolve category
    category: str | None = None
    if material_id_or_category:
        if material_id_or_category in _REFERENCE_FPR_HSS_DRILL:
            category = material_id_or_category
        else:
            mat = get_material(material_id_or_category)
            if mat:
                category = mat.get("category")

    if not category or category not in _REFERENCE_FPR_HSS_DRILL:
        return {"ok": False, "feed_low": None, "feed_high": None,
                "fpr_low": None, "fpr_high": None, "rpm_used": None,
                "note": "Material category unknown -- cannot compute recommendation."}

    fpr_low, fpr_high = _REFERENCE_FPR_HSS_DRILL[category]

    # Determine RPM to use
    rpm: float
    if spindle_rpm and spindle_rpm > 0:
        rpm = spindle_rpm
    else:
        # Use midpoint of recommended RPM range
        rpm_rec = recommend_spindle_rpm(material_id_or_category, tool_diameter_mm)
        if rpm_rec["ok"]:
            rpm = (rpm_rec["rpm_low"] + rpm_rec["rpm_high"]) / 2
        else:
            return {"ok": False, "feed_low": None, "feed_high": None,
                    "fpr_low": fpr_low, "fpr_high": fpr_high, "rpm_used": None,
                    "note": "Cannot determine RPM -- feedrate calculation incomplete."}

    rpm_int = int(rpm)
    feed_low = int(fpr_low * rpm)
    feed_high = int(fpr_high * rpm)

    return {
        "ok": True,
        "feed_low": feed_low,
        "feed_high": feed_high,
        "fpr_low": fpr_low,
        "fpr_high": fpr_high,
        "rpm_used": rpm_int,
        "note": (
            f"HSS drill D{tool_diameter_mm}mm in {category} @ {rpm_int} RPM: "
            f"f={fpr_low}-{fpr_high} mm/rev = {feed_low}-{feed_high} mm/min "
            f"(reference only)"
        ),
    }
