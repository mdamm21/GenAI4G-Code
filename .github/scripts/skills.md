# Skills

This file documents the available skills (tools/capabilities) exposed by this MCP server.

## Overview

The GenAI4G MCP server provides the following skills that Claude can invoke during agentic sessions.

---

## Available Skills

### `echo`

**Description:** Returns the input text unchanged. Useful for testing connectivity.

**Input:**
- `text` (string, required) — The text to echo back.

**Output:** The same text string.

---

### `get_system_info`

**Description:** Returns basic information about the runtime environment.

**Input:** None.

**Output:** JSON object with `platform`, `python_version`, and `cwd` fields.

---

### `read_file`

**Description:** Reads the contents of a file relative to the project root.

**Input:**
- `path` (string, required) — Relative path to the file.

**Output:** File contents as a string.

---

### `list_directory`

**Description:** Lists files and directories at a given path.

**Input:**
- `path` (string, optional, default `"."`) — Relative path to list.

**Output:** Newline-separated list of entries.

---

## Adding New Skills

1. Define a new tool function in `src/genai4g/server.py` using the `@mcp.tool()` decorator.
2. Add its documentation to this file under **Available Skills**.
3. Restart the MCP server for the change to take effect.

## Usage

The MCP server is started automatically when Claude Code loads this project, or manually via:

```bash
python src/genai4g/server.py
```

Claude can then call any skill by name during a conversation.
