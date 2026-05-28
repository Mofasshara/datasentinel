"""Streamlit dashboard for the DataSentinel Semantic Validator.

Launch with: streamlit run packages/semantic-validator/src/datasentinel_semantic/dashboard/app.py
Or via:      make dashboard-semantic
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Allow running without full install during development
sys.path.insert(0, str(Path(__file__).parents[5] / "shared" / "src"))
sys.path.insert(0, str(Path(__file__).parents[2]))

st.set_page_config(
    page_title="DataSentinel — Semantic Validator",
    page_icon="🛡️",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("🛡️ DataSentinel")
st.sidebar.caption("Semantic Validator — Module 1")
page = st.sidebar.radio("View", ["Run Validation", "History", "About"])

# ── Page: Run Validation ──────────────────────────────────────────────────────
if page == "Run Validation":
    st.title("Run Semantic Validation")
    st.markdown(
        "Upload a CSV containing AI-generated columns and configure which checks to run."
    )

    uploaded = st.file_uploader("Upload dataset (CSV)", type=["csv"])

    if uploaded:
        df = pd.read_csv(uploaded)
        st.subheader(f"Dataset preview — {len(df):,} rows")
        st.dataframe(df.head(10), use_container_width=True)

        cols = list(df.columns)

        st.divider()
        st.subheader("Configure Checks")

        checks: list[dict] = []

        with st.expander("✅ Factual Consistency", expanded=True):
            fc_enabled = st.checkbox("Enable", key="fc_enabled")
            if fc_enabled:
                fc_col = st.selectbox("AI-generated column", cols, key="fc_col")
                fc_ref = st.selectbox("Reference column", cols, key="fc_ref")
                fc_thresh = st.slider("Pass rate threshold", 0.5, 1.0, 0.95, 0.01, key="fc_thresh")
                checks.append({"type": "factual_consistency", "column": fc_col, "reference_column": fc_ref, "threshold": fc_thresh})

        with st.expander("🔍 Hallucination Detection"):
            hd_enabled = st.checkbox("Enable", key="hd_enabled")
            if hd_enabled:
                hd_col = st.selectbox("AI-generated column", cols, key="hd_col")
                hd_sources = st.multiselect("Source columns to verify against", cols, key="hd_sources")
                hd_thresh = st.slider("Pass rate threshold", 0.5, 1.0, 0.95, 0.01, key="hd_thresh")
                if hd_sources:
                    checks.append({"type": "hallucination_detection", "column": hd_col, "source_columns": hd_sources, "threshold": hd_thresh})

        with st.expander("📉 Semantic Drift"):
            sd_enabled = st.checkbox("Enable", key="sd_enabled")
            if sd_enabled:
                sd_col = st.selectbox("AI-generated column", cols, key="sd_col")
                sd_thresh = st.slider("Max drift threshold", 0.0, 0.5, 0.15, 0.01, key="sd_thresh")
                checks.append({"type": "semantic_drift", "column": sd_col, "threshold": sd_thresh})

        with st.expander("🏷️ Label Accuracy"):
            la_enabled = st.checkbox("Enable", key="la_enabled")
            if la_enabled:
                la_col = st.selectbox("Label column", cols, key="la_col")
                la_content = st.selectbox("Content column", cols, key="la_content")
                la_thresh = st.slider("Pass rate threshold", 0.5, 1.0, 0.90, 0.01, key="la_thresh")
                checks.append({"type": "label_accuracy", "column": la_col, "content_column": la_content, "threshold": la_thresh})

        sample_size = st.number_input("Sample size (0 = use all rows)", min_value=0, max_value=len(df), value=min(50, len(df)))

        if checks and st.button("▶ Run Validation", type="primary"):
            from datasentinel_semantic.expectations import (
                FactualConsistencyExpectation,
                HallucinationDetectionExpectation,
                LabelAccuracyExpectation,
                SemanticDriftExpectation,
            )
            from datasentinel_semantic.suite import SemanticExpectationSuite

            _EXP_MAP = {
                "factual_consistency": FactualConsistencyExpectation,
                "hallucination_detection": HallucinationDetectionExpectation,
                "label_accuracy": LabelAccuracyExpectation,
                "semantic_drift": SemanticDriftExpectation,
            }

            suite = SemanticExpectationSuite(name="dashboard_run")
            for check in checks:
                cls = _EXP_MAP[check.pop("type")]
                suite.add(cls(**check))

            with st.spinner("Running validation… (this calls Claude for each record)"):
                result = suite.run(df, sample_size=int(sample_size) if sample_size else None)

            st.divider()
            overall_status = "✅ PASS" if result.passed else "❌ FAIL"
            st.markdown(f"## Result: {overall_status}")
            st.metric("Overall pass rate", f"{result.overall_pass_rate:.1%}")

            for r in result.results:
                status_icon = "✅" if r.passed else "❌"
                with st.expander(f"{status_icon} {r.expectation_name}({r.column_name}) — {r.pass_rate:.1%}"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total records", r.total_records)
                    col2.metric("Passed", r.passed_records)
                    col3.metric("Failed", r.failed_records)

                    if r.verdicts:
                        st.markdown("**Sample failures:**")
                        for v in r.verdicts[:10]:
                            st.warning(f"Row {v.record_index}: {v.reason}")
                            if v.evidence:
                                st.json(v.evidence)

# ── Page: History ─────────────────────────────────────────────────────────────
elif page == "History":
    st.title("Validation History")
    st.info("Connect Postgres (set ANTHROPIC_API_KEY and Postgres env vars) to view historical pass rates and drift trends.")

    try:
        from datasentinel_semantic.storage import ResultRepository
        repo = ResultRepository()

        suite_name = st.text_input("Suite name", value="dashboard_run")
        col_name = st.text_input("Column name", value="ai_description")
        exp_name = st.selectbox("Expectation", [
            "expect_column_to_be_factually_consistent_with",
            "expect_column_to_not_hallucinate_entities",
            "expect_semantic_drift_below",
            "expect_label_to_match_content",
        ])

        history = repo.get_pass_rate_history(suite_name, col_name, exp_name)
        if history:
            hist_df = pd.DataFrame(history)
            st.line_chart(hist_df.set_index("run_at")["pass_rate"])
            st.dataframe(hist_df, use_container_width=True)
        else:
            st.info("No history found for this combination.")
    except Exception as e:
        st.error(f"Could not connect to Postgres: {e}")

# ── Page: About ───────────────────────────────────────────────────────────────
else:
    st.title("About DataSentinel")
    st.markdown("""
**DataSentinel Semantic Validator** is an open-source Python library that validates
the semantic correctness of AI-generated data in your pipelines.

**Available checks:**
- **Factual Consistency** — AI text must not contradict a reference field
- **Hallucination Detection** — entities in AI text must be traceable to source data
- **Semantic Drift** — embedding-based detection of output character shifts over time
- **Label Accuracy** — AI-assigned classifications must match the record content

**Install:**
```bash
pip install datasentinel-semantic
```

**Quick start:**
```python
from datasentinel_semantic import SemanticExpectationSuite
from datasentinel_semantic.expectations import FactualConsistencyExpectation

suite = SemanticExpectationSuite(name="my_pipeline")
suite.add(FactualConsistencyExpectation(column="ai_description", reference_column="spec"))
result = suite.run(df)
print(result.summary())
```

[GitHub](https://github.com/yourusername/datasentinel) | [Roadmap](ROADMAP.md)
    """)
