"""Built-in machine profiles — lightweight defaults for known machine configurations.

Profiles supply safe defaults for safe_z, units, WCS, and postprocessor.
They deliberately leave feedrate and spindle_speed as None — these are
job-specific values that must be supplied explicitly per job.

Usage:
    from cnc.tools.machine_profiles import list_machine_profiles, get_machine_profile

    profiles = list_machine_profiles()
    profile  = get_machine_profile("generic_drill_mm")
"""

from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# Registry — add new profiles here
# ---------------------------------------------------------------------------

_PROFILES: dict[str, dict] = {
    "generic_mill_mm": {
        "name": "generic_mill_mm",
        "machine_type": "mill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "default_safe_z": 5.0,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "fanuc",
        "notes": [
            "Generic metric milling profile.",
            "Feedrate, spindle speed, tool diameter and cutting parameters must be provided per job.",
        ],
    },
    "generic_mill_inch": {
        "name": "generic_mill_inch",
        "machine_type": "mill",
        "units": "inch",
        "work_coordinate_system": "G54",
        "default_safe_z": 0.2,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "fanuc",
        "notes": [
            "Generic inch milling profile.",
            "Feedrate, spindle speed, tool diameter and cutting parameters must be provided per job.",
        ],
    },
    "generic_drill_mm": {
        "name": "generic_drill_mm",
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "default_safe_z": 5.0,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "fanuc",
        "notes": [
            "Generic metric drilling profile.",
            "Feedrate and spindle speed must be provided per job.",
        ],
    },
    "generic_drill_inch": {
        "name": "generic_drill_inch",
        "machine_type": "drill",
        "units": "inch",
        "work_coordinate_system": "G54",
        "default_safe_z": 0.2,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "fanuc",
        "notes": [
            "Generic inch drilling profile.",
            "Feedrate and spindle speed must be provided per job.",
        ],
    },
    "generic_drill_grbl_mm": {
        "name": "generic_drill_grbl_mm",
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "default_safe_z": 5.0,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "grbl",
        "notes": [
            "Generic metric drilling profile for GRBL controllers.",
            "Feedrate and spindle speed must be provided per job.",
        ],
    },
    "generic_mill_grbl_mm": {
        "name": "generic_mill_grbl_mm",
        "machine_type": "mill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "default_safe_z": 5.0,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "grbl",
        "notes": [
            "Generic metric milling profile for GRBL controllers.",
            "Feedrate, spindle speed, tool diameter and cutting parameters must be provided per job.",
        ],
    },
    "generic_drill_linuxcnc_mm": {
        "name": "generic_drill_linuxcnc_mm",
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "default_safe_z": 5.0,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "linuxcnc",
        "notes": [
            "Generic metric drilling profile for LinuxCNC controllers.",
            "Feedrate and spindle speed must be provided per job.",
        ],
    },
    "generic_mill_linuxcnc_mm": {
        "name": "generic_mill_linuxcnc_mm",
        "machine_type": "mill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "default_safe_z": 5.0,
        "default_feedrate": None,
        "default_spindle_speed": None,
        "default_postprocessor": "linuxcnc",
        "notes": [
            "Generic metric milling profile for LinuxCNC controllers.",
            "Feedrate, spindle speed, tool diameter and cutting parameters must be provided per job.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_machine_profiles() -> list[dict]:
    """Return all built-in machine profiles as a list of dicts.

    Returns copies — callers cannot mutate the registry.
    """
    return [copy.deepcopy(p) for p in _PROFILES.values()]


def get_machine_profile(name: str) -> dict | None:
    """Return the named built-in machine profile, or None if unknown.

    Args:
        name: Profile name, e.g. "generic_drill_mm".

    Returns:
        A copy of the profile dict, or None if the name is not registered.
    """
    profile = _PROFILES.get(name)
    if profile is None:
        return None
    return copy.deepcopy(profile)
