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

| Tool | Description |
|---|---|
| `list_supported_machines` | Returns supported machine type identifiers |
| `validate_gcode` | Static safety check on a G-code program |
| `validate_plan` | Structural validation of an OperationPlan dict |
| `postprocess_plan` | Convert an OperationPlan to G-code (deterministic) |
| `generate_gcode` | Full agentic pipeline: prompt → G-code (requires API key) |

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

## Safety note

The `generate_gcode` tool uses an LLM agent internally. All generated G-code:
- Is validated before being returned
- Should be reviewed by a qualified person before use
- Is never executed directly by the system
