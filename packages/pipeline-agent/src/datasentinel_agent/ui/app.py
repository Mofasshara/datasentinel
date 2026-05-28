"""Streamlit HITL approval interface for the Self-Healing Pipeline Agent.

Launch with: make dashboard-agent
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parents[5] / "shared/src"))
sys.path.insert(0, str(Path(__file__).parents[2]))

st.set_page_config(
    page_title="DataSentinel — Pipeline Agent",
    page_icon="🔧",
    layout="wide",
)

st.sidebar.title("🔧 DataSentinel")
st.sidebar.caption("Self-Healing Pipeline Agent — Module 2")
page = st.sidebar.radio("View", ["Run Agent", "Pending Approvals", "About"])


# ── Page: Run Agent ────────────────────────────────────────────────────────────
if page == "Run Agent":
    st.title("Trigger the Self-Healing Pipeline Agent")
    st.markdown(
        "Simulate a dbt test failure and watch the agent trace root cause, "
        "generate a SQL fix, and validate it in a sandbox."
    )

    col1, col2 = st.columns(2)
    with col1:
        table_name = st.text_input("Failing model name", value="orders_enriched")
        dataset_name = st.text_input("Dataset / schema", value="analytics")

    st.subheader("Failing Tests")
    st.markdown("Define the dbt tests that are failing on this model.")

    test_type = st.selectbox("Test type", ["not_null", "unique", "accepted_values", "relationships"])
    col_name = st.text_input("Failing column", value="amount")
    n_failures = st.number_input("Number of failures", min_value=1, value=847)

    failing_tests = [
        {
            "node_name": f"not_null_{table_name}_{col_name}",
            "status": "fail",
            "test_type": test_type,
            "model": table_name,
            "column_name": col_name,
            "failures": int(n_failures),
            "message": f"{n_failures} records failed the {test_type} check on {col_name}",
        }
    ]

    if st.button("▶ Run Agent Pipeline", type="primary"):
        from datasentinel_agent.graph import run_incident

        with st.spinner("Running agent pipeline… observe → trace → diagnose → fix → sandbox"):
            final_state = run_incident(
                table_name=table_name,
                failing_tests=failing_tests,
                dataset_name=dataset_name,
            )

        st.divider()
        status = final_state.get("status", "")
        status_icons = {
            "pending_approval": ("✅", "Fix ready for approval"),
            "escalated": ("⚠️", "Escalated — could not auto-fix"),
            "resolved": ("✅", "Resolved"),
        }
        icon, label = status_icons.get(status, ("ℹ️", status))
        st.markdown(f"## {icon} {label}")

        tabs = st.tabs(["Diagnosis", "Lineage", "Proposed Fix", "Sandbox Result", "Full State"])

        with tabs[0]:
            report = final_state.get("root_cause_report", {})
            st.metric("Anomaly Type", final_state.get("anomaly_type", "—"))
            st.metric("Confidence", f"{final_state.get('diagnosis_confidence', 0):.0%}")
            st.markdown(f"**Root Cause:** {report.get('root_cause_explanation', '—')}")
            st.markdown(f"**Fix Approach:** {report.get('recommended_fix_approach', '—')}")

        with tabs[1]:
            lineage = final_state.get("lineage_graph", {})
            st.markdown(f"**Root Cause Table:** `{final_state.get('root_cause_table', '—')}`")
            st.markdown(f"**Root Cause Column:** `{final_state.get('root_cause_column', '—')}`")
            if lineage.get("_mock"):
                st.info("Using mock lineage (OpenMetadata not running). In production, real lineage is fetched.")
            if lineage.get("edges"):
                st.markdown("**Lineage edges (upstream):**")
                for edge in lineage["edges"]:
                    st.markdown(f"  `{edge['from']}` → `{edge['to']}`")

        with tabs[2]:
            fix_sql = final_state.get("proposed_fix_sql", "")
            explanation = final_state.get("proposed_fix_explanation", "")
            st.markdown(f"**Explanation:** {explanation}")
            if fix_sql:
                st.code(fix_sql, language="sql")
            else:
                st.warning("No fix was generated.")

        with tabs[3]:
            sandbox = final_state.get("sandbox_output", {})
            if sandbox:
                passed = sandbox.get("passed", False)
                st.metric("Sandbox", "PASS ✅" if passed else "FAIL ❌")
                c1, c2, c3 = st.columns(3)
                c1.metric("Tests run", sandbox.get("tests_run", 0))
                c2.metric("Passed", sandbox.get("tests_passed", 0))
                c3.metric("Failed", sandbox.get("tests_failed", 0))
                for detail in sandbox.get("details", []):
                    icon = "✅" if detail.get("passed") else "❌"
                    st.markdown(f"{icon} **{detail['name']}**: {detail.get('description', '')}")

        with tabs[4]:
            st.json({k: v for k, v in final_state.items() if k not in ("lineage_graph",)})

        if status == "pending_approval":
            st.divider()
            st.success("The agent has prepared a validated fix. Review the Proposed Fix tab, then approve or reject.")
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve Fix", type="primary"):
                st.success("Fix approved! In production, this would open a dbt PR.")
            if c2.button("❌ Reject / Escalate"):
                st.warning("Fix rejected. Escalated to the data engineering team.")


# ── Page: Pending Approvals ────────────────────────────────────────────────────
elif page == "Pending Approvals":
    st.title("Incidents Pending Approval")
    st.info("Connect Postgres to view and manage incidents across runs.")
    try:
        from datasentinel_agent.storage.incident_repository import IncidentRepository
        repo = IncidentRepository()
        incidents = repo.list_pending()
        if not incidents:
            st.success("No incidents pending approval.")
        else:
            for inc in incidents:
                with st.expander(f"🔧 {inc['table_name']} — {inc['anomaly_type']} — {inc['created_at']}"):
                    st.markdown(f"**Root Cause:** {inc.get('root_cause', '—')}")
                    st.markdown(f"**Root Cause Table:** `{inc.get('root_cause_table', '—')}`")
                    st.code(inc.get("proposed_fix", ""), language="sql")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Approve", key=f"approve_{inc['incident_id']}"):
                        repo.mark_resolved(inc["incident_id"])
                        st.success("Approved and resolved.")
                    if c2.button("❌ Reject", key=f"reject_{inc['incident_id']}"):
                        repo.mark_rejected(inc["incident_id"])
                        st.warning("Rejected and escalated.")
    except Exception as e:
        st.error(f"Database not available: {e}")


# ── Page: About ────────────────────────────────────────────────────────────────
else:
    st.title("About — Self-Healing Pipeline Agent")
    st.markdown("""
**DataSentinel Pipeline Agent** automatically resolves data pipeline incidents.

**How it works:**
1. **Observer** reads dbt test failures and computes column stats
2. **Lineage Tracer** walks the upstream data lineage graph to find where the anomaly first appeared
3. **Diagnoser** uses Claude to classify the anomaly (schema drift, null spike, logic error, etc.)
4. **Remediator** uses Claude to generate a targeted SQL fix
5. **Sandbox** runs the fix in isolated DuckDB, re-runs the failing assertions
6. If the sandbox passes → presents for **one-click human approval**
7. If the sandbox fails → iterates up to 3 times before escalating

**What makes it different:**
The agent generates *novel SQL fixes for bad data content* — not just rerunning jobs or reverting schemas.
No existing commercial product (Acceldata, SYNQ, FirstEigen) closes this specific loop as of May 2026.
    """)
