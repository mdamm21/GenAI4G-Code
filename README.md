# GENAI4G-CODE

CNC G-code generation pipeline using Claude AI, MCP (Model Context Protocol), and a multi-agent architecture.

---

## Architecture

```
User Prompt
    │
    ▼
cnc/server.py          ← MCP outer API (FastMCP tools)
    │
    ▼
cnc/agent.py           ← CNC Supervisor Agent (Anthropic tool-use loop)
    │
    ├─ delegate_to_subagent
    │       │
    │       ├─ cnc/subagents/drilling.py   → OperationPlan
    │       ├─ cnc/subagents/milling.py    → OperationPlan
    │       └─ cnc/subagents/laser.py      → OperationPlan
    │
    ├─ validate_operation_plan (cnc/tools/validation_tools.py)
    ├─ postprocess_operations  (cnc/postprocessors/fanuc|grbl|marlin|linuxcnc.py)
    └─ validate_gcode_text     (cnc/validators/gcode_validator.py)
```

**Key design principles:**

- MCP server is the **outer API only** — no CNC logic lives there.
- Subagents produce **structured OperationPlans** — never raw G-code.
- Postprocessors perform **deterministic, schema-driven** G-code generation.
- Validators run on both plans and G-code before any output is returned.
- Missing critical parameters produce `missing_info` / `warnings` — never silent fabrication.

---

## Current MVP: Drill Pipeline

The deterministic drill pipeline is fully implemented and testable **without an LLM or API key**:

1. `normalize_operation_plan` — maps agent field names to canonical schema
2. `validate_operation_plan` — drill-specific error checks (x/y/z/feedrate required)
3. `postprocess_operations` — Fanuc-compatible G-code with safety guards
4. `validate_gcode_text` — static G-code safety analysis

Supported postprocessors: `fanuc`, `grbl`, `marlin`, `linuxcnc`

Supported machine types: `mill`, `drill`, `laser`, `lathe` (stub), `grinder` (stub), `3d_printer` (stub)

---

## Install

```bash
pip install -r requirements.txt
```

Requires Python >= 3.11.

For LLM-backed agent features, set your API key:

```bash
# .env (copy from .env.example, never commit real keys)
ANTHROPIC_API_KEY=your-key-here
```

---

## Typed Drill MCP Tool

`generate_drill_gcode` is the safe, deterministic MVP path — no LLM, no API key.

It accepts explicit machining parameters, builds a structured OperationPlan,
validates the plan, runs the postprocessor, and validates the G-code output.

**Example parameters (MCP Inspector / Claude Desktop):**

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

**Run the typed tool demo:**

```bash
python scripts/demo_drill_mcp_tool.py
```

Compared to `generate_gcode(prompt=...)`:

| | `generate_drill_gcode` | `generate_gcode` |
|---|---|---|
| LLM required | No | Yes (ANTHROPIC_API_KEY) |
| Input | Explicit typed parameters | Natural language prompt |
| Deterministic | Yes | No |
| Safe for automation | Yes | Review required |

---

## Milling Facing MVP

The `generate_milling_facing_gcode` MCP tool generates conservative facing
(surface milling) G-code for a **rectangular area** without an LLM or API key.

**Example parameters (MCP Inspector / Claude Desktop):**

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

- Generates alternating parallel passes along X, stepping Y by `step_over`.
- `depth` is a positive number (e.g. `1` → cuts to Z=-1).
- **No cutter compensation** (G41/G42) is applied automatically.
- **No tool radius offset** is calculated — program the centerline.
- Not a full CAM system — complex geometries require dedicated CAM software.
- All output must be reviewed and simulated before use on a real machine.

**Run the milling facing demo:**

```bash
python scripts/demo_milling_facing_mvp.py
```

---

## Milling Pocket MVP

The `generate_milling_pocket_gcode` MCP tool generates conservative rectangular
pocket G-code without an LLM or API key.

