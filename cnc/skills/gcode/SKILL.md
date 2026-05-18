# G-Code Skill

Best practices for generating safe, readable, and standard-compliant G-code.

## Unit Declaration

- Always declare units explicitly at program start.
- Use `G21` for millimeters.
- Use `G20` for inches.
- Never leave units implicit.

## Positioning Mode

- Always declare positioning mode explicitly.
- Use `G90` for absolute positioning (preferred default).
- Use `G91` for incremental positioning only when explicitly required.
- Reset to `G90` after any incremental section.

## Work Coordinate System

- Always specify work coordinate system explicitly.
- Prefer `G54` (first work offset) as the default.
- Document the physical meaning of the WCS origin in comments.

## Program Structure

Every G-code program must include:

1. `%` (program start delimiter, Fanuc style)
2. Program number (`O<nnnn>`)
3. Safety cancel block: `G17 G40 G49 G80`
4. Unit declaration: `G20` or `G21`
5. Positioning mode: `G90`
6. Feed mode: `G94` (feed per minute)
7. Work offset: `G54` (or other WCS)
8. Tool call: `T<n> M06`
9. Spindle start: `S<rpm> M03` or `M04`
10. Rapid to safe Z: `G00 Z<safe_height>`
11. Cutting moves with explicit feedrates
12. Retract: `G00 Z<safe_height>`
13. Spindle stop: `M05`
14. Coolant off: `M09`
15. Return home: `G28 G91 Z0.`
16. `G90`
17. `M30` (program end + rewind)
18. `%`

## Comments

- Use parentheses for comments: `(THIS IS A COMMENT)`
- Comment every major section: tool change, operation start, safety moves.
- Document all assumptions in the header comment block.

## Conservative Defaults

- Use conservative feeds and speeds when exact values are unknown.
- Prefer smaller depth-of-cut over aggressive material removal.
- Explain all assumptions clearly.
