# MCP Developer Setup

This document explains how to connect an MCP client to the GENAI4G-CODE server.

---

## Start the MCP server

```bash
python -m cnc.server
```

The server uses stdio transport (reads from stdin, writes to stdout). It will wait for MCP messages — this is expected behavior.

---

## CLI (independent of MCP)

The `cnc.cli` module provides a command-line interface that works without a running MCP server
or API key. It is useful for testing jobs, validating G-code, and listing library entries
directly from the terminal.

```bash
python -m cnc.cli validate-job examples/jobs/drill_pattern_job.json
python -m cnc.cli run-job examples/jobs/milling_pocket_job.json --gcode-out out.nc
python -m cnc.cli batch-run examples/jobs --save-artifacts
python -m cnc.cli analyze-gcode out.nc --machine-type mill --expected-units mm
python -m cnc.cli list-profiles
python -m cnc.cli list-materials --category aluminum
```

All CLI commands output JSON to stdout (exit code 0 = ok, 1 = error).
The CLI never starts a server and does not use the MCP transport.

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
| `list_available_materials` | **No** | Returns all built-in material entries (informational context only) |
| `get_material_info` | **No** | Returns a single material entry by ID |
| `search_materials` | **No** | Filters materials by category, operation type, or machinability |
| `evaluate_operation_guardrails` | **No** | Plausibility checks on an OperationPlan — returns findings without modifying the plan |
| `create_job` | **No** | Create a reproducible JSON job spec from an OperationPlan |
| `validate_job` | **No** | Validate a job spec without generating G-code |
| `generate_gcode_from_job` | **No** | Regenerate deterministic G-code from a job spec (stored G-code ignored) |
| `save_job` | **No** | Save a job spec to a local JSON file |
| `load_job` | **No** | Load a job spec from a local JSON file |
| `run_cnc_job` | **No** | Full deterministic run: validate + G-code + safety; optionally save outputs |
| `save_run` | **No** | Save a run report to a local JSON file |
| `load_run` | **No** | Load a run report from a local JSON file |
| `run_cnc_job_batch` | **No** | Run a list of JobSpec dicts as a batch |
| `run_cnc_job_batch_from_paths` | **No** | Load and run JobSpec files from a path list |
| `run_cnc_job_batch_from_directory` | **No** | Load and run all matching JSON files from a directory |
| `save_batch` | **No** | Save a batch report to a local JSON file |
| `load_batch` | **No** | Load a batch report from a local JSON file |
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
- Agent output (natural language, agent-generated gcode text) is **never** directly treated as final G-code.
- Only structured OperationPlans extracted from agent output are accepted.
- If `missing_info` is non-empty in the agent result, `ok=False` and `gcode=""`.
- The returned G-code is **always regenerated deterministically** from the OperationPlan:
  `OperationPlan → validate_operation_plan → postprocess_operations → Safety Analyzer`.
- Agent-provided `gcode` text is discarded and replaced with deterministic output.
  (LLMs may abbreviate long G-code blocks with placeholders like `... [18 rows × 4 passes]`.)
- Deterministic typed tools (`generate_drill_gcode`, etc.) work without an API key and are preferred
  when all parameters are known.

---

---

### list_available_materials (deterministic, no API key needed)

```json
{}
```

Returns the built-in material library as a list. Each entry includes `id`, `name`, `category`, `machinability`, `notes`, `warnings`, and `supported_operations`.

---

### get_material_info (deterministic, no API key needed)

```json
{
  "material_id": "aluminum_6061"
}
```

Returns the matching material entry or `{"ok": false, "material": null, "error": "..."}` if unknown.

---

### search_materials (deterministic, no API key needed)

```json
{
  "category": "aluminum"
}
```

Optional filters:
- `category`: `"aluminum"`, `"steel"`, `"stainless_steel"`, `"brass"`, `"plastic"`, `"wood"`, `"composite"`.
- `operation_type`: `"drill"`, `"pocket"`, `"facing"`, `"slot"`.
- `machinability`: `"easy"`, `"medium"`, `"hard"`.

Returns a filtered list (empty list if no match).

---

### evaluate_operation_guardrails (deterministic, no API key needed)

