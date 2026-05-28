"""Self-Healing Pipeline Agent demo.

Simulates a dbt pipeline incident:
  - Model: orders_enriched
  - Incident: upstream schema change in raw orders table — the 'payment_amount' column
    was renamed to 'total_amount', causing 847 null failures downstream.

The agent will:
  1. Observe: detect the failing not_null test on 'amount'
  2. Trace: walk lineage to raw.orders_raw, find high null rate there too
  3. Diagnose: classify as schema_drift with high confidence
  4. Remediate: generate a COALESCE / column rename fix
  5. Sandbox: validate the fix in DuckDB
  6. Present: show the fix for approval

Run with: make demo-agent  OR  python demo/scenarios/agent_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages/pipeline-agent/src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "shared/src"))

from datasentinel_agent.graph import run_incident

FAILING_TESTS = [
    {
        "node_name": "not_null_orders_enriched_amount",
        "status": "fail",
        "test_type": "not_null",
        "model": "orders_enriched",
        "column_name": "amount",
        "failures": 847,
        "message": "847 of 10000 records failed the not_null check on 'amount'",
        "compiled_code": "SELECT amount FROM orders_enriched WHERE amount IS NULL",
    }
]


def main() -> None:
    print("\n" + "=" * 65)
    print("  DataSentinel — Self-Healing Pipeline Agent Demo")
    print("  Module 2: Agentic Data Incident Remediation")
    print("=" * 65)
    print("\nIncident:")
    print("  Model:   orders_enriched")
    print("  Test:    not_null on 'amount' — 847 failures")
    print("  Cause:   upstream column rename (payment_amount → total_amount)")
    print("\nRunning agent pipeline...\n")

    final_state = run_incident(
        table_name="orders_enriched",
        failing_tests=FAILING_TESTS,
        dataset_name="analytics",
    )

    print("\n" + "─" * 65)
    print(f"  Incident ID:       {final_state.get('incident_id', '—')}")
    print(f"  Status:            {final_state.get('status', '—')}")
    print(f"  Anomaly Type:      {final_state.get('anomaly_type', '—')}")
    print(f"  Root Cause Table:  {final_state.get('root_cause_table', '—')}")
    print(f"  Root Cause Column: {final_state.get('root_cause_column', '—')}")
    print("─" * 65)

    report = final_state.get("root_cause_report", {})
    if report:
        print(f"\nDiagnosis:")
        print(f"  {report.get('root_cause_explanation', '—')}")

    fix = final_state.get("proposed_fix_sql", "")
    explanation = final_state.get("proposed_fix_explanation", "")
    if fix:
        print(f"\nProposed Fix ({explanation}):")
        print("  " + "\n  ".join(fix.split("\n")))

    sandbox = final_state.get("sandbox_output", {})
    if sandbox:
        passed = sandbox.get("passed", False)
        print(f"\nSandbox Validation: {'PASS ✅' if passed else 'FAIL ❌'}")
        print(f"  Tests run: {sandbox.get('tests_run', 0)}")
        print(f"  Passed:    {sandbox.get('tests_passed', 0)}")
        print(f"  Failed:    {sandbox.get('tests_failed', 0)}")

    status = final_state.get("status")
    if status == "pending_approval":
        print("\n✅ Fix validated in sandbox. Ready for one-click approval.")
        print("   Run `make dashboard-agent` to approve via the UI.")
    elif status == "escalated":
        print("\n⚠️  Could not auto-fix. Incident escalated to data engineering team.")

    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    main()
