"""CNC DeepAgent — internal orchestrator for the G-code generation pipeline.

Architecture:
    MCP Server (outer) -> CNCAgent (supervisor loop)
                       -> delegate_to_subagent (machine-specific LLM call)
                       -> validate_operation_plan (tool)
                       -> postprocess_operations (tool)
                       -> validate_gcode_output (tool)

The CNCAgent uses the Anthropic Messages API with native tool use.
The supervisor runs a multi-turn loop: it calls tools, inspects results,
and produces a final structured JSON result.

Fallback: if anthropic is not importable, _FallbackCNCAgent is used — single
LLM call, same output contract, no tool-use loop.

Usage:
    from cnc.agent import build_cnc_agent
    agent = build_cnc_agent()
    result = agent.run("Mill a 50x50mm pocket 10mm deep in aluminium")
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from cnc.subagents.milling import MILLING_AGENT
from cnc.subagents.drilling import DRILLING_AGENT
from cnc.subagents.laser import LASER_AGENT
from cnc.subagents.turning import TURNING_AGENT
from cnc.subagents.grinding import GRINDING_AGENT
from cnc.subagents.printing import PRINTING_AGENT
from cnc.tools.postprocess_tools import postprocess_operations
from cnc.tools.validation_tools import validate_operation_plan
from cnc.validators.gcode_validator import validate_gcode_text

# ---------------------------------------------------------------------------
# Subagent registry
# ---------------------------------------------------------------------------

_SUBAGENTS: dict[str, dict] = {
    "mill": MILLING_AGENT,
    "drill": DRILLING_AGENT,
    "laser": LASER_AGENT,
    "lathe": TURNING_AGENT,
    "grinder": GRINDING_AGENT,
    "3d_printer": PRINTING_AGENT,
}

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

CNC_SUPERVISOR_PROMPT = """\
You are the CNC Supervisor Agent.

Your job is to orchestrate CNC G-code generation safely and correctly.

## Workflow — follow this exactly
1. Parse the user request: identify machine_type, units, material, dimensions, description.
2. Call delegate_to_subagent with the appropriate machine_type and a job_spec dict.
3. The subagent returns an OperationPlan. Call validate_operation_plan with it.
4. If validation passes (no errors), call postprocess_operations to generate G-code.
5. Call validate_gcode_output with the generated G-code and machine_type.
6. Return a final JSON result.

## Supported machines
- mill       → milling_agent
- drill      → drilling_agent
- laser      → laser_agent
- lathe      → turning_agent
- grinder    → grinding_agent
- 3d_printer → printing_agent

## Safety rules
- Never output G-code without running validate_gcode_output first.
- Never invent missing critical parameters (material, feedrate, tool) silently.
- If critical data is missing, return missing_info instead of unsafe G-code.
- Always include assumptions and warnings in the final result.

