"""Response contract helpers for MCP tool responses.

Provides standardised envelope builders for MCP tool return values.

Conventions
-----------
- Lookup/meta tools use the full envelope: ok, data, warnings, errors, metadata.
- CNC G-code generation tools keep their domain-specific top-level keys
  (gcode, operation_plan, validation, safety_report) and are NOT wrapped
  into ``data`` — doing so would break existing callers and tests.
- ``ok: True`` means the pipeline succeeded technically.
  It does NOT mean the G-code is safe to run on a real machine.
"""

from __future__ import annotations


def success_response(
    data: dict | list | str | None = None,
    warnings: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build a successful response envelope.

    Returns
    -------
    dict with keys: ok, data, warnings, errors, metadata
    """
    return {
        "ok": True,
        "data": data,
        "warnings": warnings or [],
        "errors": [],
        "metadata": metadata or {},
    }


def error_response(
    errors: list[str] | str,
    data: dict | list | str | None = None,
    warnings: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build an error response envelope.

    Parameters
    ----------
    errors:
        A single error string or a list of error strings.

    Returns
    -------
    dict with keys: ok, data, warnings, errors, metadata
    """
    if isinstance(errors, str):
        errors_list: list[str] = [errors]
    else:
        errors_list = list(errors)
    return {
        "ok": False,
        "data": data,
        "warnings": warnings or [],
        "errors": errors_list,
        "metadata": metadata or {},
    }


def merge_warnings_errors(*items: dict) -> dict:
    """Collect warnings and errors from multiple response dicts.

    Parameters
    ----------
    *items:
        Any number of dicts that may contain ``warnings`` and/or ``errors`` lists.

    Returns
    -------
    dict with keys: warnings (list[str]), errors (list[str])
    """
    warnings: list[str] = []
    errors: list[str] = []
    for item in items:
        if isinstance(item, dict):
            warnings.extend(item.get("warnings") or [])
            errors.extend(item.get("errors") or [])
    return {"warnings": warnings, "errors": errors}


def normalize_exception_response(
    exc: Exception,
    context: str | None = None,
) -> dict:
    """Convert an unexpected exception into a safe error response envelope.

    No stack trace is included in the response. The exception type is
    recorded in metadata for diagnostics.

    Parameters
    ----------
    exc:
        The caught exception.
    context:
        Optional label prepended to the error message, e.g. ``"get_tool_info"``.

    Returns
    -------
    dict with keys: ok, data, warnings, errors, metadata
    """
    message = str(exc) if str(exc) else repr(exc)
    error_msg = f"{context}: {message}" if context else message
    return {
        "ok": False,
        "data": None,
        "warnings": [],
        "errors": [error_msg],
        "metadata": {
            "exception_type": type(exc).__name__,
        },
    }


def finding(
    severity: str,
    code: str,
    message: str,
    **extra: object,
) -> dict:
    """Build a single finding dict for use in ``findings`` lists.

    Parameters
    ----------
    severity:
        ``"info"``, ``"warning"``, or ``"error"``.
    code:
        Short machine-readable identifier, e.g. ``"MISSING_FEEDRATE"``.
    message:
        Human-readable description.
    **extra:
        Additional fields (e.g. ``line``, ``operation_index``).

    Returns
    -------
    dict with at least: severity, code, message
    """
    result: dict = {"severity": severity, "code": code, "message": message}
    result.update(extra)
    return result
