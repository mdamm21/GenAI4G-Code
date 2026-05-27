# MCP Developer Setup

This document explains how to connect an MCP client to the GENAI4G-CODE server.

---

## Start the MCP server

```bash
python -m cnc.server
```

The server uses stdio transport (reads from stdin, writes to stdout). It will wait for MCP messages — this is expected behavior.

---

## MCP Inspector

Use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test the tools interactively:

```bash
npx @modelcontextprotocol/inspector python -m cnc.server
```

This opens a browser UI where you can call individual tools like `list_supported_machines`, `validate_gcode`, `validate_plan`, `postprocess_plan`, and `generate_gcode`.

---

## Claude Desktop configuration

Add the following to your Claude Desktop MCP configuration file.

**Location:**
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Configuration snippet:**

```json
{
  "mcpServers": {
    "genai4g-code": {
      "command": "python",
      "args": ["-m", "cnc.server"],
      "env": {
        "PYTHONPATH": "C:\\absolute\\path\\to\\GenAI4G-Code",
        "ANTHROPIC_API_KEY": "your-key-here"
      }
    }
  }
}
```

> **Important:** Replace `C:\\absolute\\path\\to\\GenAI4G-Code` with the actual absolute path to your repository. On macOS/Linux use forward slashes.

> **Security:** Do not commit API keys to version control. Use a `.env` file or system environment variables instead. The `env` block in the Claude Desktop config is local to your machine only.

---

## Available MCP tools

| Tool | LLM needed | Description |
|---|---|---|
| `list_supported_machines` | No | Returns supported machine type identifiers |
| `list_profiles` | No | Returns all built-in machine profiles |
| `get_profile` | No | Returns a single machine profile by name |
| `validate_gcode` | No | Static safety check on a G-code program |
| `validate_plan` | No | Structural validation of an OperationPlan dict |
| `postprocess_plan` | No | Convert an OperationPlan to G-code (deterministic) |
| `generate_drill_gcode` | **No** | Single-hole drill pipeline: explicit params → G-code (deterministic) |
| `generate_drill_pattern_gcode` | **No** | Multi-hole drill pattern: holes list + optional profile → G-code (deterministic) |
| `generate_milling_facing_gcode` | **No** | Rectangular facing: explicit geometry → G-code (deterministic, no cutter comp) |
| `generate_milling_slot_gcode` | **No** | Straight slot along X or Y: explicit geometry → G-code (deterministic, no cutter comp) |
| `generate_milling_pocket_gcode` | **No** | Rectangular pocket, raster clearing: explicit geometry → G-code (deterministic, no cutter comp) |
| `analyze_gcode_safety_report` | **No** | Structured static safety analysis of a G-code program → risk report (deterministic) |
| `plan_operation` | Yes | NL prompt → OperationPlan (structured, no G-code, requires API key) |
| `generate_gcode` | Yes | Full agentic pipeline: NL prompt → OperationPlan → G-code (requires API key) |

---

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Required for `generate_gcode` (agent) | — |
| `GENAI4G_MODEL` | Anthropic model for the CNC supervisor | `claude-sonnet-4-6` |
| `GENAI4G_MAX_TURNS` | Max agent loop iterations | `20` |
| `CNC_AGENT_MODEL` | Model for deepagents (if installed) | `openai:gpt-4o` |

---

## Tool call examples

### generate_drill_gcode (deterministic, no API key needed)

The recommended starting point. Supply explicit machining parameters — no LLM involved.

```json
{
  "x": 0,
  "y": 0,
  "depth": 5,
  "tool_diameter": 5,
  "safe_z": 5,
  "feedrate": 100,
  "spindle_speed": 1200,
  "units": "mm",
  "work_coordinate_system": "G54",
  "material": "6061 aluminium",
  "postprocessor": "fanuc"
}
```

**Notes:**
- `depth` is a **positive** number (e.g. `5` drills to Z=-5). Negative values are accepted and normalised with a warning.
- `spindle_speed` is optional. If omitted, M03 is skipped and a warning is returned.
- `postprocessor`: `"fanuc"` (default), `"grbl"`, `"linuxcnc"`, or `"marlin"`.
  - `"fanuc"` — Fanuc-compatible with `%`, `O0001`, `M30`.
  - `"grbl"` — GRBL firmware compatible: no `%`, no tool changer, ends with `M2`.
  - `"linuxcnc"` — Conservative RS274NGC: no `%`, header identifies LinuxCNC style, ends with `M2`.
  - `"marlin"` — **Stub only.** Always returns `ok: false` for CNC operations. Not implemented.
- This tool is deterministic and requires no API key.
- Generated G-code must still be reviewed and simulated before use on a real machine.

---

### validate_plan (deterministic, no API key needed)