```json
{
  "operation_plan": {
    "machine_type": "mill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5,
    "tools": [{"id": "T1", "diameter": 5}],
    "operations": [
      {
        "type": "pocket",
        "feedrate": 150,
        "spindle_speed": 3000,
        "parameters": {
          "origin_x": 0, "origin_y": 0,
          "width": 20, "height": 10, "target_z": -3,
          "step_down": 1, "step_over": 2, "tool_diameter": 5
        }
      }
    ],
    "assumptions": [], "warnings": []
  },
  "material": "aluminum_6061"
}
```

Returns `ok`, `errors`, `warnings`, `info`, `material`, and `findings`. Each finding has `severity` (`"info"` / `"warning"` / `"error"`), `code`, `message`, and `operation_index`.

`ok=False` only when hard errors are present (e.g. missing `feedrate`, missing `safe_z`). Warnings (unknown material, stainless steel caution, `step_over > tool_diameter`) do not set `ok=False`.

**Finding codes include:** `NO_MATERIAL`, `UNKNOWN_MATERIAL`, `STAINLESS_STEEL_CAUTION`, `WOOD_SAFETY`, `PLASTIC_HEAT`, `MISSING_SAFE_Z`, `MISSING_FEEDRATE`, `MISSING_SPINDLE`, `STEP_OVER_EXCEEDS_DIAMETER`, `STEP_DOWN_EXCEEDS_DEPTH`.

---

---

### create_job (deterministic, no API key needed)

```json
{
  "operation_plan": {
    "machine_type": "drill",
    "units": "mm",
    "work_coordinate_system": "G54",
    "safe_z": 5,
    "tools": [{"id": "T1", "diameter": 5}],
    "operations": [
      {
        "type": "drill",
        "feedrate": 100,
        "spindle_speed": 1200,
        "parameters": {"x": 0, "y": 0, "z": -5}
      }
    ],
    "assumptions": [], "warnings": [], "missing_info": []
  },
  "name": "My drill job",
  "machine_profile": "generic_drill_mm",
  "material": "aluminum_6061",
  "postprocessor": "fanuc"
}
```

Returns a `CNCJobSpec`-compatible dict with `schema_version`, `job_id`, `operation_plan`, and all
context fields. Does NOT generate G-code.

---

### validate_job (deterministic, no API key needed)

```json
{
  "job": { "schema_version": "0.1", "postprocessor": "fanuc", "operation_plan": { ... } }
}
```

Runs structural checks, machine_type consistency, profile/material/tool_id lookups,
`validate_operation_plan`, and `evaluate_parameter_guardrails`.

Returns `ok`, `errors`, `warnings`, `job`, `operation_plan_validation`, `guardrails`.

---

### generate_gcode_from_job (deterministic, no API key needed)

```json
{
  "job": { "schema_version": "0.1", "postprocessor": "fanuc", "operation_plan": { ... } }
}
```

**Notes:**
- Any stored `gcode` field in the job is **ignored** — a warning is added.
- G-code is always regenerated from `operation_plan` via the postprocessor pipeline.
- Returns `ok`, `gcode`, `job`, `validation`, `warnings`, `errors`, `postprocessor`, `safety_report`.
- The `operation_plan` is the truth. Stored G-code is never the truth.

---

### save_job (deterministic, no API key needed)

```json
{
  "job": { "schema_version": "0.1", "postprocessor": "fanuc", "operation_plan": { ... } },
  "path": "examples/jobs/my_job.json"
}
```

**Notes:**
- Path is resolved relative to the server's working directory (or as an absolute path).
- File is written as UTF-8 JSON with 2-space indentation.
- Do NOT store secrets (API keys, passwords) in job specs.
- Returns `{"ok": bool, "path": str, "errors": list, "warnings": list}`.

---

### load_job (deterministic, no API key needed)

```json
{
  "path": "examples/jobs/drill_pattern_job.json"
}
```

**Notes:**
- Path is resolved relative to the server's working directory (or as an absolute path).
- Returns `{"ok": bool, "job": dict | null, "path": str, "errors": list, "warnings": list}`.
- If the file contains a `gcode` field a warning is added; use `generate_gcode_from_job` to regenerate.

