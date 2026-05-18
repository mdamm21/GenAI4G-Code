# Drilling Skill

Planning guidelines for CNC drilling operations.

## Core Principle

The drilling agent MUST plan jobs as structured operation plans (JSON/dict).
It MUST NOT directly emit final G-code.

## Required Information

Always request or warn if missing:

- Hole X, Y coordinates (list of positions)
- Hole depth (Z depth from surface)
- Hole diameter (determines tool selection)
- Material type (affects feed/speed)
- Safe Z height
- Work coordinate system offset

## Drill Cycle Selection

| Condition | Recommended Cycle |
|-----------|-------------------|
| Depth ≤ 3x diameter | G81 (standard drill) |
| Depth > 3x diameter | G83 (peck drill, Q = 1/3 diameter) |
| Precision hole | G85 (bore, feed in/feed out) |
| Reaming | G85 or G86 after pilot drill |

## Peck Drilling (G83)

When depth > 3x diameter:
- Set peck increment Q to approximately 1/3 of hole diameter
- Retract fully between pecks (chip clearance)
- Reduce feedrate by 20-30% for deep holes

## Warnings

Add warnings for:
- Missing hole coordinates
- Missing hole depth
- Missing tool diameter
- Hole depth > 10x diameter (very deep — consider gun drilling)
- No safe Z specified
- Overlapping holes closer than 2x diameter
- Hole near part edge (wall thickness warning)
