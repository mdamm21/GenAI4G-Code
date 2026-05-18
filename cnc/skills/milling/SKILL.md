# Milling Skill

Planning guidelines for CNC milling operations.

## Core Principle

The milling agent MUST plan jobs as structured operation plans (JSON/dict).
It MUST NOT directly emit final G-code.

## Operation Plan Requirements

Every milling operation plan must include:

- `machine_type`: "mill"
- `units`: "mm" or "inch"
- `work_coordinate_system`: e.g. "G54"
- `safe_z`: positive number (height above workpiece for safe rapids)
- `tools`: list of tool specs (number, type, diameter, flutes, material)
- `operations`: list of operations (name, type, tool_number, feedrate, spindle_rpm, depth)
- `assumptions`: all values that were assumed
- `warnings`: anything missing, uncertain, or potentially unsafe

## Setup Assumptions

Always document:
- Workpiece zero location (e.g., "top-left corner of stock, top surface Z=0")
- Stock dimensions
- Fixturing method (vise, clamp, etc.)
- Any required work holding clearance

## Operation Types

| Type | Description |
|------|-------------|
| `face_mill` | Raster passes at ≤75% tool diameter step-over |
| `pocket` | Pocket milling with entry strategy (ramp, helical, or pre-drilled) |
| `profile` | Contour cutting with cutter compensation |
| `drill` | Drilling (G83 peck cycle for depth > 3x diameter) |
| `bore` | Boring (G85 feed-in/feed-out for precision) |

## Feeds and Speeds

If exact material data is available, calculate:
- Surface footage (SFM) from material and tool
- RPM from SFM and tool diameter
- Chip load from material and flute count
- Feed rate = RPM × flute count × chip load

If not, use conservative defaults and add to assumptions.

## Warnings

Add warnings for:
- Missing material specification
- Missing tool data
- Depth of cut exceeding 1x tool diameter
- No work offset specified
- Missing coolant strategy
