"""Interactive CLI Warning Resolution — user-facing issue resolution layer.

This module provides the interactive CLI renderer that presents actionable
warnings to the user and collects resolution decisions. It is the ONLY
module that performs user interaction (via injected input_fn/output_fn).

Core pipeline modules (cnc/agent.py, cnc/tools/*, cnc/validators/*) remain
completely non-interactive. The MCP server never waits on stdin.

Usage:
    from cnc.cli_interaction import resolve_issues_interactively
    result = resolve_issues_interactively(result, prompt=user_prompt)
"""

from __future__ import annotations

from typing import Any, Callable


def resolve_issues_interactively(
    result: dict,
    prompt: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[..., None] = print,
) -> dict:
    """Present actionable issues to the user and apply their decisions.

    Args:
        result: Pipeline result dict (with operation_plan, warnings, etc.)
        prompt: Original user prompt (used for material inference etc.)
        input_fn: Input function (injected for testing)
        output_fn: Output function (injected for testing)

    Returns:
        Updated result dict with resolution_log and regenerated G-code
        after plan-modifying resolutions.
    """
    from cnc.tools.issue_resolution import (
        collect_interactive_issues,
        build_issue_choices,
        apply_resolution_decision,
    )

    result.setdefault("resolution_log", [])

    # Collect issues
    issues = collect_interactive_issues(result, prompt=prompt)

    # Preserve initial issues snapshot (first pass only)
    if "initial_issues" not in result:
        result["initial_issues"] = [
            {k: v for k, v in i.items() if k != "choices"}
            for i in issues
        ]

    if not issues:
        output_fn("\nNo actionable issues found.")
        return result

    # Separate actionable from info-only
    actionable = [i for i in issues if i.get("actionable")]
    info_only = [i for i in issues if not i.get("actionable")]

    # Show and log info-only issues
    if info_only:
        output_fn("\n--- Informational ---")
        for issue in info_only:
            sev = issue["severity"].upper()
            output_fn(f"  [{sev}] {issue['title']}: {issue['message']}")
            # Log acknowledgement so the full chain is traceable
            result["resolution_log"].append({
                "issue_code": issue.get("code", ""),
                "action": "ACKNOWLEDGED",
                "title": issue.get("title", ""),
                "message": issue.get("message", ""),
                "severity": issue.get("severity", ""),
                "affected_operations": list(issue.get("affected_operations", [])),
            })
        output_fn("")

    if not actionable:
        output_fn("No actionable issues to resolve.")
        return result

    output_fn(f"\n{len(actionable)} actionable issue(s) to resolve:\n")

    plan_modified = False

    for idx, issue in enumerate(actionable):
        # Build choices for this issue
        choices = build_issue_choices(issue, result, prompt=prompt)
        issue["choices"] = choices

        # Render issue
        output_fn(f"[{idx + 1}/{len(actionable)}] {issue['title']}")
        output_fn(f"  {issue['message']}")

        if issue["affected_operations"]:
            ops_str = ", ".join(str(o) for o in issue["affected_operations"])
            output_fn(f"  Affected operations: {ops_str}")

        output_fn("")
        output_fn("  What should I do?")
        output_fn("")

        for choice in choices:
            label = choice["label"]
            desc = choice.get("description", "")
            if desc:
                output_fn(f"    {choice['key']}. {label}")
                output_fn(f"       {desc}")
            else:
                output_fn(f"    {choice['key']}. {label}")

        output_fn("")

        # Get default choice key
        default_key = _get_default_choice_key(issue, choices)

        # Collect user input with validation
        selected_choice = _get_user_choice(
            choices, default_key, input_fn, output_fn,
        )

        if selected_choice is None:
            # Should not happen with retry logic, but treat as ignore
            continue

        # Handle sub-interactions (e.g. selecting from library, entering values)
        decision = _build_decision(issue, selected_choice, result, input_fn, output_fn)

        if decision.get("action") == "ABORT":
            result = apply_resolution_decision(result, issue, decision)
            output_fn("\nAborted by user.")
            return result

        # Apply decision
        result = apply_resolution_decision(result, issue, decision)

        # Check if plan was modified
        if decision.get("action") not in ("IGNORE_ONCE",):
            plan_modified = True

        output_fn("")

    # After all resolutions, regenerate if plan was modified
    if plan_modified:
        output_fn("--- Regenerating G-code after plan modifications ---")
        result = _regenerate_after_resolution(result)
        output_fn("")

    # Re-collect issues after regeneration
    remaining = collect_interactive_issues(result, prompt=prompt)
    blocking = [i for i in remaining if i.get("blocking") and i.get("severity") == "error"]
    actionable_remaining = [i for i in remaining
                            if i.get("severity") == "warning" and i.get("actionable")]
    info_remaining = [i for i in remaining if not i.get("actionable")
                      and i.get("severity") != "error"]

    if blocking:
        output_fn(f"\n{len(blocking)} blocking error(s) remain. Cannot output G-code.")
        for b in blocking:
            output_fn(f"  [ERROR] {b['message']}")
        result["gcode_display_allowed"] = False
        return result

    all_remaining = actionable_remaining + info_remaining
    if all_remaining:
        output_fn(f"\nRemaining warnings: {len(all_remaining)}")
        output_fn("")
        output_fn("  1. Show warnings and continue to G-code")
        output_fn("  2. Go back and review")
        output_fn("  3. Abort")
        output_fn("")

        choice = _get_valid_input(
            "Choice [1]: ", ["1", "2", "3"], "1", input_fn, output_fn,
        )

        if choice == "3":
            result["aborted"] = True
            result["gcode_display_allowed"] = False
            output_fn("Aborted by user.")
            return result
        elif choice == "2":
            # Recursive re-resolution (simple approach)
            return resolve_issues_interactively(result, prompt=prompt,
                                                 input_fn=input_fn,
                                                 output_fn=output_fn)
        else:
            # Show ALL remaining warnings (actionable + informational)
            for w in actionable_remaining:
                output_fn(f"  [WARN] {w['message']}")
            for w in info_remaining:
                output_fn(f"  [INFO] {w['message']}")
            result["gcode_display_allowed"] = True
    else:
        result["gcode_display_allowed"] = True

    # Consolidate all warnings for downstream consumers (G-code header etc.)
    all_warnings = _consolidate_all_warnings(result)
    result["all_warnings"] = all_warnings

    # Inject into operation_plan so postprocessors can include them in G-code header
    op_plan = result.get("operation_plan")
    if isinstance(op_plan, dict):
        op_plan["consolidated_warnings"] = [
            w["message"] for w in all_warnings
            if w["severity"] in ("warning", "error")
        ]

    return result


