"""Shared pytest fixtures for GENAI4G-CODE tests."""

import pytest


@pytest.fixture
def valid_drill_plan() -> dict:
    """A fully-specified, deterministic drill operation plan (no LLM needed)."""
    return {
        "machine_type": "drill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 5,
        "tools": [
            {
                "id": "T1",
                "name": "5mm drill",
                "diameter": 5,
                "units": "mm",
                "spindle_speed": 1200,
                "feedrate": 100,
            }
        ],
        "operations": [
            {
                "type": "drill",
                "description": "Drill one hole at X0 Y0 to Z-5",
                "tool_id": "T1",
                "parameters": {"x": 0, "y": 0, "z": -5},
                "feedrate": 100,
                "spindle_speed": 1200,
            }
        ],
        "assumptions": [],
        "warnings": [],
    }


@pytest.fixture
def normalized_drill_plan(valid_drill_plan) -> dict:
    """Drill plan after normalize_operation_plan — canonical field names."""
    from cnc.tools.operation_plan_tools import normalize_operation_plan
    return normalize_operation_plan(valid_drill_plan)


@pytest.fixture
def valid_mill_plan() -> dict:
    """A minimal milling plan for regression tests."""
    return {
        "machine_type": "mill",
        "units": "mm",
        "work_coordinate_system": "G54",
        "safe_z": 10,
        "tools": [
            {
                "tool_number": 1,
                "description": "10mm end mill",
                "diameter_mm": 10,
                "type": "end_mill",
            }
        ],
        "operations": [
            {
                "name": "Face pass",
                "type": "face_mill",
                "tool_number": 1,
                "feedrate_mmpm": 800,
                "spindle_rpm": 8000,
                "depth_mm": 0.5,
                "parameters": {
                    "x_start": 0,
                    "y_start": 0,
                    "x_end": 50,
                    "y_end": 30,
                },
            }
        ],
        "assumptions": [],
        "warnings": [],
    }
