"""Demo: Batch Jobs v0.

Shows how to load multiple JobSpec files and run them as a batch,
producing G-code files and run reports for each job.
No API key required.

Run:
    python -m scripts.demo_batch_jobs
"""

from __future__ import annotations

import os

from cnc.tools.batch_jobs import run_job_batch_from_paths

PATHS = [
    "examples/jobs/drill_pattern_job.json",
    "examples/jobs/milling_pocket_job.json",
]
OUTPUT_DIR = "outputs/batches/demo_batch"


def main() -> None:
    print("=" * 62)
    print("DEMO: Batch Jobs v0")
    print("=" * 62)

    print(f"\n[1] Running batch of {len(PATHS)} jobs ...")
    print(f"    output_dir:     {OUTPUT_DIR!r}")
    print(f"    save_artifacts: True")

    result = run_job_batch_from_paths(
        paths=PATHS,
        output_dir=OUTPUT_DIR,
        save_artifacts=True,
        batch_name="demo_batch",
    )

    br = result["batch_report"]
    print(f"\n[2] Batch summary:")
    print(f"    batch_id:    {br['batch_id']}")
    print(f"    created_at:  {br['created_at']}")
    print(f"    status:      {br['status']}")
    print(f"    total_jobs:  {br['total_jobs']}")
    print(f"    ok_count:    {br['ok_count']}")
    print(f"    warning_count: {br['warning_count']}")
    print(f"    failed_count:  {br['failed_count']}")
    print(f"    ok:          {result['ok']}")

    if result["errors"]:
        for e in result["errors"]:
            print(f"    batch error: {e}")
    for w in result["warnings"]:
        print(f"    batch warning: {w}")

    print(f"\n[3] Per-job results:")
    for entry in br["results"]:
        idx = entry["job_index"]
        name = entry.get("job_name") or "(unnamed)"
        status = entry["status"]
        gcode_path = entry.get("gcode_path")
        report_path = entry.get("report_path")

        gcode_size = (
            os.path.getsize(gcode_path)
            if gcode_path and os.path.exists(gcode_path)
            else "?"
        )
        report_size = (
            os.path.getsize(report_path)
            if report_path and os.path.exists(report_path)
            else "?"
        )

        print(f"\n    Job {idx}: {name!r}")
        print(f"      status:      {status}")
        print(f"      run_id:      {entry.get('run_id')}")
        print(f"      gcode_path:  {gcode_path}  ({gcode_size} bytes)")
        print(f"      report_path: {report_path}  ({report_size} bytes)")
        for e in entry.get("errors", []):
            print(f"      error:   {e}")
        for w in entry.get("warnings", []):
            print(f"      warning: {w}")

    print("\n[OK] Demo completed successfully -- no API key required.")


if __name__ == "__main__":
    main()