## Final response format
After all tool calls are done, return ONLY a JSON object with these keys:
{
  "gcode": "<final G-code string or empty string>",
  "operation_plan": <dict or null>,
  "assumptions": ["..."],
  "warnings": ["..."],
  "missing_info": ["..."],
  "validation": {"ok": bool, "errors": [...], "warnings": [...]},
  "machine_type": "<string or null>"
}
Do not add any text outside the JSON object.
"""

# ---------------------------------------------------------------------------
# Anthropic tool schemas
# ---------------------------------------------------------------------------

_TOOLS: list[dict] = [
    {
        "name": "delegate_to_subagent",
        "description": (
            "Delegate machine-specific operation planning to a specialised subagent. "
            "The subagent returns a structured OperationPlan (JSON dict). "
            "Use this BEFORE calling validate_operation_plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "machine_type": {
                    "type": "string",
                    "enum": ["mill", "drill", "laser", "lathe", "grinder", "3d_printer"],
                    "description": "The machine type to delegate to.",
                },
                "job_spec": {
                    "type": "object",
                    "description": (
                        "Partial JobSpec dict: machine_type, units, material, "
                        "raw_stock, description, assumptions, missing_info."
                    ),
                },
            },
            "required": ["machine_type", "job_spec"],
        },
    },
    {
        "name": "validate_operation_plan",
        "description": (
            "Validate a structured OperationPlan for completeness and safety. "
            "Returns {ok, errors, warnings}. "
            "Call this after delegate_to_subagent returns a plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation_plan": {
                    "type": "object",
                    "description": "The OperationPlan dict to validate.",
                },
            },
            "required": ["operation_plan"],
        },
    },
    {
        "name": "postprocess_operations",
        "description": (
            "Convert a validated OperationPlan to G-code using a named postprocessor. "
            "Only call this if validate_operation_plan returned no errors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation_plan": {
                    "type": "object",
                    "description": "The validated OperationPlan dict.",
                },
                "postprocessor": {
                    "type": "string",
                    "enum": ["fanuc", "grbl", "marlin", "linuxcnc"],
                    "description": "Target postprocessor. Default: fanuc.",
                },
            },
            "required": ["operation_plan"],
        },
    },
    {
        "name": "validate_gcode_output",
        "description": (
            "Validate generated G-code for safety and correctness. "
            "Always call this before including G-code in the final response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "gcode": {
                    "type": "string",
                    "description": "The G-code program text to validate.",
                },
                "machine_type": {
                    "type": "string",
                    "description": "Target machine type (mill, drill, laser, etc.).",
                },
            },
            "required": ["gcode"],
        },
    },
]


# ---------------------------------------------------------------------------
# CNCAgent — full tool-use implementation
# ---------------------------------------------------------------------------


class CNCAgent:
    """CNC Supervisor Agent using Anthropic Messages API with tool use.

    Implements a multi-turn agentic loop:
    1. Supervisor calls delegate_to_subagent → OperationPlan
    2. Supervisor calls validate_operation_plan → validation result
    3. Supervisor calls postprocess_operations → G-code
    4. Supervisor calls validate_gcode_output → safety check
    5. Supervisor returns structured JSON result
    """

    def __init__(self) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is required. Install with: pip install anthropic"
            ) from exc
        self._client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self._model = os.environ.get("GENAI4G_MODEL", "claude-sonnet-4-6")
        self._max_turns = int(os.environ.get("GENAI4G_MAX_TURNS", "20"))

    # ------------------------------------------------------------------
    # Tool dispatcher
    # ------------------------------------------------------------------

    def _dispatch_tool(self, name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result as a JSON string."""
        try:
            if name == "delegate_to_subagent":
                result = self._delegate_to_subagent(
                    machine_type=tool_input["machine_type"],
                    job_spec=tool_input["job_spec"],
                )
            elif name == "validate_operation_plan":
                result = validate_operation_plan(tool_input["operation_plan"])
            elif name == "postprocess_operations":
                result = postprocess_operations(
                    tool_input["operation_plan"],
                    postprocessor=tool_input.get("postprocessor", "fanuc"),
                )
            elif name == "validate_gcode_output":
                result = validate_gcode_text(
                    tool_input["gcode"],
                    machine_type=tool_input.get("machine_type", "mill"),
                )
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as exc:  # noqa: BLE001
            result = {"error": f"Tool '{name}' raised exception: {exc}"}

        return json.dumps(result)

    # ------------------------------------------------------------------
    # Subagent delegation
    # ------------------------------------------------------------------

    def _delegate_to_subagent(self, machine_type: str, job_spec: dict) -> dict:
        """Invoke a machine-specific subagent via a secondary LLM call.

        The subagent is specialised (milling, drilling, laser) and returns
        only an OperationPlan — it never writes final G-code.
        """
        subagent = _SUBAGENTS.get(machine_type)
        if subagent is None:
            return {
                "error": (
                    f"No subagent available for machine_type='{machine_type}'. "
                    f"Supported: {list(_SUBAGENTS.keys())}"
                ),
                "missing_info": [f"machine_type '{machine_type}' subagent not implemented yet."],
            }

        system_prompt = subagent["system_prompt"]
        user_message = (
            f"Plan this manufacturing job and return a structured OperationPlan JSON.\n\n"
            f"JobSpec:\n{json.dumps(job_spec, indent=2)}\n\n"
            "Return ONLY the OperationPlan JSON object. No prose, no code fences."
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text if response.content else ""
            plan = _extract_json(raw)
            if plan is None:
                return {
                    "error": "Subagent returned non-JSON output.",
                    "raw_output": raw[:500],
                }
            # Unwrap if the subagent nested the plan under an extra key
            if "operation_plan" in plan and "operations" not in plan:
                plan = plan["operation_plan"]
            return plan
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Subagent call failed: {exc}"}

    # ------------------------------------------------------------------
    # Main agent loop
    # ------------------------------------------------------------------

    def run(self, user_message: str) -> dict[str, Any]:
        """Run the CNC supervisor loop.

        Returns a structured dict with gcode, operation_plan, assumptions,
        warnings, missing_info, validation, machine_type.
        """
        from cnc.tools.input_tools import extract_job_spec_from_text

        partial_spec = extract_job_spec_from_text(user_message)
        machine_type_hint = partial_spec.get("machine_type")

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"{user_message}\n\n"
                    f"Detected hint — machine_type: {machine_type_hint or 'unknown'}, "
                    f"units: {partial_spec.get('units', 'mm')}."
                ),
            }
        ]

        turns = 0
        final_text: str = ""

        while turns < self._max_turns:
            turns += 1
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=CNC_SUPERVISOR_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            # Collect tool calls and text from this response
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if text_blocks:
                final_text = text_blocks[-1].text

            # If no tool calls, the supervisor is done
            if not tool_use_blocks:
                break

            # Append assistant message (all content blocks)
            messages.append({
                "role": "assistant",
                "content": [_block_to_dict(b) for b in response.content],
            })

            # Execute each tool and append results
            tool_results = []
            for block in tool_use_blocks:
                result_str = self._dispatch_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

            messages.append({"role": "user", "content": tool_results})

        # Parse final structured result
        result = _extract_json(final_text)
        if result is None:
            return {
                "gcode": "",
                "operation_plan": None,
                "assumptions": [],
                "warnings": ["Supervisor returned non-JSON final response."],
                "missing_info": [],
                "validation": {
                    "ok": False,
                    "errors": ["No structured output from supervisor."],
                    "warnings": [],
                },
                "machine_type": machine_type_hint,
                "_raw": final_text[:500] if final_text else "",
            }

        # Guarantee required keys
        result.setdefault("gcode", "")
        result.setdefault("operation_plan", None)
        result.setdefault("assumptions", [])
        result.setdefault("warnings", [])
        result.setdefault("missing_info", [])
        result.setdefault("machine_type", machine_type_hint)
        result.setdefault("validation", {
            "ok": False,
            "errors": ["No validation result in response."],
            "warnings": [],
        })

        return result

    async def ainvoke(self, user_message: str) -> dict[str, Any]:
        """Async wrapper around run() for use in async contexts (e.g. MCP server).

        Runs the synchronous agent loop in a thread-pool executor so it does
        not block the event loop.
        """
        import asyncio
        return await asyncio.to_thread(self.run, user_message)


