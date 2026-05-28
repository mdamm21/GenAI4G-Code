"""Material Library v0 — context and caution notices for workpiece materials.

This is NOT a cutting data database.
It provides:
  - Material names and IDs for normalisation
  - Informational notes about machining considerations
  - Warnings about risk categories (stainless steel, wood, plastic)
  - Supported operation types per material

Feeding, speeds, step-down, and step-over are NEVER derived from this module.
All machining parameters must be supplied explicitly by the operator.

Public API:
    list_materials()         → list[dict]
    get_material(id)         → dict | None
    find_materials(...)      → list[dict]
    normalize_material(...)  → dict
"""

from __future__ import annotations

import copy

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
