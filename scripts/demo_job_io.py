"""Demo: JSON JobSpec Import/Export v0.

Shows how to create, save, load, validate, and regenerate G-code
from a CNC job spec — no API key required.

Run:
    python -m scripts.demo_job_io
"""

from __future__ import annotations

import os

from cnc.tools.job_io import (
    create_job_spec,
    job_spec_to_gcode,
    load_job_spec,
    save_job_spec,
    validate_job_spec,
)
from cnc.tools.milling_tools import build_milling_pocket_operation_plan

OUTPUT_PATH = "examples/jobs/generated_demo_pocket_job.json"


def main() -> None:
    print("=" * 62)
    print("DEMO: JSON JobSpec Import/Export v0")
    print("=" * 62)

    # ------------------------------------------------------------------
    # 1. Build a milling pocket OperationPlan
    # ------------------------------------------------------------------
    print("\n[1] Building milling pocket OperationPlan ...")
    op_plan = build_milling_pocket_operation_plan(
        origin_x=0.0,
        origin_y=0.0,
        width=50.0,
        height=30.0,
        depth=5.0,
        tool_diameter=6.0,
        step_down=1.5,
        step_over=3.0,
        safe_z=5.0,
        feedrate=200.0,
        spindle_speed=4000.0,
        material="aluminum_6061",
    )
    print(f"    machine_type: {op_plan['machine_type']}")
    print(f"    operations:   {len(op_plan['operations'])}")

    # ------------------------------------------------------------------
    # 2. Create a JobSpec
    # ------------------------------------------------------------------
    print("\n[2] Creating CNCJobSpec ...")
    job = create_job_spec(
        operation_plan=op_plan,
        name="Demo pocket job",
        description="50x30x5 mm pocket, 6mm endmill, Al6061",
        machine_profile="generic_mill_mm",
        material="aluminum_6061",
        postprocessor="fanuc",
        metadata={"author": "demo_job_io.py", "units": "mm"},
    )
    print(f"    schema_version: {job['schema_version']}")
    print(f"    job_id:         {job['job_id']}")
    print(f"    name:           {job['name']}")
    print(f"    machine_type:   {job['machine_type']}")
    print(f"    material:       {job['material']}")
    print(f"    tool_ids:       {job['tool_ids']}")
    print(f"    postprocessor:  {job['postprocessor']}")
    print(f"    warnings:       {job['warnings']}")

    # ------------------------------------------------------------------
    # 3. Save to file
    # ------------------------------------------------------------------
    print(f"\n[3] Saving job to {OUTPUT_PATH!r} ...")
    save_result = save_job_spec(job, OUTPUT_PATH)
    print(f"    ok:     {save_result['ok']}")
    print(f"    path:   {save_result['path']}")
    if save_result["errors"]:
        for e in save_result["errors"]:
            print(f"    error:  {e}")
    file_size = os.path.getsize(OUTPUT_PATH) if os.path.exists(OUTPUT_PATH) else 0
    print(f"    size:   {file_size} bytes")

    # ------------------------------------------------------------------
    # 4. Load from file
    # ------------------------------------------------------------------
    print(f"\n[4] Loading job from {OUTPUT_PATH!r} ...")
    load_result = load_job_spec(OUTPUT_PATH)
    print(f"    ok:            {load_result['ok']}")
    if load_result["errors"]:
        for e in load_result["errors"]:
            print(f"    error:  {e}")
    if load_result["warnings"]:
        for w in load_result["warnings"]:
            print(f"    warning: {w}")
    loaded_job = load_result["job"]
    print(f"    loaded name:   {loaded_job.get('name')}")
    print(f"    schema_version:{loaded_job.get('schema_version')}")

    # ------------------------------------------------------------------
    # 5. Validate the loaded job
    # ------------------------------------------------------------------
    print("\n[5] Validating loaded job ...")
    val = validate_job_spec(loaded_job)
    print(f"    ok:      {val['ok']}")
    print(f"    errors:  {val['errors']}")
    for w in val["warnings"]:
        print(f"    warning: {w}")
    op_val = val.get("operation_plan_validation") or {}
    print(f"    op_validation ok: {op_val.get('ok')}")
    guardrails = val.get("guardrails") or {}
    print(f"    guardrails ok:    {guardrails.get('ok')}")

    # ------------------------------------------------------------------
    # 6. Regenerate G-code from loaded job
    # ------------------------------------------------------------------
    print("\n[6] Regenerating G-code from loaded job ...")
    gc = job_spec_to_gcode(loaded_job)
    print(f"    ok:           {gc['ok']}")
    print(f"    postprocessor:{gc['postprocessor']}")
    print(f"    errors:       {gc['errors']}")
    for w in gc["warnings"]:
        print(f"    warning: {w}")
    gcode_lines = gc["gcode"].splitlines()
    print(f"    G-code lines: {len(gcode_lines)}")
    if gcode_lines:
        print(f"    First line:   {gcode_lines[0]}")
        print(f"    Last line:    {gcode_lines[-1]}")

    # ------------------------------------------------------------------
    # 7. Demonstrate stored-gcode rejection
    # ------------------------------------------------------------------
    print("\n[7] Demo: stored gcode field is ignored ...")
    job_with_gcode = dict(loaded_job)
    job_with_gcode["gcode"] = "... [18 rows x 4 passes] -- abbreviated by LLM"
    gc2 = job_spec_to_gcode(job_with_gcode)
    fake_in_result = "18 rows" in gc2["gcode"]
    print(f"    fake gcode appears in result: {fake_in_result}  (expected: False)")
    print(f"    ok: {gc2['ok']}")
    for w in gc2["warnings"]:
        print(f"    warning: {w}")

    print("\n[OK] Demo completed successfully -- no API key required.")


if __name__ == "__main__":
    main()
