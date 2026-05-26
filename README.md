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
