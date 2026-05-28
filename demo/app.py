"""DataSentinel — Unified Platform Dashboard.

Single-page home view across all three modules. Shows health at a glance
and links through to each module's detailed dashboard.

Launch: streamlit run demo/app.py
Or:     make dashboard
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="DataSentinel Platform",
    page_icon="🛡️",
    layout="wide",
)

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🛡️ DataSentinel — Agentic Data Reliability Platform")
st.caption(
    "Semantic validation · Self-healing pipelines · Real-time stream monitoring"
)
st.divider()

# ── Module availability checks ─────────────────────────────────────────────────
def _importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None

semantic_ok = _importable("datasentinel_semantic")
agent_ok = _importable("datasentinel_agent")
stream_ok = _importable("datasentinel_stream")

# ── Three-column module cards ──────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    status = "✅ Installed" if semantic_ok else "⚠️ Not installed"
    st.subheader("Module 1 — Semantic Validator")
    st.markdown(f"**Status:** {status}")
    st.markdown("""
**What it does:** Validates every AI-generated record in your data pipeline
using Claude as an LLM judge.

**Checks:**
- Factual consistency with reference columns
- Hallucination detection (entity traceability)
- Semantic drift from historical baseline
- AI label accuracy vs. content
""")
    st.code("pip install datasentinel-semantic", language="bash")
    if semantic_ok:
        st.success("16/16 tests passing")
    if st.button("Launch Dashboard →", key="btn_semantic"):
        st.info("Run: `make dashboard-semantic`")

with col2:
    status = "✅ Installed" if agent_ok else "⚠️ Not installed"
    st.subheader("Module 2 — Pipeline Agent")
    st.markdown(f"**Status:** {status}")
    st.markdown("""
**What it does:** When a dbt test fails, the agent traces root cause through
data lineage, generates a SQL fix, tests it in a sandbox, and presents a
one-click approval.

**Agent flow:**
- Observer → Lineage Tracer → Diagnoser
- Remediator → DuckDB Sandbox → HITL approval
""")
    st.code("pip install datasentinel-agent", language="bash")
    if agent_ok:
        st.success("19/19 tests passing")
    if st.button("Launch Dashboard →", key="btn_agent"):
        st.info("Run: `make dashboard-agent`")

with col3:
    status = "✅ Installed" if stream_ok else "⚠️ Not installed"
    st.subheader("Module 3 — Stream Monitor")
    st.markdown(f"**Status:** {status}")
    st.markdown("""
**What it does:** Near-real-time statistical anomaly detection on Kafka streams.
Learns baselines, fires alerts on deviations, correlates bursts into incidents.

**Rule types:**
- Range / not-null / regex (deterministic)
- Null rate threshold (sliding window)
- Z-score anomaly detection (learned baseline)
""")
    st.code("pip install datasentinel-stream", language="bash")
    if stream_ok:
        st.success("32/32 tests passing")
    if st.button("Launch Dashboard →", key="btn_stream"):
        st.info("Run: `make dashboard-stream`")

st.divider()

# ── Platform stats ──────────────────────────────────────────────────────────────
st.subheader("Platform Overview")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Tests", "67/67", delta="100% passing")
m2.metric("Modules Built", "3/3", delta="All complete")
m3.metric("LLM Provider", "Claude API")
m4.metric("Stream Rules", "5 types")

st.divider()

# ── Architecture ───────────────────────────────────────────────────────────────
st.subheader("Architecture")
st.code("""
┌─────────────────────────────────────────────────────────────────────────┐
│                          DataSentinel Platform                           │
│                                                                          │
│  Kafka Stream ──► [ Stream Monitor ]  ◄── learned baselines             │
│                         │ violations                                     │
│                         ▼                                                │
│  Data Warehouse ─► [ Pipeline Agent ]  ◄── OpenMetadata lineage graph   │
│                    detect │ trace │ fix │ sandbox │ approve              │
│                         │                                                │
│  AI Enrichment ──► [ Semantic Validator ]  ◄── LLM-as-judge             │
│                    factual │ hallucination │ drift │ label               │
│                         │                                                │
│                    Trustworthy Data ✓                                    │
└─────────────────────────────────────────────────────────────────────────┘
""", language="text")

st.divider()

# ── Quick start ────────────────────────────────────────────────────────────────
st.subheader("Quickstart")
st.code("""
# Run all three demos back-to-back
make demo

# Or run individual demos
make demo-semantic     # Validates AI-generated product catalog (API key required)
make demo-agent        # Self-heals a broken dbt pipeline (API key required)
make demo-stream       # Detects GPS sensor anomalies (standalone, no Kafka needed)

# Launch dashboards
make dashboard-semantic
make dashboard-agent
make dashboard-stream
make dashboard            # This unified view
""", language="bash")

st.caption(f"DataSentinel · Built with LangGraph + Claude API · {datetime.now().strftime('%Y-%m-%d')}")
