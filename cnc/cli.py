"""CLI v0 — command-line interface for the GENAI4G-CODE CNC toolchain.

All commands are deterministic and require no LLM or API key.

Usage:
    python -m cnc.cli <command> [options]

Commands:
    validate-job            Validate a CNCJobSpec JSON file
    run-job                 Run a CNCJobSpec JSON file (validate + G-code + safety)
    batch-run               Run multiple CNCJobSpec files (directory or path list)
    analyze-gcode           Run the safety analyzer on a G-code file
    list-profiles           List all built-in machine profiles
    list-tools              List all built-in tools (if Tool Library is available)
    list-materials          List all built-in materials
    server                  Start the MCP server (or show the command to do so)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_json(data: object) -> None:
    """Print *data* as pretty-printed JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _error_json(errors: list[str], warnings: list[str] | None = None) -> dict:
    return {"ok": False, "errors": errors, "warnings": warnings or []}


def _read_text(path: str) -> str:
    """Read a text file; raise IOError on failure."""
    return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------

def _cmd_validate_job(args: argparse.Namespace) -> int:
    from cnc.tools.job_io import load_job_spec, validate_job_spec

    load_result = load_job_spec(args.job_path)
    if not load_result["ok"]:
        _print_json(_error_json(load_result["errors"], load_result.get("warnings", [])))
        return 1

    result = validate_job_spec(load_result["job"])
    _print_json(result)
    return 0 if result["ok"] else 1


def _cmd_run_job(args: argparse.Namespace) -> int:
    from cnc.tools.job_io import load_job_spec
    from cnc.tools.job_runs import run_job

    load_result = load_job_spec(args.job_path)
    if not load_result["ok"]:
        _print_json(_error_json(load_result["errors"], load_result.get("warnings", [])))
        return 1

    result = run_job(
        load_result["job"],
        save_gcode_path=args.gcode_out,
        save_report_path=args.report_out,
    )

    # Print a compact summary (omit the full gcode body to keep stdout readable).
    summary = {
        "ok": result["ok"],
        "status": result["run_report"].get("status"),
        "run_id": result["run_report"].get("run_id"),
        "gcode_lines": len(result["gcode"].splitlines()) if result["gcode"] else 0,
        "warnings": result["warnings"],
        "errors": result["errors"],
        "artifacts": result["artifacts"],
    }
    _print_json(summary)
    return 0 if result["ok"] else 1


def _cmd_batch_run(args: argparse.Namespace) -> int:
    from cnc.tools.batch_jobs import (
        run_job_batch_from_directory,
        run_job_batch_from_paths,
    )

    input_path = Path(args.input)

    if input_path.is_dir():
        result = run_job_batch_from_directory(
            directory=str(input_path),
            pattern=args.pattern,
            output_dir=args.output_dir,
            save_artifacts=args.save_artifacts,
            batch_name=args.batch_name,
        )
    elif input_path.is_file():
        result = run_job_batch_from_paths(
            paths=[str(input_path)],
            output_dir=args.output_dir,
            save_artifacts=args.save_artifacts,
            batch_name=args.batch_name,
        )
    else:
        _print_json(_error_json([f"Input path not found: '{args.input}'."]))
        return 1

    br = result["batch_report"]
    summary = {
        "ok": result["ok"],
        "status": br.get("status"),
        "batch_id": br.get("batch_id"),
        "total_jobs": br.get("total_jobs"),
        "ok_count": br.get("ok_count"),
        "warning_count": br.get("warning_count"),
        "failed_count": br.get("failed_count"),
        "warnings": result["warnings"],
        "errors": result["errors"],
        "results": [
            {
                "job_index": r["job_index"],
                "job_name": r.get("job_name"),
                "job_path": r.get("job_path"),
                "status": r["status"],
                "run_id": r.get("run_id"),
                "gcode_path": r.get("gcode_path"),
                "report_path": r.get("report_path"),
                "errors": r.get("errors", []),
            }
            for r in br.get("results", [])
        ],
    }
    _print_json(summary)
    return 0 if result["ok"] else 1


