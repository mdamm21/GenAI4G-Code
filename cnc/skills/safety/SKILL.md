# Safety Skill

Rules the CNC Supervisor Agent and all subagents must always follow.

## Hard Rules

- Never generate final G-code without validation.
- Prefer safe Z moves before any XY rapid motion.
- Never rapid (G00) into the workpiece — use G01 for all plunge moves.
- Always stop spindle (M05) and cancel coolant (M09) before program end (M30).

## Required Information (warn if missing)

Warn and add to `missing_info` if any of these are absent:

- Material type and hardness
- Raw stock dimensions
- Tool type, diameter, and flute count
- Feedrate and spindle speed
- Work offset (G54–G59)
- Unit declaration (G20/G21)
- Safe Z height

## Missing Critical Data

- Do not silently invent critical machining parameters.
- If required safety data is absent, return `missing_info` instead of unsafe G-code.
- Prefer conservative values over aggressive ones when assumptions are necessary.
- Always document every assumption in the `assumptions` list.

## Validation Requirement

All G-code output MUST pass through the G-code validator before being returned
to the user. The validator must confirm:
- ok: true
- No unresolved errors
