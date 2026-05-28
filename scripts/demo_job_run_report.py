"""Demo: Job Runs and Reports v0.

Shows how to load a JobSpec, execute a run (validation + G-code generation
+ safety analysis), save artifacts, and inspect the run report.
No API key required.

Run:
    python -m scripts.demo_job_run_report
"""

from __future__ import annotations

import os

from cnc.tools.job_io import load_job_spec
from cnc.tools.job_runs import load_run_report, run_job

GCODE_PATH = "outputs/gcode/demo_pocket.nc"
REPORT_PATH = "outputs/runs/demo_pocket_run.json"
JOB_PATH = "examples/jobs/milling_pocket_job.json"


def main() -> None:
    print("=" * 62)
    print("DEMO: Job Runs and Reports v0")
    print("=" * 62)

    # ------------------------------------------------------------------
    # 1. Load example job
    # ------------------------------------------------------------------
    print(f"\n[1] Loading job from {JOB_PATH!r} ...")
    load_result = load_job_spec(JOB_PATH)
    print(f"    ok:    {load_result['ok']}")
    if not load_result["ok"]:
        for e in load_result["errors"]:
            print(f"    error: {e}")
        return
    job = load_result["job"]
    print(f"    name:  {job.get('name')}")
    print(f"    type:  {job.get('machine_type')}")

    # ------------------------------------------------------------------
    # 2. Run the job
    # ------------------------------------------------------------------
    print(f"\n[2] Running job (save_gcode_path={GCODE_PATH!r}, save_report_path={REPORT_PATH!r}) ...")
    result = run_job(
        job,
        save_gcode_path=GCODE_PATH,
        save_report_path=REPORT_PATH,
    )

    print(f"    ok:          {result['ok']}")
    print(f"    status:      {result['run_report']['status']}")
    print(f"    run_id:      {result['run_report']['run_id']}")
    print(f"    created_at:  {result['run_report']['created_at']}")
    print(f"    postprocessor: {result['run_report']['postprocessor']}")

    if result["errors"]:
        for e in result["errors"]:
            print(f"    error:   {e}")
    for w in result["warnings"]:
        print(f"    warning: {w}")

    # ------------------------------------------------------------------
    # 3. Artifacts
    # ------------------------------------------------------------------
    print(f"\n[3] Artifacts ({len(result['artifacts'])}):")
    for art in result["artifacts"]:
        size = (
            os.path.getsize(art["path"])
            if art.get("path") and os.path.exists(art["path"])
            else "?"
        )
        print(f"    [{art['kind']}]  {art['path']}  ({size} bytes)")

    # ------------------------------------------------------------------
    # 4. G-code preview
    # ------------------------------------------------------------------
    gcode = result["gcode"]
    lines = gcode.splitlines()
    print(f"\n[4] G-code preview ({len(lines)} lines):")
    for line in lines[:6]:
        print(f"    {line}")
    if len(lines) > 6:
        print(f"    ... ({len(lines) - 6} more lines)")

    # ------------------------------------------------------------------
    # 5. Validation summary
    # ------------------------------------------------------------------
    op_val = result["run_report"].get("operation_plan_validation") or {}
    guardrails = result["run_report"].get("guardrails") or {}
    safety = result["run_report"].get("safety_report") or {}
    print(f"\n[5] Validation summary:")
    print(f"    op_plan_validation ok: {op_val.get('ok')}")
    print(f"    guardrails ok:         {guardrails.get('ok')}")
    print(f"    safety risk_level:     {safety.get('risk_level')}")

    # ------------------------------------------------------------------
    # 6. Reload and verify run report
    # ------------------------------------------------------------------
    print(f"\n[6] Reloading run report from {REPORT_PATH!r} ...")
    loaded = load_run_report(REPORT_PATH)
    print(f"    ok:      {loaded['ok']}")
    if loaded["ok"]:
        rr = loaded["run_report"]
        print(f"    run_id:  {rr.get('run_id')}")
        print(f"    status:  {rr.get('status')}")
        print(f"    schema:  {rr.get('schema_version')}")

    print("\n[OK] Demo completed successfully -- no API key required.")


if __name__ == "__main__":
    main()
