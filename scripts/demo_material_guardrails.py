"""Demo: Material Library v0 and Parameter Guardrails.

Shows how to use the material library and guardrails alongside the
deterministic G-code pipeline — no API key required.

Run:
    python -m scripts.demo_material_guardrails
"""

from __future__ import annotations

from cnc.tools.material_library import (
    find_materials,
    get_material,
    list_materials,
    normalize_material,
)
from cnc.tools.parameter_guardrails import evaluate_parameter_guardrails
from cnc.tools.milling_tools import (
    build_milling_pocket_operation_plan,
    generate_milling_pocket_gcode_from_params,
)


def main() -> None:
    print("=" * 62)
    print("DEMO: Material Library v0 and Parameter Guardrails")
    print("=" * 62)

    # ------------------------------------------------------------------
    # 1. List available materials
    # ------------------------------------------------------------------
    print("\n[1] Available materials:")
    for m in list_materials():
        print(
            f"    {m['id']:30s}  {m['category']:20s}  machinability={m['machinability']}"
        )

    # ------------------------------------------------------------------
    # 2. Get specific materials
    # ------------------------------------------------------------------
    print("\n[2] aluminum_6061:")
    al = get_material("aluminum_6061")
    for note in al["notes"]:
        print(f"    note:    {note}")
    for w in al["warnings"]:
        print(f"    warning: {w}")

    print("\n    mild_steel:")
    ms = get_material("mild_steel")
    for w in ms["warnings"]:
        print(f"    warning: {w}")

    # ------------------------------------------------------------------
    # 3. Find materials by category
    # ------------------------------------------------------------------
    print("\n[3] Aluminum materials:")
    for m in find_materials(category="aluminum"):
        print(f"    {m['id']}")

    # ------------------------------------------------------------------
    # 4. Normalize material names
    # ------------------------------------------------------------------
    print("\n[4] normalize_material examples:")
    for name in ("Aluminum 6061", "mild_steel", "stainless_steel_generic", "unobtainium", None):
        r = normalize_material(name)
        status = "OK" if r["ok"] else "!"
        print(
            f"    [{status}] {str(name):30s}  id={r['material_id']}  "
            f"warnings={r['warnings']}"
        )

    # ------------------------------------------------------------------
    # 5. Build a milling pocket plan with material
    # ------------------------------------------------------------------
    print("\n[5] Building milling pocket OperationPlan with material='aluminum_6061':")
    plan = build_milling_pocket_operation_plan(
        origin_x=0.0,
        origin_y=0.0,
        width=20.0,
        height=10.0,
        depth=3.0,
        tool_diameter=5.0,
        step_down=1.0,
        step_over=2.0,
        safe_z=5.0,
        feedrate=150.0,
        spindle_speed=3000.0,
        material="aluminum_6061",
    )
    print(f"    machine_type: {plan['machine_type']}")
    print(f"    material key: {plan.get('material')}")
    print(f"    assumptions:  {plan['assumptions']}")

    # ------------------------------------------------------------------
    # 6. Evaluate guardrails — valid plan
    # ------------------------------------------------------------------
    print("\n[6] Guardrails for valid aluminum_6061 pocket plan:")
    gr = evaluate_parameter_guardrails(plan, material="aluminum_6061")
    print(f"    ok:       {gr['ok']}")
    print(f"    errors:   {gr['errors']}")
    for w in gr["warnings"]:
        print(f"    warning:  {w}")
    print(f"    material: {gr['material']['name'] if gr['material'] else None}")

    # ------------------------------------------------------------------
    # 7. Guardrails — stainless steel → caution
    # ------------------------------------------------------------------
    print("\n[7] Guardrails for stainless_steel_generic:")
    gr_ss = evaluate_parameter_guardrails(plan, material="stainless_steel_generic")
    print(f"    ok: {gr_ss['ok']}")
    for w in gr_ss["warnings"]:
        print(f"    warning: {w}")

    # ------------------------------------------------------------------
    # 8. Guardrails — no material
    # ------------------------------------------------------------------
    plan_no_mat = build_milling_pocket_operation_plan(
        origin_x=0.0, origin_y=0.0, width=20.0, height=10.0,
        depth=3.0, tool_diameter=5.0, step_down=1.0, step_over=2.0,
        safe_z=5.0, feedrate=150.0, spindle_speed=3000.0,
    )
    print("\n[8] Guardrails without material:")
    gr_nomat = evaluate_parameter_guardrails(plan_no_mat)
    print(f"    ok: {gr_nomat['ok']}")
    for w in gr_nomat["warnings"]:
        print(f"    warning: {w}")

    # ------------------------------------------------------------------
    # 9. Generate G-code with material set
    # ------------------------------------------------------------------
    print("\n[9] Generating pocket G-code with material='aluminum_6061':")
    result = generate_milling_pocket_gcode_from_params(
        origin_x=0.0, origin_y=0.0, width=20.0, height=10.0,
        depth=3.0, tool_diameter=5.0, step_down=1.0, step_over=2.0,
        safe_z=5.0, feedrate=150.0, spindle_speed=3000.0,
        material="aluminum_6061",
    )
    print(f"    ok: {result['ok']}")
    print(f"    operation_plan material: {result['operation_plan'].get('material')}")
    gcode_lines = result["gcode"].splitlines()
    print(f"    G-code lines: {len(gcode_lines)}")
    print(f"    First line:   {gcode_lines[0] if gcode_lines else '(empty)'}")
    print(f"    Last line:    {gcode_lines[-1] if gcode_lines else '(empty)'}")

    print("\n[OK] Demo completed successfully — no API key required.")


if __name__ == "__main__":
    main()