```json
{
  "machine_type": "drill",
  "units": "mm",
  "work_coordinate_system": "G54",
  "safe_z": 5,
  "tools": [{"tool_number": 1, "description": "5mm drill", "diameter_mm": 5}],
  "operations": [
    {
      "type": "drill",
      "name": "hole 1",
      "tool_number": 1,
      "feedrate_mmpm": 100,
      "spindle_rpm": 1200,
      "parameters": {"x": 0, "y": 0, "z": -5}
    }
  ]
}
```

### generate_gcode (requires ANTHROPIC_API_KEY)

```json
{
  "prompt": "Drill a 5mm hole at X0 Y0, depth 10mm, in aluminium. Units mm. Safe Z 5mm.",
  "machine_type": "drill"
}
```

---

### list_profiles (deterministic, no API key needed)

```json
{}
```

Returns all built-in machine profiles with their defaults.

---

### get_profile (deterministic, no API key needed)

```json
{
  "name": "generic_drill_mm"
}
```

Returns the named profile or `{"ok": false, "profile": null, "error": "..."}` if unknown.

---

### generate_drill_pattern_gcode (deterministic, no API key needed)

```json
{
  "holes": [
    {"x": 0, "y": 0, "depth": 5},
    {"x": 10, "y": 0, "depth": 5},
    {"x": 10, "y": 10, "depth": 8}
  ],
  "tool_diameter": 5,
  "feedrate": 100,
  "spindle_speed": 1200,
  "machine_profile": "generic_drill_mm"
}
```

**Notes:**
- Each `hole` requires `x`, `y`, `depth` (positive depth → Z negative).
- `machine_profile` is optional. When supplied, its `default_safe_z` fills in `safe_z` if not provided.
- `feedrate` and `spindle_speed` are **never invented** — missing values produce errors or warnings.
- Spindle starts once and stays running while drilling holes at the same speed.
- `postprocessor`: `"fanuc"` (default), `"grbl"`, `"marlin"`, or `"linuxcnc"`.
- Machine profiles are defaults, not safety guarantees. Always review before machine use.

---

### generate_milling_facing_gcode (deterministic, no API key needed)

```json
{
  "origin_x": 0,
  "origin_y": 0,
  "width": 20,
  "height": 10,
  "depth": 1,
  "step_over": 2,
  "tool_diameter": 5,
  "safe_z": 5,
  "feedrate": 150,
  "spindle_speed": 3000,
  "machine_profile": "generic_mill_mm"
}
```

**Notes:**
- `depth` is a positive number (e.g. `1` → cuts to Z=-1). Negative values normalised with warning.
- `machine_profile` (optional) — `"generic_mill_mm"` supplies `safe_z=5.0` if not provided.
- No cutter compensation (G41/G42). No tool radius offset. Program the centerline path.
- This is a conservative MVP — parallel X passes with Y step-over, not a full CAM algorithm.
- `postprocessor`: `"fanuc"` (default), `"grbl"`, or `"linuxcnc"`. All three produce proper facing paths. `"marlin"` always returns `ok: false`.
- All output is deterministic and requires no API key. Review and simulate before use.

---

### generate_milling_slot_gcode (deterministic, no API key needed)

```json
{
  "start_x": 0,
  "start_y": 0,
  "length": 20,
  "depth": 3,
  "tool_diameter": 5,
  "safe_z": 5,
  "feedrate": 150,
  "spindle_speed": 3000,
  "direction": "x",
  "step_down": 1,
  "machine_profile": "generic_mill_mm"
}
```

**Notes:**
- `direction`: `"x"` or `"y"`. Any other value returns `ok=false` with an error.
- `step_down` (required, > 0): Z increment per pass. Multiple passes until `target_z` is reached.
- `depth` is a positive number (e.g. `3` → final cut at Z=-3). Negative values normalised with warning.
- `machine_profile` (optional) — `"generic_mill_mm"` supplies `safe_z=5.0` if not provided.
- Slot width equals tool diameter. No cutter compensation (G41/G42).
- `postprocessor`: `"fanuc"` (default), `"grbl"`, or `"linuxcnc"`. All three produce proper slot paths. `"marlin"` always returns `ok: false`.
- All output is deterministic and requires no API key. Review and simulate before use.

---

### generate_milling_pocket_gcode (deterministic, no API key needed)

```json
{
  "origin_x": 0,
  "origin_y": 0,
  "width": 20,
  "height": 10,
  "depth": 3,
  "tool_diameter": 5,
  "step_down": 1,
  "step_over": 2,
  "safe_z": 5,
  "feedrate": 150,
  "spindle_speed": 3000,
  "machine_profile": "generic_mill_mm"
}
```