# ---------------------------------------------------------------------------
# _FallbackCNCAgent — single-shot fallback without tool-use loop
# ---------------------------------------------------------------------------


class _FallbackCNCAgent:
    """Minimal single-shot fallback agent.

    Used only if the anthropic package cannot be imported with the full client.
    Provides the same .run() interface as CNCAgent.
    """

    def __init__(self) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is required. Install with: pip install anthropic"
            ) from exc
        self._client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self._model = os.environ.get("GENAI4G_MODEL", "claude-sonnet-4-6")

    def run(self, user_message: str) -> dict[str, Any]:
        from cnc.tools.input_tools import extract_job_spec_from_text

        partial_spec = extract_job_spec_from_text(user_message)

        prompt = (
            f"{CNC_SUPERVISOR_PROMPT}\n\n"
            f"User request: {user_message}\n\n"
            f"Detected hint: {json.dumps(partial_spec)}\n\n"
            "Return ONLY a valid JSON object with keys: "
            "gcode, operation_plan, assumptions, warnings, missing_info, validation, machine_type."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text if response.content else ""
        result = _extract_json(raw)

        if result is None:
            return {
                "gcode": "",
                "operation_plan": None,
                "assumptions": [],
                "warnings": ["Agent returned non-JSON response."],
                "missing_info": [],
                "validation": {"ok": False, "errors": ["No structured output"], "warnings": []},
                "machine_type": partial_spec.get("machine_type"),
            }

        if result.get("operation_plan") and not result.get("gcode"):
            pp = postprocess_operations(result["operation_plan"], postprocessor="fanuc")
            if pp.get("ok"):
                result["gcode"] = pp["gcode"]
            else:
                result.setdefault("warnings", []).extend(pp.get("errors", []))

        if result.get("gcode"):
            val = validate_gcode_text(
                result["gcode"],
                machine_type=result.get("machine_type") or "mill",
            )
            result["validation"] = val
        else:
            result.setdefault("validation", {
                "ok": False, "errors": ["No G-code generated"], "warnings": []
            })

        return result

    async def ainvoke(self, user_message: str) -> dict[str, Any]:
        """Async wrapper — interface parity with CNCAgent."""
        import asyncio
        return await asyncio.to_thread(self.run, user_message)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from a text response."""
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, AttributeError):
        pass
    # Markdown code fence
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text or "")
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Largest JSON object in text
    for match in re.finditer(r"\{[\s\S]*\}", text or ""):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue
    return None


def _block_to_dict(block: Any) -> dict:
    """Convert an Anthropic content block to a serialisable dict."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    # Fallback for unknown block types
    return {"type": block.type}


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_cnc_agent() -> CNCAgent | _FallbackCNCAgent:
    """Build and return the CNC Supervisor Agent.

    Returns CNCAgent (full tool-use loop) when the anthropic package is
    available. Falls back to _FallbackCNCAgent only if initialisation fails.

    Returns:
        An agent with a .run(user_message: str) -> dict method.

    Raises:
        RuntimeError: If anthropic is not installed at all.
    """
    try:
        return CNCAgent()
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to initialise CNCAgent: {exc}") from exc