def _cmd_analyze_gcode(args: argparse.Namespace) -> int:
    from cnc.validators.safety_analyzer import analyze_gcode_safety

    try:
        gcode = _read_text(args.gcode_path)
    except OSError as exc:
        _print_json(_error_json([f"Cannot read file '{args.gcode_path}': {exc}"]))
        return 1

    result = analyze_gcode_safety(
        gcode=gcode,
        machine_type=args.machine_type,
        expected_units=args.expected_units,
        safe_z=args.safe_z,
        max_depth=args.max_depth,
    )
    _print_json(result)
    return 0 if result.get("ok", False) else 1


def _cmd_list_profiles(args: argparse.Namespace) -> int:
    from cnc.tools.machine_profiles import list_machine_profiles
    _print_json(list_machine_profiles())
    return 0


def _cmd_list_tools(args: argparse.Namespace) -> int:
    # Tool Library is an optional future module; degrade gracefully.
    try:
        from cnc.tools.tool_library import find_tools, list_tools  # type: ignore

        has_filters = any([
            args.machine_type,
            args.operation_type,
            args.tool_type,
            args.units,
        ])
        if has_filters:
            kwargs = {}
            if args.machine_type:
                kwargs["machine_type"] = args.machine_type
            if args.operation_type:
                kwargs["operation_type"] = args.operation_type
            if args.tool_type:
                kwargs["tool_type"] = args.tool_type
            if args.units:
                kwargs["units"] = args.units
            _print_json(find_tools(**kwargs))
        else:
            _print_json(list_tools())
    except ImportError:
        _print_json({
            "ok": False,
            "tools": [],
            "info": [
                "Tool Library is not yet available in this installation. "
                "It will be added in a future release."
            ],
        })
        return 1
    return 0


def _cmd_list_materials(args: argparse.Namespace) -> int:
    from cnc.tools.material_library import find_materials, list_materials

    has_filters = any([args.category, args.operation_type, args.machinability])
    if has_filters:
        kwargs: dict = {}
        if args.category:
            kwargs["category"] = args.category
        if args.operation_type:
            kwargs["operation_type"] = args.operation_type
        if args.machinability:
            kwargs["machinability"] = args.machinability
        _print_json(find_materials(**kwargs))
    else:
        _print_json(list_materials())
    return 0