**Notes:**
- `step_down` (required, > 0): Z increment per pass. Multiple passes until `target_z` is reached.
- `step_over` (required, > 0): Radial step-over per raster row. Values > `tool_diameter` produce a warning about potential uncut material.
- `depth` is a positive number (e.g. `3` → final cut at Z=-3). Negative values normalised with warning.
- `machine_profile` (optional) — `"generic_mill_mm"` supplies `safe_z=5.0` if not provided.
- Simple raster clearing — parallel rows along X, Y step-over. No helix-ramping, trochoidal toolpaths, or adaptive clearing.
- No cutter compensation (G41/G42). No tool radius offset.
- `postprocessor`: `"fanuc"` (default), `"grbl"`, or `"linuxcnc"`. All three produce proper pocket raster paths. `"marlin"` always returns `ok: false`.
- All output is deterministic and requires no API key. Review and simulate before use.

---

## Postprocessor dialects

All deterministic tools accept a `postprocessor` parameter:

| Value | Status | Behaviour |
|---|---|---|
| `"fanuc"` | MVP | `%`, `O0001`, `M30`. Reference dialect. |
| `"grbl"` | MVP | No `%`, no `M06`, ends with `M5 / G0 Zsafe / M2`. |
| `"linuxcnc"` | MVP | No `%`, `(Conservative LinuxCNC-style postprocessor)` header, ends with `M2`. |
| `"marlin"` | stub | Always `ok: false`. No CNC motion generated. |

**Example — use GRBL for a drill pattern:**

```json
{
  "holes": [{"x": 0, "y": 0, "depth": 5}, {"x": 20, "y": 0, "depth": 5}],
  "tool_diameter": 5,
  "feedrate": 100,
  "spindle_speed": 1200,
  "postprocessor": "grbl"
}
```

**Example — use LinuxCNC for a pocket:**

```json
{
  "origin_x": 0,
  "origin_y": 0,
  "width": 20,
  "height": 10,
  "depth": 3,
  "tool_diameter": 5,
  "step_down": 1,
  "step_over": 2,
  "safe_z": 5,
  "feedrate": 150,
  "spindle_speed": 3000,
  "postprocessor": "linuxcnc"
}
```

---

### analyze_gcode_safety_report (deterministic, no API key needed)

```json
{
  "gcode": "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30",
  "machine_type": "drill",
  "expected_units": "mm",
  "safe_z": 5.0,
  "max_depth": 10.0
}
```

**Notes:**
- `machine_type`: `"mill"` (default), `"drill"`, `"lathe"`, `"laser"`, `"3d_printer"`. Affects machine-specific checks (spindle, laser enable, hotend temp).
- `expected_units`: `"mm"` or `"inch"`. Error if program declares the other unit.
- `safe_z`: Expected retract height — used to warn if program never reaches it.
- `max_depth`: Maximum allowed cutting depth (positive number). Error if `min_z < -max_depth`.
- `allowed_commands`: Optional whitelist of `"G<n>"` / `"M<n>"` strings. Error on any not in list.
- Returns `ok`, `risk_level` (`"low"` / `"medium"` / `"high"`), `errors`, `warnings`, `summary`, `findings`.
- Each finding has: `severity` (`"info"` / `"warning"` / `"error"`), `code`, `line`, `message`, `text`.
- Static analysis only — no machine motion simulated. Always review before use on a real machine.

---

### plan_operation (requires ANTHROPIC_API_KEY)

Returns a structured OperationPlan only — no G-code. Use to inspect what the
agent plans before committing to G-code generation.

```json
{
  "prompt": "Drill a 5mm deep hole at X0 Y0 with a 5mm drill, safe Z 5mm, feedrate 100, spindle 1200, units mm.",
  "machine_type": "drill"
}
```

Returns `ok`, `operation_plan`, `validation`, `warnings`, `errors`, `missing_info`, `machine_type`.
If `missing_info` is non-empty, the plan is incomplete and no G-code should be generated from it.

---

### generate_gcode (requires ANTHROPIC_API_KEY)

Full pipeline: NL prompt → OperationPlan → G-code → Safety report.

```json
{
  "prompt": "Drill a 5mm deep hole at X0 Y0 with a 5mm drill, safe Z 5mm, feedrate 100, spindle 1200, units mm.",
  "machine_type": "drill"
}
```

**Notes:**
- Agent output is **never** directly treated as G-code — only structured OperationPlans are accepted.
- If `missing_info` is non-empty in the agent result, `ok=False` and `gcode=""`.
- The full pipeline runs: OperationPlan extraction → validation → postprocessor → Safety Analyzer.
- Deterministic typed tools (`generate_drill_gcode`, etc.) work without an API key and are preferred
  when all parameters are known.

---

## Safety note

The `generate_gcode` tool uses an LLM agent internally. All generated G-code:
- Is validated before being returned
- Should be reviewed by a qualified person before use
- Is never executed directly by the system
