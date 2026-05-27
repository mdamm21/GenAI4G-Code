"""Demo: G-Code Safety Analyzer v1.

Runs the safety analyzer on several example programs to show:
- ok/risk_level/errors/warnings output
- structured findings with severity and line numbers
- summary statistics (Z range, feedrates, spindle speeds)

No API key or LLM required. All analysis is deterministic.
"""

from cnc.validators.safety_analyzer import analyze_gcode_safety

SEPARATOR = "-" * 60


def print_report(label: str, result: dict) -> None:
    print(SEPARATOR)
    print(f"  {label}")
    print(SEPARATOR)
    print(f"  ok         : {result['ok']}")
    print(f"  risk_level : {result['risk_level']}")

    if result["errors"]:
        print(f"  errors     : {result['errors']}")
    if result["warnings"]:
        print(f"  warnings   : {result['warnings']}")

    summary = result["summary"]
    print(f"  units      : {summary['units']}")
    print(f"  positioning: {summary['positioning_mode']}")
    print(f"  wcs        : {summary['work_coordinate_system']}")
    print(f"  z_range    : min={summary['min_z']}  max={summary['max_z']}")
    print(f"  feedrates  : {summary['feedrates']}")
    print(f"  spindle    : {summary['spindle_speeds']}")
    print(f"  lines      : {summary['line_count']} total  {summary['motion_line_count']} motion")

    if result["findings"]:
        print()
        print("  Findings:")
        for f in result["findings"]:
            line_part = f" (line {f['line']})" if f["line"] else ""
            print(f"    [{f['severity'].upper():7s}] {f['code']}{line_part}: {f['message'][:80]}")

    print()


# --- Example 1: Clean drill G-code (low risk, ok=True) ---

CLEAN_DRILL = """\
G21
G90
G54
G0 Z5
S1200 M03
G0 X0 Y0
G01 Z-5 F100
G0 Z5
M05
M30"""

result = analyze_gcode_safety(CLEAN_DRILL, machine_type="drill")
print_report("Example 1: Clean drill G-code (expected: ok=True, risk=low)", result)


# --- Example 2: Rapid plunge to negative Z (high risk, ok=False) ---

RAPID_PLUNGE = """\
G21
G90
G54
G0 Z-10
M30"""

result = analyze_gcode_safety(RAPID_PLUNGE, machine_type="mill")
print_report("Example 2: Rapid plunge to negative Z (expected: ok=False, risk=high)", result)


# --- Example 3: Mixed units — G20 and G21 in same program ---

MIXED_UNITS = """\
G20
G21
G90
G54
G0 Z5
G01 Z-5 F100
M30"""

result = analyze_gcode_safety(MIXED_UNITS, machine_type="mill")
print_report("Example 3: Mixed units (G20 + G21) — expected: ok=False, risk=high", result)


# --- Example 4: Milling program with expected_units and max_depth ---

MILLING = """\
G21
G90
G54
G0 Z5
S3000 M03
G0 X0 Y0
G01 Z-3 F150
G01 X20 F150
G0 Z5
M05
M30"""

result = analyze_gcode_safety(
    MILLING,
    machine_type="mill",
    expected_units="mm",
    safe_z=5.0,
    max_depth=10.0,
)
print_report("Example 4: Milling — expected_units=mm, max_depth=10 (expected: ok=True)", result)


# --- Example 5: 3D printer G-code without hotend temperature ---

PRINTER_NO_TEMP = """\
G21
G90
G0 X0 Y0
G1 E10 F200
M30"""

result = analyze_gcode_safety(PRINTER_NO_TEMP, machine_type="3d_printer")
print_report("Example 5: 3D printer without hotend temp (expected: ok=True, risk=medium)", result)


# --- Example 6: allowed_commands filter ---

DISALLOWED = """\
G21
G90
G54
G40
G01 Z-5 F100
M30"""

result = analyze_gcode_safety(
    DISALLOWED,
    machine_type="mill",
    allowed_commands=["G21", "G90", "G54", "G0", "G1", "G01", "M30"],
)
print_report("Example 6: Disallowed command G40 (expected: ok=False, risk=high)", result)