**Example parameters (MCP Inspector / Claude Desktop):**

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

- `step_down`: Z increment per pass (required, > 0). Multiple Z passes until `depth` reached.
- `step_over`: Radial step-over per raster row (required, > 0). Values > `tool_diameter` warn about uncut material.
- `depth` is a positive number (e.g. `3` → final cut at Z=-3). Negative values normalised with warning.
- Simple raster clearing strategy — parallel rows along X, stepping Y by `step_over`.
- **No cutter compensation** (G41/G42) is applied automatically.
- **No helix-ramping, trochoidal toolpaths, or adaptive clearing.**
- Not a full CAM system — review and simulate before use on a real machine.

**Run the milling pocket demo:**

```bash
python -m scripts.demo_milling_pocket_mvp
```

---

## Milling Slot MVP

The `generate_milling_slot_gcode` MCP tool generates conservative straight-slot
G-code along X or Y without an LLM or API key.

**Example parameters (MCP Inspector / Claude Desktop):**

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

- `direction`: `"x"` or `"y"` — axis along which the slot is cut.
- `step_down`: Z increment per pass (positive, in mm). Multiple passes if `depth > step_down`.
- `depth` is a positive number (e.g. `3` → final cut at Z=-3). Negative values normalised with warning.
- Slot width equals tool diameter — no cutter compensation, no roughing/finishing strategy.
- **No cutter compensation** (G41/G42) is applied automatically.
- Not a full CAM system — review and simulate before use on a real machine.

**Run the milling slot demo:**

```bash
python scripts/demo_milling_slot_mvp.py
```

---

## Multi-Hole Drill Pattern MVP

The `generate_drill_pattern_gcode` MCP tool generates conservative drilling
G-code for **multiple explicit hole positions** without an LLM or API key.

**Example parameters (MCP Inspector / Claude Desktop):**

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

- Each `hole` specifies `x`, `y`, and `depth` (positive number, e.g. `5` → Z=-5).
- `machine_profile` is optional — it provides defaults for `safe_z`, `units`, and WCS.
- `feedrate` and `spindle_speed` are never invented — missing values produce errors.
- Spindle starts once (not before every hole) if the speed stays constant.
- All output is validated before being returned.

**Run the multi-hole demo:**

```bash
python scripts/demo_drill_pattern_mvp.py
```

### Machine Profiles

Machine profiles supply safe defaults for known machine configurations.
Available profiles can be listed with the `list_profiles` MCP tool.

| Profile | machine_type | units | default_safe_z | default_feedrate | default_spindle |
|---|---|---|---|---|---|
| `generic_drill_mm` | drill | mm | 5.0 | (per job) | (per job) |
| `generic_drill_inch` | drill | inch | 0.2 | (per job) | (per job) |

> Profiles are defaults, not safety guarantees. Feedrate and spindle speed must
> always be verified before running on a real machine.

---

## Postprocessor Dialects v0

All postprocessors are conservative MVP implementations. No machine-specific guarantees.
Simulation and expert review are required before running on a real machine.

| Postprocessor | Status | Supported MVP operations |
|---|---|---|
| `fanuc` | MVP | drill, facing, slot, pocket |
| `grbl` | MVP | drill, facing, slot, pocket |
| `linuxcnc` | MVP | drill, facing, slot, pocket |
| `marlin` | stub | 3d_printer: not implemented yet |

**Fanuc** — Reference postprocessor. Includes `%` tape delimiters, `O0001` program number, `G17 G40 G49 G80` safety cancel, `T## M06` tool change, `M30` program end.

**GRBL** — Hobbyist/open-source CNC firmware. No `%`, no tool changer, no canned cycles. End sequence: `M5`, `G0 Zsafe`, `M2`.

**LinuxCNC** — Conservative RS274NGC output. No `%`, no o-words, no cutter compensation. Header includes `(Conservative LinuxCNC-style postprocessor)`. End sequence: `M5`, `G0 Zsafe`, `M2`.