def _cmd_server(args: argparse.Namespace) -> int:
    print(
        "To start the MCP server run:\n"
        "    python -m cnc.server\n\n"
        "The server uses stdio transport and will wait for tool messages."
    )
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cnc.cli",
        description=(
            "GENAI4G-CODE CLI — deterministic CNC toolchain "
            "(no LLM or API key required)"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    # ------------------------------------------------------------------
    # validate-job
    # ------------------------------------------------------------------
    p_vj = sub.add_parser(
        "validate-job",
        help="Validate a CNCJobSpec JSON file",
    )
    p_vj.add_argument("job_path", help="Path to a CNCJobSpec JSON file")

    # ------------------------------------------------------------------
    # run-job
    # ------------------------------------------------------------------
    p_rj = sub.add_parser(
        "run-job",
        help="Run a CNCJobSpec: validate + generate G-code + safety analysis",
    )
    p_rj.add_argument("job_path", help="Path to a CNCJobSpec JSON file")
    p_rj.add_argument(
        "--gcode-out",
        dest="gcode_out",
        default=None,
        metavar="PATH",
        help="Save generated G-code to this file",
    )
    p_rj.add_argument(
        "--report-out",
        dest="report_out",
        default=None,
        metavar="PATH",
        help="Save run report JSON to this file",
    )

    # ------------------------------------------------------------------
    # batch-run
    # ------------------------------------------------------------------
    p_br = sub.add_parser(
        "batch-run",
        help="Run multiple CNCJobSpecs (file or directory)",
    )
    p_br.add_argument(
        "input",
        help="Path to a CNCJobSpec JSON file or a directory containing them",
    )
    p_br.add_argument(
        "--pattern",
        default="*.json",
        metavar="GLOB",
        help="Glob pattern for directory scan (default: *.json)",
    )
    p_br.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        metavar="DIR",
        help="Root directory for saved artifacts",
    )
    p_br.add_argument(
        "--save-artifacts",
        dest="save_artifacts",
        action="store_true",
        help="Save G-code and run reports for each job",
    )
    p_br.add_argument(
        "--batch-name",
        dest="batch_name",
        default=None,
        metavar="NAME",
        help="Human-readable batch label",
    )

    # ------------------------------------------------------------------
    # analyze-gcode
    # ------------------------------------------------------------------
    p_ag = sub.add_parser(
        "analyze-gcode",
        help="Run the safety analyzer on a G-code file",
    )
    p_ag.add_argument("gcode_path", help="Path to a G-code file")
    p_ag.add_argument(
        "--machine-type",
        dest="machine_type",
        default="mill",
        metavar="TYPE",
        help="Machine type: mill, drill, lathe, laser, 3d_printer (default: mill)",
    )
    p_ag.add_argument(
        "--expected-units",
        dest="expected_units",
        default=None,
        metavar="UNITS",
        help="Expected unit system: mm or inch",
    )
    p_ag.add_argument(
        "--safe-z",
        dest="safe_z",
        type=float,
        default=None,
        metavar="Z",
        help="Expected safe retract Z height",
    )
    p_ag.add_argument(
        "--max-depth",
        dest="max_depth",
        type=float,
        default=None,
        metavar="DEPTH",
        help="Maximum allowed cutting depth (positive number)",
    )

    # ------------------------------------------------------------------
    # list-profiles
    # ------------------------------------------------------------------
    sub.add_parser("list-profiles", help="List all built-in machine profiles")

    # ------------------------------------------------------------------
    # list-tools
    # ------------------------------------------------------------------
    p_lt = sub.add_parser(
        "list-tools",
        help="List built-in tools (requires Tool Library module)",
    )
    p_lt.add_argument("--machine-type", dest="machine_type", default=None)
    p_lt.add_argument("--operation-type", dest="operation_type", default=None)
    p_lt.add_argument("--tool-type", dest="tool_type", default=None)
    p_lt.add_argument("--units", dest="units", default=None)

    # ------------------------------------------------------------------
    # list-materials
    # ------------------------------------------------------------------
    p_lm = sub.add_parser("list-materials", help="List all built-in materials")
    p_lm.add_argument("--category", dest="category", default=None)
    p_lm.add_argument("--operation-type", dest="operation_type", default=None)
    p_lm.add_argument("--machinability", dest="machinability", default=None)

    # ------------------------------------------------------------------
    # server
    # ------------------------------------------------------------------
    sub.add_parser(
        "server",
        help="Show how to start the MCP server",
    )

    return parser


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

_COMMAND_MAP = {
    "validate-job": _cmd_validate_job,
    "run-job": _cmd_run_job,
    "batch-run": _cmd_batch_run,
    "analyze-gcode": _cmd_analyze_gcode,
    "list-profiles": _cmd_list_profiles,
    "list-tools": _cmd_list_tools,
    "list-materials": _cmd_list_materials,
    "server": _cmd_server,
}


def main(argv: list[str] | None = None) -> int:
    """Entry point for the GENAI4G-CODE CLI.

    Parameters
    ----------
    argv:
        Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns
    -------
    int
        Exit code: 0 on success, 1 on failure.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = _COMMAND_MAP.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except Exception as exc:  # noqa: BLE001
        _print_json(_error_json([f"Unexpected error in '{args.command}': {exc}"]))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
