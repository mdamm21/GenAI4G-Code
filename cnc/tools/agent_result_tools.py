"""Agent result tools — extract and normalize OperationPlans from agent output.

Agents may return results in many shapes. These helpers robustly extract a
structured OperationPlan and normalize it to the canonical schema before it
is validated, postprocessed, or returned to the caller.
"""

from __future__ import annotations

import json
import re


def is_operation_plan_like(value: object) -> bool:
    """Return True if value looks like an OperationPlan dict.

    Minimal check: value is a dict containing at least one of:
    - "machine_type"
    - "operations"
    - "missing_info"
    """
    if not isinstance(value, dict):
        return False
    return any(k in value for k in ("machine_type", "operations", "missing_info"))


def _extract_json_from_string(text: str) -> dict | None:
    """Extract the first JSON object from a string."""
    # Direct parse
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, AttributeError):
        pass
    # Markdown code fence
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text or "")
    if fenced:
        try:
            parsed = json.loads(fenced.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    # Largest JSON-object in text
    for match in re.finditer(r"\{[\s\S]*\}", text or ""):
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def extract_operation_plan_from_agent_result(result: object) -> dict:
    """Extract a structured OperationPlan from a raw agent return value.

    Handles the following forms:
    - dict that already looks like an OperationPlan
    - dict with ``"operation_plan"`` key
    - dict with ``"output"`` key containing a JSON string or dict
    - dict with ``"messages"`` key (last assistant message content extracted)
    - plain JSON string containing an OperationPlan-like dict
    - any other form → structured error dict

    Returns:
        The OperationPlan dict if found, otherwise a failure dict::

            {
              "ok": False,
              "errors": ["Agent returned unstructured output."],
              "warnings": [],
              "operation_plan": None,
              "raw_output_preview": "...",
            }
    """

    def _failure(raw: object) -> dict:
        preview = ""
        if isinstance(raw, str):
            preview = raw[:200]
        elif isinstance(raw, dict):
            preview = str(raw)[:200]
        elif raw is not None:
            preview = repr(raw)[:200]
        return {
            "ok": False,
            "errors": [
                "Agent returned unstructured output. "
                "Refusing to treat it as an OperationPlan."
            ],
            "warnings": [],
            "operation_plan": None,
            "raw_output_preview": preview,
        }

    # --- Case 1: direct OperationPlan dict ---
    if is_operation_plan_like(result):
        return result  # type: ignore[return-value]

    # --- Case 2: dict with known wrapper keys ---
    if isinstance(result, dict):
        # "operation_plan" key
        candidate = result.get("operation_plan")
        if candidate is not None:
            if is_operation_plan_like(candidate):
                return candidate  # type: ignore[return-value]
            if isinstance(candidate, str):
                parsed = _extract_json_from_string(candidate)
                if parsed is not None and is_operation_plan_like(parsed):
                    return parsed

        # "output" key
        output = result.get("output")
        if output is not None:
            if is_operation_plan_like(output):
                return output  # type: ignore[return-value]
            if isinstance(output, str):
                parsed = _extract_json_from_string(output)
                if parsed is not None and is_operation_plan_like(parsed):
                    return parsed

        # "messages" key — scan last assistant messages backwards
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            for msg in reversed(messages):
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") not in ("assistant", None):
                    continue
                content = msg.get("content", "")
                if isinstance(content, str):
                    parsed = _extract_json_from_string(content)
                    if parsed is not None and is_operation_plan_like(parsed):
                        return parsed
                elif isinstance(content, list):
                    for block in reversed(content):
                        if isinstance(block, dict) and block.get("type") == "text":
                            parsed = _extract_json_from_string(block.get("text", ""))
                            if parsed is not None and is_operation_plan_like(parsed):
                                return parsed

        return _failure(result)

    # --- Case 3: plain string ---
    if isinstance(result, str):
        parsed = _extract_json_from_string(result)
        if parsed is not None and is_operation_plan_like(parsed):
            return parsed
        return _failure(result)

    # --- Unknown type ---
    return _failure(result)


def normalize_agent_operation_plan(
    raw: dict,
    preferred_machine_type: str | None = None,
) -> dict:
    """Normalize an OperationPlan-like dict to the canonical schema.

    Fills optional fields with safe defaults without silently inventing
    critical machining parameters.

    **Never silently invented** (left absent if not present in raw):
    - ``units``
    - ``safe_z``
    - ``feedrate`` / ``feedrate_mmpm``
    - ``tool_diameter``
    - ``depth``
    - ``spindle_speed`` / ``spindle_rpm``
    - ``step_down`` / ``step_over``

    **Safe defaults added** when missing:
    - ``assumptions`` → ``[]``
    - ``warnings`` → ``[]``
    - ``missing_info`` → ``[]``
    - ``tools`` → ``[]``
    - ``operations`` → ``[]``
    - ``work_coordinate_system`` → ``"G54"`` (with a warning appended)
    - ``machine_type`` → ``preferred_machine_type`` if raw has none and hint is set

    Args:
        raw: Raw OperationPlan-like dict from agent output.
        preferred_machine_type: Optional hint from the caller (e.g., MCP param).

    Returns:
        Normalized OperationPlan dict (shallow copy of raw with defaults applied).
    """
    plan: dict = dict(raw)  # shallow copy — do not mutate caller's dict

    # machine_type: only fill from hint when raw has none
    if not plan.get("machine_type") and preferred_machine_type:
        plan["machine_type"] = preferred_machine_type

    # Safe list defaults
    plan.setdefault("assumptions", [])
    plan.setdefault("warnings", [])
    plan.setdefault("missing_info", [])
    plan.setdefault("tools", [])
    plan.setdefault("operations", [])

    # work_coordinate_system: default G54 + warning
    if not plan.get("work_coordinate_system"):
        plan["work_coordinate_system"] = "G54"
        plan["warnings"] = list(plan["warnings"]) + [
            "work_coordinate_system was not provided by the agent. Defaulted to G54. "
            "Verify the correct work offset is active on the machine."
        ]

    return plan