**Marlin** — Stub only. Marlin is a laser/3D-printer firmware. CNC milling and drilling operations always return `ok: False`. 3D printing support is not implemented — use a slicer instead.

**Machine profiles for GRBL and LinuxCNC:**

| Profile | machine_type | units | default_postprocessor |
|---|---|---|---|
| `generic_drill_grbl_mm` | drill | mm | grbl |
| `generic_mill_grbl_mm` | mill | mm | grbl |
| `generic_drill_linuxcnc_mm` | drill | mm | linuxcnc |
| `generic_mill_linuxcnc_mm` | mill | mm | linuxcnc |

**Dialects demo (no API key needed):**

```bash
python -m scripts.demo_postprocessor_dialects
```

---

## Natural-Language Planning v1

The `plan_operation` and `generate_gcode` MCP tools use a CNC DeepAgent to
parse natural language and produce structured G-code — but with strict architectural
safeguards.

**Architecture:**
```
User Prompt
    │
    ▼
CNC DeepAgent          ← Produces only OperationPlan JSON (never raw G-code)
    │
    ▼
extract_operation_plan ← Rejects freeform text / unstructured agent output
    │
    ▼
normalize_operation_plan ← Fills safe defaults, preserves missing_info
    │
    ▼
validate_operation_plan  ← Structural + safety checks
    │
    ▼
postprocess_operations   ← Deterministic G-code generation (fanuc/grbl/linuxcnc)
    │
    ▼
Safety Analyzer          ← Static G-code safety analysis + risk level
```

**Safety guarantees:**
- Agent text is **never** treated as final G-code.
- `missing_info` blocks G-code generation — no silent fabrication of critical params.
- Every OperationPlan is validated before postprocessing.
- Every generated G-code is analyzed by the Safety Analyzer.

**`plan_operation(prompt, machine_type)` — returns OperationPlan only:**

```json
{
  "prompt": "Drill a 5mm hole at X0 Y0, depth 5mm, 5mm drill, safe Z 5, feedrate 100, spindle 1200, units mm.",
  "machine_type": "drill"
}
```

Returns `ok`, `operation_plan`, `validation`, `missing_info` — **no G-code**.

**`generate_gcode(prompt, machine_type)` — full pipeline:**

Same input as `plan_operation`, but additionally runs the postprocessor and
safety analyzer. Returns `ok`, `gcode`, `operation_plan`, `safety_report`, `missing_info`.

If `missing_info` is non-empty, `ok=False` and `gcode=""`.

**Supported MVP operations:**
- Drill single hole
- Drill multi-hole pattern
- Milling facing (rectangular surface milling)
- Milling straight slot (along X or Y)
- Milling rectangular pocket

Requires `ANTHROPIC_API_KEY`. All other deterministic tools work without it.

**Demo (requires API key):**

```bash
python -m scripts.demo_nl_planning_optional
```

**Demo without API key (normalization only):**

```bash
python -m scripts.demo_agent_result_normalization
```

---

## G-Code Safety Analyzer v1

The `analyze_gcode_safety_report` MCP tool performs **structured static analysis** of any
G-code program and returns a risk-scored safety report — no LLM or API key required.

It does **not** simulate machine motion and does **not** replace expert review or CAM simulation.
All results are advisory only.

**What it checks:**

- Unit declaration (G20/G21) — missing, mixed, or mismatched vs expected
- Positioning mode (G90/G91) — missing or unexpected relative mode
- Work coordinate system (G54–G59) — missing
- Feedrate — missing or zero/negative
- Program end (M30/M2) — missing
- Rapid move to negative Z (G00 Z<negative>) — **error** (dangerous plunge)
- Spindle start/stop (M03/M04/M05) — missing, unmatched, or no speed
- Machine-type specific: hotend temp (3D printer), laser enable (laser)
- Exceeded `max_depth` — error if program cuts deeper than configured limit
- Disallowed commands — error if `allowed_commands` whitelist is set
- Unsupported G/M codes — warning

