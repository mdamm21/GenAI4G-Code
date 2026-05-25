"""CNC DeepAgent builder — internal orchestrator for G-code generation pipeline.

Architecture: MCP Server (outer) -> DeepAgent (inner) -> Subagents -> Postprocessors -> Validators

Usage:
    from cnc.agent import build_cnc_agent
    agent = build_cnc_agent()
    result = agent.run("Mill a 50x50mm pocket 10mm deep in aluminium")
"""

from __future__ import annotations

import json
import os
from typing import Any

# ---------------------------------------------------------------------------
# Robust deepagents import
# ---------------------------------------------------------------------------
# TODO: Replace with the correct import once deepagents/claude-agent-sdk API is confirmed.
# Try multiple known package names for robustness.

_CREATE_DEEP_AGENT = None
_IMPORT_ERROR: str | None = None

for _candidate in (
    ("deepagents", "create_deep_agent"),
    ("claude_agent_sdk", "create_deep_agent"),
    ("anthropic.agents", "create_deep_agent"),
):
    try:
        import importlib
        _mod = importlib.import_module(_candidate[0])
        _CREATE_DEEP_AGENT = getattr(_mod, _candidate[1])
        break
    except (ImportError, AttributeError):
        continue

if _CREATE_DEEP_AGENT is None:
    _IMPORT_ERROR = (
        "deepagents (create_deep_agent) is not available. "
        "Install with: pip install deepagents\n"
        "Or check if your package is named differently (claude-agent-sdk, etc.).\n"
        "See: https://docs.anthropic.com/agents"
    )

# ---------------------------------------------------------------------------
# Subagent and tool imports
# ---------------------------------------------------------------------------

from cnc.subagents.milling import MILLING_AGENT
from cnc.subagents.drilling import DRILLING_AGENT
from cnc.subagents.laser import LASER_AGENT
from cnc.tools.postprocess_tools import postprocess_operations
from cnc.tools.validation_tools import validate_operation_plan

# ---------------------------------------------------------------------------
# Supervisor system prompt
# ---------------------------------------------------------------------------

CNC_SUPERVISOR_PROMPT = """\
You are the CNC Supervisor Agent.

Your job:
1. Understand the manufacturing request from the user.
2. Extract or ask for missing information (material, dimensions, tool, units, machine type).
3. Build a neutral manufacturing JobSpec.
4. Delegate machine-specific planning to the correct subagent (milling, drilling, laser, etc.).
5. Never output unsafe G-code without validation.
6. Prefer structured operation plans over free-form G-code.
7. Always return assumptions and warnings.
8. Never invent missing critical machining parameters silently.
9. If information is missing, return missing_info instead of unsafe G-code.

## Workflow
1. Parse user request -> identify machine_type, units, material, description.
2. Delegate to the appropriate subagent to produce an OperationPlan.
3. Call validate_operation_plan(operation_plan) to check completeness.
4. If valid, call postprocess_operations(operation_plan, postprocessor="fanuc") to get G-code.
5. Return a structured result with: gcode, operation_plan, assumptions, warnings, validation.

## Supported machines
- mill (CNC milling) -> milling_agent
- drill (CNC drilling) -> drilling_agent
- laser (laser cutting/engraving) -> laser_agent
- lathe, grinder, 3d_printer -> inform user that planning is not yet available

## Response format
Always return a JSON-serialisable dict with keys:
- gcode: str (final G-code or empty string)
- operation_plan: dict | null
- assumptions: list[str]
- warnings: list[str]
- missing_info: list[str]
- validation: {"ok": bool, "errors": list, "warnings": list}
- machine_type: str | null
"""

# ---------------------------------------------------------------------------
# Fallback agent — used when deepagents is not installed
# ---------------------------------------------------------------------------


class _FallbackCNCAgent:
    """Minimal fallback agent using direct Anthropic API calls.

    Used when deepagents is not installed. Provides the same interface
    as a real DeepAgent but without multi-agent orchestration.
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
        """Run the CNC supervisor agent with a user message.

        Returns a structured dict with gcode, operation_plan, etc.
        """
        from cnc.tools.input_tools import extract_job_spec_from_text

        # Light pre-parse for machine type hint
        partial_spec = extract_job_spec_from_text(user_message)

        prompt = (
            f"{CNC_SUPERVISOR_PROMPT}\n\n"
            f"User request: {user_message}\n\n"
            f"Partial spec detected: {json.dumps(partial_spec)}\n\n"
            "Return ONLY a valid JSON object with keys: "
            "gcode, operation_plan, assumptions, warnings, missing_info, validation, machine_type."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text if response.content else ""

        # Extract JSON from response
        result = _extract_json(raw)
        if result is None:
            return {
                "gcode": "",
                "operation_plan": None,
                "assumptions": [],
                "warnings": ["Agent returned non-JSON response — see raw output."],
                "missing_info": [],
                "validation": {"ok": False, "errors": ["No structured output"], "warnings": []},
                "machine_type": partial_spec.get("machine_type"),
                "_raw": raw,
            }

        # Run postprocessor if we have an operation plan but no gcode
        if result.get("operation_plan") and not result.get("gcode"):
            pp_result = postprocess_operations(
                result["operation_plan"],
                postprocessor="fanuc",
            )
            if pp_result.get("ok"):
                result["gcode"] = pp_result["gcode"]
            else:
                result.setdefault("warnings", []).extend(pp_result.get("errors", []))

        # Validate gcode if present
        if result.get("gcode"):
            from cnc.validators.gcode_validator import validate_gcode_text
            val = validate_gcode_text(
                result["gcode"],
                machine_type=result.get("machine_type", "mill") or "mill",
            )
            result["validation"] = val
        else:
            result.setdefault("validation", {"ok": False, "errors": ["No G-code generated"], "warnings": []})

        return result


def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from a text response."""
    import re
    # Try full parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try extracting largest JSON object
    for match in re.finditer(r"\{[\s\S]*\}", text):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue
    return None


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_cnc_agent():
    """Build and return the CNC Supervisor DeepAgent.

    Prefers deepagents.create_deep_agent if available.
    Falls back to a minimal Anthropic-API-based agent with the same interface.

    Returns:
        An agent object with a .run(user_message: str) -> dict method.

    Raises:
        RuntimeError: If neither deepagents nor anthropic is available.
    """
    if _CREATE_DEEP_AGENT is not None:
        # TODO: Adjust this call to match the exact deepagents API.
        # This is a best-guess based on expected SDK conventions.
        # See deepagents documentation for the correct parameter names.
        try:
            agent = _CREATE_DEEP_AGENT(
                system_prompt=CNC_SUPERVISOR_PROMPT,
                subagents=[MILLING_AGENT, DRILLING_AGENT, LASER_AGENT],
                tools=[postprocess_operations, validate_operation_plan],
                skills=[
                    "cnc/skills/safety",
                    "cnc/skills/gcode",
                ],
                model=os.environ.get("GENAI4G_MODEL", "claude-sonnet-4-6"),
                max_turns=int(os.environ.get("GENAI4G_MAX_TURNS", "20")),
            )
            return agent
        except Exception as exc:
            raise RuntimeError(
                f"create_deep_agent failed: {exc}\n"
                "TODO: Check deepagents API and adjust build_cnc_agent() call in cnc/agent.py."
            ) from exc

    # Fallback: use direct Anthropic API
    return _FallbackCNCAgent()