---

---

### run_cnc_job (deterministic, no API key needed)

```json
{
  "job": {
    "schema_version": "0.1",
    "postprocessor": "fanuc",
    "material": "aluminum_6061",
    "operation_plan": {
      "machine_type": "drill",
      "units": "mm",
      "work_coordinate_system": "G54",
      "safe_z": 5,
      "tools": [{"id": "T1", "diameter": 5}],
      "operations": [
        {
          "type": "drill",
          "feedrate": 100,
          "spindle_speed": 1200,
          "parameters": {"x": 0, "y": 0, "z": -5}
        }
      ],
      "assumptions": [], "warnings": [], "missing_info": []
    }
  },
  "save_gcode_path": "outputs/gcode/my_job.nc",
  "save_report_path": "outputs/runs/my_run.json"
}
```

**Notes:**
- `save_gcode_path` and `save_report_path` are optional. Omit to skip file output.
- Any stored `gcode` field in the job is **ignored** — a warning is added.
- G-code is always regenerated from `operation_plan`.
- Returns `ok`, `run_report`, `gcode`, `warnings`, `errors`, `artifacts`.
- `run_report.status`: `"ok"` / `"warning"` / `"failed"`.
- `run_report` includes `operation_plan_validation`, `guardrails`, `safety_report`, `artifacts`.

---

### save_run (deterministic, no API key needed)

```json
{
  "run_report": { "schema_version": "0.1", "run_id": "run_...", "status": "ok", ... },
  "path": "outputs/runs/my_run.json"
}
```

Returns `{"ok": bool, "path": str, "errors": list, "warnings": list}`.

---

### load_run (deterministic, no API key needed)

```json
{
  "path": "outputs/runs/my_run.json"
}
```

Returns `{"ok": bool, "run_report": dict | null, "path": str, "errors": list, "warnings": list}`.

---

---

### run_cnc_job_batch (deterministic, no API key needed)

```json
{
  "jobs": [
    { "schema_version": "0.1", "postprocessor": "fanuc", "operation_plan": { ... } },
    { "schema_version": "0.1", "postprocessor": "grbl",  "operation_plan": { ... } }
  ],
  "output_dir": "outputs/batches/my_batch",
  "save_artifacts": true,
  "batch_name": "my_batch"
}
```

Returns `{"ok": bool, "batch_report": dict, "warnings": list, "errors": list}`.

---

### run_cnc_job_batch_from_paths (deterministic, no API key needed)

```json
{
  "paths": [
    "examples/jobs/drill_pattern_job.json",
    "examples/jobs/milling_pocket_job.json"
  ],
  "output_dir": "outputs/batches/my_batch",
  "save_artifacts": true
}
```

Files that cannot be loaded appear in the batch results with `status: "failed"`.

---

### run_cnc_job_batch_from_directory (deterministic, no API key needed)

```json
{
  "directory": "examples/jobs",
  "pattern": "*.json",
  "output_dir": "outputs/batches/my_batch",
  "save_artifacts": true
}
```

**Notes:**
- Files are sorted stably before processing.
- `pattern` defaults to `"*.json"`.
- Returns an error if the directory does not exist or contains no matching files.

---

### save_batch / load_batch (deterministic, no API key needed)

```json
{ "batch_report": { ... }, "path": "outputs/batches/my_batch.json" }
```

```json
{ "path": "outputs/batches/my_batch.json" }
```

---

## Batch Jobs — important notes

- Paths are **local server paths**.
- Each job is processed independently — one failed job does not stop the rest.
- Batch reports are **traceability artefacts** — not safety releases.
- `status` values: `"ok"` / `"warning"` / `"mixed"` / `"failed"`.
- No automatic approval for real machines. Expert review and simulation are always required.

---

## Job Runs — important notes

- Paths in `run_cnc_job`, `save_run`, and `load_run` are **local server paths**.
- Do **not** store secrets in run reports.
- Run reports are **traceability artefacts** — they document what happened during one run.
  They are **not** safety releases or G-code approval records.
- No automatic approval for real machines. Expert review and simulation are always required
  before using any generated G-code on physical equipment.