**Risk levels:** `low` (no issues) / `medium` (warnings only) / `high` (one or more errors)

**Example parameters (MCP Inspector / Claude Desktop):**

```json
{
  "gcode": "G21\nG90\nG54\nG0 Z5\nS1200 M03\nG01 Z-5 F100\nG0 Z5\nM05\nM30",
  "machine_type": "drill",
  "expected_units": "mm",
  "safe_z": 5.0,
  "max_depth": 10.0
}
```

**Run the safety analyzer demo:**

```bash
python scripts/demo_safety_analyzer.py
```

---

## Material Library v0 and Parameter Guardrails

The material library provides **informational context** about workpiece materials. It is NOT a cutting data database — feedrate, spindle speed, step_down, and step_over must always be supplied explicitly.

### Material Library

| ID | Name | Category | Machinability |
|---|---|---|---|
| `aluminum_6061` | Aluminum 6061 | aluminum | easy |
| `aluminum_generic` | Aluminum (generic) | aluminum | easy |
| `mild_steel` | Mild steel | steel | medium |
| `stainless_steel_generic` | Generic stainless steel | stainless_steel | hard |
| `acrylic` | Acrylic | plastic | medium |
| `plywood` | Plywood | wood | easy |
| `brass_generic` | Brass (generic) | brass | easy |

Each material entry contains: `notes` (informational), `warnings` (cautions), `supported_operations`.

### Parameter Guardrails

`evaluate_parameter_guardrails(operation_plan, material)` checks for:

- Missing material → warning
- Unknown material → warning
- Stainless steel → `"Stainless steel requires conservative, verified cutting parameters."`
- Wood → `"Wood machining may require dust extraction and fire-risk controls."`
- Plastic → `"Plastic machining may require chip evacuation and heat control."`
- Unsupported operation for material → warning
- Missing feedrate → error
- Missing spindle_speed → warning
- Missing safe_z → error
- step_over > tool_diameter → warning (may leave uncut material)
- step_down > total depth → warning

Guardrails **never** modify the plan and **never** derive cutting parameters.

### New MCP Tools

| Tool | Description |
|---|---|
| `list_available_materials` | List all built-in material library entries |
| `get_material_info(material_id)` | Get one material entry by ID |
| `search_materials(category, operation_type, machinability)` | Filter materials |
| `evaluate_operation_guardrails(operation_plan, material)` | Run guardrail checks |

### Material integration

When `material` is passed to deterministic tools (`generate_drill_gcode`, `generate_milling_pocket_gcode`, etc.), it is stored in `operation_plan["material"]` and validated by `validate_operation_plan` (missing material adds a warning). The `evaluate_operation_guardrails` tool can then be called for deeper context checks.

**Demo (no API key required):**

```bash
python -m scripts.demo_material_guardrails
```

---

## Deterministic G-code Regeneration

A fundamental safety principle in GENAI4G-CODE: **agent-generated G-code text is never
trusted as final output.**

LLMs may abbreviate long G-code blocks in their JSON responses, e.g.:

```
"gcode": "G21\n... [18 rows × 4 passes]\nM30"
```

Such output is silently incomplete and would be dangerous on a real machine.

### How it works

Whenever an `OperationPlan` is present in an agent result, the pipeline always
discards the agent's `gcode` field and regenerates G-code deterministically:

```
OperationPlan
    │
    ▼
validate_operation_plan    ← structural + safety checks
    │
    ▼
postprocess_operations     ← deterministic, schema-driven G-code
    │
    ▼
validate_gcode_text        ← static safety analysis + risk level
```

This is implemented in `cnc/tools/gcode_pipeline.py` via `regenerate_gcode_from_operation_plan()`.

### Guarantees