def _get_default_choice_key(issue: dict, choices: list[dict]) -> str:
    """Determine the default choice for an issue."""
    code = issue.get("code", "")
    # For UNKNOWN_TOOL_ID, default to transient custom tool (key 3)
    if code == "UNKNOWN_TOOL_ID":
        for c in choices:
            if c.get("action") == "USE_TRANSIENT_CUSTOM_TOOL":
                return c["key"]
    # For MISSING_MATERIAL with inferred candidate, default to first
    if code in ("MISSING_MATERIAL", "UNKNOWN_MATERIAL"):
        if choices and choices[0].get("action") == "SET_MATERIAL":
            return choices[0]["key"]
    # For assumed defaults, default to the current default value (first choice)
    if code in ("ASSUMED_POSTPROCESSOR", "ASSUMED_UNITS", "ASSUMED_WCS", "ASSUMED_MACHINE_TYPE"):
        # Find the choice marked as current default
        for c in choices:
            if "(current default)" in c.get("label", ""):
                return c["key"]
    # Default to first choice
    return choices[0]["key"] if choices else "1"


def _get_user_choice(
    choices: list[dict],
    default_key: str,
    input_fn: Callable[[str], str],
    output_fn: Callable[..., None],
) -> dict | None:
    """Get and validate user's choice selection."""
    valid_keys = {c["key"] for c in choices}
    max_retries = 10

    for _ in range(max_retries):
        try:
            raw = input_fn(f"  Choice [{default_key}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if not raw:
            raw = default_key

        if raw in valid_keys:
            return next(c for c in choices if c["key"] == raw)

        output_fn(f"  Invalid choice '{raw}'. Valid options: {', '.join(sorted(valid_keys))}")

    return None


def _get_valid_input(
    prompt_text: str,
    valid: list[str],
    default: str,
    input_fn: Callable[[str], str],
    output_fn: Callable[..., None],
) -> str:
    """Get a validated input from valid options."""
    for _ in range(10):
        try:
            raw = input_fn(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            return default
        if not raw:
            return default
        if raw in valid:
            return raw
        output_fn(f"  Invalid input '{raw}'. Valid: {', '.join(valid)}")
    return default


def _build_decision(
    issue: dict,
    choice: dict,
    result: dict,
    input_fn: Callable[[str], str],
    output_fn: Callable[..., None],
) -> dict:
    """Build a full resolution decision, handling sub-interactions."""
    action = choice["action"]
    payload = dict(choice.get("payload", {}))

    if action == "SELECT_LIBRARY_TOOL":
        candidates = payload.get("candidates", [])
        if candidates:
            output_fn("\n  Matching tools:")
            for i, cid in enumerate(candidates, 1):
                try:
                    from cnc.tools.tool_library import get_tool
                    t = get_tool(cid)
                    if t:
                        d = t.get("diameter", "?")
                        output_fn(f"    {i}. {cid} — {d} {t.get('units', 'mm')} {t.get('name', '')}")
                    else:
                        output_fn(f"    {i}. {cid}")
                except ImportError:
                    output_fn(f"    {i}. {cid}")
            output_fn(f"    {len(candidates) + 1}. Back")
            output_fn("")

            valid = [str(i) for i in range(1, len(candidates) + 2)]
            sel = _get_valid_input("  Choice: ", valid, "1", input_fn, output_fn)
            sel_idx = int(sel) - 1
            if sel_idx < len(candidates):
                payload["tool_id"] = candidates[sel_idx]
            else:
                # Back — treat as ignore
                return {"action": "IGNORE_ONCE", "payload": {}}

    elif action == "ENTER_TOOL_ID":
        output_fn("")
        try:
            tool_id = input_fn("  Enter tool_id: ").strip()
        except (EOFError, KeyboardInterrupt):
            return {"action": "IGNORE_ONCE", "payload": {}}
        if tool_id:
            payload["tool_id"] = tool_id
        else:
            return {"action": "IGNORE_ONCE", "payload": {}}

    elif action == "SET_MATERIAL":
        if payload.get("select_from_library"):
            from cnc.tools.material_library import list_materials
            materials = list_materials()
            output_fn("\n  Available materials:")
            for i, m in enumerate(materials, 1):
                output_fn(f"    {i}. {m['id']} — {m['name']}")
            output_fn("")

            valid = [str(i) for i in range(1, len(materials) + 1)]
            sel = _get_valid_input("  Choice: ", valid, "1", input_fn, output_fn)
            sel_idx = int(sel) - 1
            if 0 <= sel_idx < len(materials):
                payload["material_id"] = materials[sel_idx]["id"]
            payload.pop("select_from_library", None)

    elif action == "SET_CUSTOM_MATERIAL":
        output_fn("")
        try:
            mat = input_fn("  Enter material name: ").strip()
        except (EOFError, KeyboardInterrupt):
            return {"action": "IGNORE_ONCE", "payload": {}}
        if mat:
            payload["material_name"] = mat
        else:
            return {"action": "IGNORE_ONCE", "payload": {}}

    elif action == "SET_FEEDRATE":
        if not payload.get("feedrate"):
            output_fn("")
            val = _get_numeric_input("  Enter feedrate (mm/min): ", input_fn, output_fn)
            if val is not None and val > 0:
                payload["feedrate"] = val
            else:
                output_fn("  Invalid feedrate. Ignoring.")
                return {"action": "IGNORE_ONCE", "payload": {}}

    elif action == "SET_SPINDLE_SPEED":
        # If the choice already has a spindle_speed (e.g. from recommendation),
        # use it directly without prompting.
        if not payload.get("spindle_speed"):
            output_fn("")
            val = _get_numeric_input("  Enter spindle speed (RPM): ", input_fn, output_fn)
            if val is not None and val > 0:
                payload["spindle_speed"] = val
            else:
                output_fn("  Invalid spindle speed. Ignoring.")
                return {"action": "IGNORE_ONCE", "payload": {}}

    elif action == "SET_SAFE_Z":
        output_fn("")
        val = _get_numeric_input("  Enter safe Z height: ", input_fn, output_fn)
        if val is not None:
            payload["safe_z"] = val
        else:
            output_fn("  Invalid value. Ignoring.")
            return {"action": "IGNORE_ONCE", "payload": {}}

    elif action == "CONFIRM_BOLT_CIRCLE_CENTER":
        # Confirmation — payload already contains center_x/center_y
        pass

    elif action == "SET_BOLT_CIRCLE_CENTER":
        output_fn("")
        cx = _get_numeric_input("  Enter center X: ", input_fn, output_fn)
        if cx is None:
            output_fn("  Invalid value. Aborting.")
            return {"action": "IGNORE_ONCE", "payload": {}}
        cy = _get_numeric_input("  Enter center Y: ", input_fn, output_fn)
        if cy is None:
            output_fn("  Invalid value. Aborting.")
            return {"action": "IGNORE_ONCE", "payload": {}}
        payload["center_x"] = cx
        payload["center_y"] = cy

    elif action == "CONFIRM_BOLT_CIRCLE_START_ANGLE":
        # Confirmation — payload already contains start_angle_deg
        pass

    elif action == "SET_BOLT_CIRCLE_START_ANGLE":
        output_fn("")
        val = _get_numeric_input("  Enter start angle (degrees): ", input_fn, output_fn)
        if val is not None:
            payload["start_angle_deg"] = val
        else:
            output_fn("  Invalid value. Aborting.")
            return {"action": "IGNORE_ONCE", "payload": {}}

    elif action == "SET_BOLT_CIRCLE_HOLE_TYPE":
        # hole_type is already set in payload from the choice
        pass

    elif action == "CONFIRM_Z_REFERENCE":
        # Confirmation — payload already contains z_reference
        pass

    elif action == "SET_CUSTOM_DIAMETER":
        output_fn("")
        val = _get_numeric_input("  Enter tool diameter (mm): ", input_fn, output_fn)
        if val is not None and val > 0:
            payload["diameter"] = val
        else:
            output_fn("  Invalid diameter. Ignoring.")
            return {"action": "IGNORE_ONCE", "payload": {}}

    return {
        "issue_id": issue.get("id", ""),
        "issue_code": issue.get("code", ""),
        "action": action,
        "choice_key": choice.get("key"),
        "payload": payload,
        "ignored": action == "IGNORE_ONCE",
    }


def _get_numeric_input(
    prompt_text: str,
    input_fn: Callable[[str], str],
    output_fn: Callable[..., None],
) -> float | None:
    """Get a numeric value from the user."""
    for _ in range(3):
        try:
            raw = input_fn(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            output_fn(f"  '{raw}' is not a valid number. Try again.")
    return None


def _consolidate_all_warnings(result: dict) -> list[dict]:
    """Build a deduplicated list of all warnings from every pipeline stage.

    Each entry: {source, severity, message}.
    This is the single authoritative list that downstream consumers
    (G-code header, final report) should use.
    """
    seen: set[str] = set()
    consolidated: list[dict] = []

    def _add(msg: str, severity: str, source: str) -> None:
        if msg and msg not in seen:
            seen.add(msg)
            consolidated.append({"source": source, "severity": severity, "message": msg})

    # operation_plan warnings
    op = result.get("operation_plan", {})
    if isinstance(op, dict):
        for w in op.get("warnings", []):
            _add(w, "warning", "operation_plan")
        for a in op.get("assumptions", []):
            _add(a, "info", "assumption")

    # validation
    val = result.get("validation", {})
    if isinstance(val, dict):
        for w in val.get("warnings", []):
            _add(w, "warning", "validation")
        for e in val.get("errors", []):
            _add(e, "error", "validation")

    # safety_report
    sr = result.get("safety_report", {})
    if isinstance(sr, dict):
        for w in sr.get("warnings", []):
            _add(w, "warning", "safety")
        for f in sr.get("findings", []):
            if isinstance(f, dict) and f.get("message"):
                _add(f["message"], f.get("severity", "warning"), "safety")

    # guardrails
    gr = result.get("guardrails", {})
    if isinstance(gr, dict):
        for w in gr.get("warnings", []):
            _add(w, "warning", "guardrail")

    # resolution_log: include acknowledged informational issues, but
    # skip those whose content is about issues that were subsequently
    # resolved (e.g. "feedrate missing" after SET_FEEDRATE).
    from cnc.tools.issue_resolution import _RESOLVED_CLEANUP_PATTERNS

    resolved_pats: list = []
    for entry in result.get("resolution_log", []):
        action = entry.get("action", "")
        if action not in ("ACKNOWLEDGED", "IGNORE_ONCE"):
            code = entry.get("issue_code", "")
            for p in _RESOLVED_CLEANUP_PATTERNS.get(code, []):
                resolved_pats.append(p)

    for entry in result.get("resolution_log", []):
        if entry.get("action") == "ACKNOWLEDGED" and entry.get("message"):
            msg = entry["message"]
            # Skip if content matches a resolved issue's cleanup pattern
            if resolved_pats and any(p.search(msg) for p in resolved_pats):
                continue
            _add(msg, entry.get("severity", "info"), "acknowledged")

    return consolidated


def _regenerate_after_resolution(result: dict) -> dict:
    """Regenerate G-code deterministically after plan modifications.

    Removes stale top-level warnings/errors that correspond to resolved
    issues before calling the pipeline so that only warnings valid for
    the *current* plan state survive.
    """
    from cnc.tools.issue_resolution import _RESOLVED_CLEANUP_PATTERNS

    # Collect cleanup patterns for every resolved issue
    resolved_pats: list = []
    acknowledged_general_msgs: set[str] = set()
    for entry in result.get("resolution_log", []):
        action = entry.get("action", "")
        if action not in ("ACKNOWLEDGED", "IGNORE_ONCE"):
            code = entry.get("issue_code", "")
            for p in _RESOLVED_CLEANUP_PATTERNS.get(code, []):
                resolved_pats.append(p)
        elif action == "ACKNOWLEDGED" and entry.get("issue_code") == "GENERAL_WARNING":
            # Collect ACKNOWLEDGED general messages — they are ephemeral
            # agent-generated messages that should not persist after
            # the issues they describe are resolved.
            msg = entry.get("message", "")
            if msg:
                acknowledged_general_msgs.add(msg)

    def _is_stale(w: str) -> bool:
        if resolved_pats and any(p.search(w) for p in resolved_pats):
            return True
        if w in acknowledged_general_msgs:
            return True
        return False

    # Filter stale warnings; keep legitimate safety / informational ones
    result["warnings"] = [
        w for w in result.get("warnings", []) if not _is_stale(str(w))
    ]
    # Clear errors — the pipeline re-derives valid errors from the plan
    result["errors"] = []

    try:
        from cnc.tools.gcode_pipeline import regenerate_gcode_from_operation_plan
        result = regenerate_gcode_from_operation_plan(result)
    except Exception as exc:
        result.setdefault("errors", []).append(
            f"Regeneration after resolution failed: {exc}"
        )
    return result