---

## Job Import/Export — important notes

- Paths in `save_job` / `load_job` are **local server paths** — they must be accessible to the process running `cnc.server`.
- Do **not** store secrets (API keys, credentials, passwords) in job spec files.
- A stored `gcode` field in a job spec is **not the truth** — `operation_plan` is the truth.
  Use `generate_gcode_from_job` to always get deterministic, up-to-date G-code.
- Example job files are in `examples/jobs/`.

---

## Material Library — important notes

- The Material Library is **informational context only**. It provides notes and warnings about materials but does **not** derive or recommend feedrates, spindle speeds, or cutting depths.
- Feedrates and spindle speeds must always be supplied explicitly by the user or operator.
- The Material Library does **not** replace a cutting database or manufacturer specifications.
- **No automatic approval for real machines.** Expert review and simulation remain mandatory before any G-code is used on physical equipment.

---

## Tool Library — MCP tool examples

### `list_available_tools` — list all built-in tools

```json
{
  "tool": "list_available_tools",
  "arguments": {}
}
```

Returns a list of tool dicts. Each entry includes `id`, `name`, `tool_type`, `diameter`, `units`,
`flute_count`, `material`, `supported_machine_types`, `supported_operations`, and `notes`.

### `get_tool_info` — get metadata for a single tool

```json
{
  "tool": "get_tool_info",
  "arguments": {
    "tool_id": "drill_5mm"
  }
}
```

Returns `{"ok": true, "tool": {...}, "errors": [], "warnings": []}` or
`{"ok": false, "tool": null, "errors": ["Tool 'x' not found..."]}` if not recognised.

### `search_tools` — filter tools by capability

```json
{
  "tool": "search_tools",
  "arguments": {
    "machine_type": "mill",
    "operation_type": "pocket"
  }
}
```

All filter arguments are optional and AND-combined. Available filters:
- `machine_type` — e.g. `"drill"`, `"mill"`
- `operation_type` — e.g. `"drill"`, `"facing"`, `"pocket"`, `"slot"`
- `tool_type` — `"drill"`, `"end_mill"`, `"engraver"`, `"laser"`
- `units` — `"mm"` or `"inch"`

Returns `{"ok": true, "tools": [...], "count": N, "errors": [], "warnings": []}`.

### `resolve_tool` — validate a tool_id against the registry

```json
{
  "tool": "resolve_tool",
  "arguments": {
    "tool_id": "drill_5mm",
    "machine_type": "drill",
    "operation_type": "drill"
  }
}
```

Returns `{"ok": true, "tool": {...}, "warnings": [], "errors": []}`.
Unknown tool_ids (e.g. `"T1"`) always return `ok: true` with a warning — they are never errors.

### `resolve_plan_tools` — validate all tool references in an OperationPlan

```json
{
  "tool": "resolve_plan_tools",
  "arguments": {
    "operation_plan": {
      "machine_type": "drill",
      "units": "mm",
      "safe_z": 5.0,
      "tools": [{"id": "drill_5mm", "diameter": 5.0}],
      "operations": [
        {"type": "drill", "tool_id": "drill_5mm",
         "feedrate": 150, "parameters": {"x": 10, "y": 20, "z": -5}}
      ]
    }
  }
}
```

Returns `{"ok": bool, "warnings": [...], "errors": [...], "resolved": [...]}`.
`resolved` contains full library metadata for each known tool found in the plan.

---

## Tool Library — important notes

- The Tool Library provides **dimensional and capability metadata only** — no cutting data.
- Cutting parameters (feedrate, spindle speed, depth of cut) are always **job-specific** and must be supplied explicitly.
- **Unknown `tool_id`s produce warnings, not errors.** Plans using machine-internal IDs like `"T1"` are valid and common.
- **Known tools used for unsupported operations produce errors** during `validate_operation_plan`.
- Machine profiles (`list_machine_profiles`) include a `default_tool_ids` list indicating which tools are commonly available on that machine.

---

## Safety note

The `generate_gcode` tool uses an LLM agent internally. All generated G-code:
- Is validated before being returned
- Should be reviewed by a qualified person before use
- Is never executed directly by the system