- Agent `gcode` text is discarded whenever `operation_plan` is present.
- A warning is added to the result: `"Agent-provided gcode was discarded and regenerated deterministically from operation_plan."`
- Invalid `OperationPlan` → `gcode=""` and validation errors (old agent G-code is NOT kept).
- `operation_plan` returned as a list → first item is used with a warning.
- Postprocessor selection order: `result["postprocessor"]` → `operation_plan["postprocessor"]` → `default_postprocessor`.
- The same pipeline is used in both `CNCAgent.run()` and the MCP `generate_gcode` tool.

### Demo (no API key required)

```bash
python scripts/demo_deterministic_regeneration.py
```

---

## JSON JobSpec Import/Export v0

CNC jobs can be saved to and loaded from JSON files using the **CNCJobSpec** format. A job spec is a
reproducible container that bundles everything needed to regenerate G-code deterministically.

### What a JobSpec contains

| Field | Purpose |
|---|---|
| `schema_version` | Format version (`"0.1"`) |
| `job_id` | Auto-generated UUID |
| `name` / `description` | Human-readable labels |
| `machine_type` | `"mill"` / `"drill"` / ... |
| `machine_profile` | Profile name (e.g. `"generic_mill_mm"`) |
| `material` | Material name or library ID (e.g. `"aluminum_6061"`) |
| `tool_ids` | Tool references |
| `postprocessor` | `"fanuc"` / `"grbl"` / `"linuxcnc"` |
| `operation_plan` | The technical truth — OperationPlan dict |
| `metadata` | Arbitrary key-value context |
| `assumptions` / `warnings` / `missing_info` | Propagated from OperationPlan |

### G-code is never stored

**`gcode` fields are not stored in a job spec.** G-code is always regenerated deterministically
from `operation_plan` via the postprocessor pipeline. If a loaded job contains a `gcode` field
it is ignored and a warning is returned.

### Python API

```python
from cnc.tools.job_io import create_job_spec, validate_job_spec, job_spec_to_gcode
from cnc.tools.job_io import save_job_spec, load_job_spec

# Create a job spec from an OperationPlan
job = create_job_spec(operation_plan, material="aluminum_6061", postprocessor="fanuc")

# Save and reload
save_job_spec(job, "examples/jobs/my_job.json")
loaded = load_job_spec("examples/jobs/my_job.json")

# Validate
val = validate_job_spec(loaded["job"])

# Regenerate G-code
result = job_spec_to_gcode(loaded["job"])
print(result["gcode"])
```

### New MCP tools

| Tool | Description |
|---|---|
| `create_job` | Create a job spec from an OperationPlan |
| `validate_job` | Validate a job spec without generating G-code |
| `generate_gcode_from_job` | Regenerate G-code from a job spec (stored G-code ignored) |
| `save_job` | Save a job spec to a local JSON file |
| `load_job` | Load a job spec from a local JSON file |

### Example job files

```
examples/jobs/drill_pattern_job.json    — 3-hole drill pattern, Al6061
examples/jobs/milling_pocket_job.json  — 20x10x3 mm pocket, Al6061
```

### Demo (no API key required)

```bash
python -m scripts.demo_job_io
```

---

## Job Runs and Reports v0

A **run** is one concrete processing of a CNCJobSpec through the full deterministic pipeline.
The resulting **run report** documents everything that happened for traceability.

### What a run does

```
CNCJobSpec
    │
    ▼
validate_job_spec        ← structural checks, guardrails, material, profile
    │
    ▼
job_spec_to_gcode        ← deterministic postprocessor pipeline
    │
    ▼
CNCRunReport             ← bundles all results + G-code + artifacts
```

### Run Report structure

| Field | Description |
|---|---|
| `schema_version` | `"0.1"` |
| `run_id` | Auto-generated `run_<uuid4>` |
| `created_at` | UTC ISO 8601 timestamp |
| `status` | `"ok"` / `"warning"` / `"failed"` |
| `job` | Input CNCJobSpec |
| `postprocessor` | Dialect used |
| `operation_plan_validation` | Result of `validate_operation_plan` |
| `guardrails` | Result of `evaluate_parameter_guardrails` |
| `postprocess_result` | OperationPlan validation from postprocessor |
| `safety_report` | G-code static safety analysis |
| `gcode` | Final deterministic G-code (empty if `status == "failed"`) |
| `warnings` / `errors` | Aggregated from all pipeline stages |
| `artifacts` | Files saved during the run (G-code, report) |

### Key properties

- **No LLM.** `run_job` calls no external API.
- **Stored G-code ignored.** Any `gcode` field in the job is discarded; a warning is added.
- **Run reports are traceability artefacts** — not safety releases or G-code authorities.
- G-code and run report can optionally be saved to files.

### Python API

```python
from cnc.tools.job_runs import run_job, save_run_report, load_run_report

result = run_job(
    job,
    save_gcode_path="outputs/gcode/my_job.nc",
    save_report_path="outputs/runs/my_run.json",
)
print(result["run_report"]["status"])   # "ok" / "warning" / "failed"
print(result["gcode"][:200])
```

### New MCP tools

| Tool | Description |
|---|---|
| `run_cnc_job` | Run a JobSpec through the full pipeline; optionally save G-code + report |
| `save_run` | Save a run report dict to a local JSON file |
| `load_run` | Load a run report dict from a local JSON file |

### Demo (no API key required)

```bash
python -m scripts.demo_job_run_report
```

---

## Run tests

```bash
pytest
```

All deterministic tests run **without** an API key. LLM-dependent paths are not triggered by the test suite.

---

## Run deterministic demo (no API key needed)

```bash
python scripts/demo_drill_mvp.py
```

Demonstrates the full drill pipeline: normalize → validate → postprocess → G-code output.

---

## Run the full pipeline test

```bash
python scripts/test_drill_pipeline.py
```

---

## Run the MCP server

```bash
python -m cnc.server
```

The server speaks the MCP stdio protocol. Use with an MCP client or the MCP Inspector.

See [docs/mcp_setup.md](docs/mcp_setup.md) for Claude Desktop and Inspector configuration.

---

## Run the local agent test client (requires API key)

```bash
python agent.py
# or with a custom prompt:
python agent.py "Drill a 5mm hole at X10 Y20 to a depth of 15mm in aluminium"
```

---

## Project structure

```
GenAI4G-Code/
├── agent.py                    # Local test client (not for production)
├── requirements.txt
├── pyproject.toml
├── cnc/
│   ├── server.py               # MCP server (outer API)
│   ├── agent.py                # CNC Supervisor Agent (orchestrator)
│   ├── subagents/              # Machine-specific planning agents
│   ├── tools/                  # Validation, postprocessing, normalization
│   ├── validators/             # Static G-code safety checks
│   ├── postprocessors/         # Fanuc, GRBL, Marlin, LinuxCNC
│   └── schemas/                # Pydantic data models
├── scripts/
│   ├── demo_drill_mvp.py       # Deterministic demo (no LLM needed)
│   └── test_drill_pipeline.py  # End-to-end pipeline test
├── tests/                      # pytest test suite
└── docs/
    └── mcp_setup.md            # MCP Inspector & Claude Desktop setup
```

---

## Safety note

> **Generated G-code is for review and simulation only.**
>
> Never run generated G-code on a real CNC machine without:
> - Expert review by a qualified machinist or CNC programmer
> - Simulation in CAM software or a G-code simulator
> - Machine-specific setup validation (tool offsets, work offsets, feeds/speeds)
> - Appropriate safety checks and limit verification
>
> The system deliberately refuses to silently invent critical machining parameters.
> Missing information is reported as `missing_info` or `warnings` rather than
> substituted with potentially unsafe defaults.
