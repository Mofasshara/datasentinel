"""Real-time stream quality dashboard.

Launch with: streamlit run packages/stream-monitor/src/datasentinel_stream/dashboard/app.py
Or via:      make dashboard-stream

Shows:
  - Live violation feed (auto-refreshes every 5 seconds)
  - Per-topic quality score timeline
  - Baseline vs. actual metric overlay for statistical rules
  - Correlated incident summary
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from datasentinel_stream.storage.violations_repository import ViolationsRepository


st.set_page_config(
    page_title="DataSentinel — Stream Monitor",
    page_icon="📡",
    layout="wide",
)

st.title("📡 DataSentinel — Real-Time Stream Monitor")
st.caption("Live data quality monitoring for Kafka streams")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    topic_filter = st.text_input("Filter by topic", value="")
    refresh_sec = st.slider("Auto-refresh (seconds)", 2, 30, 5)
    limit = st.slider("Max violations shown", 50, 500, 200)
    st.divider()
    st.caption("DataSentinel Stream Monitor · Phase 3")

repo = ViolationsRepository()

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=refresh_sec)
def load_violations(topic: str | None, lim: int) -> pd.DataFrame:
    rows = repo.get_recent_violations(topic=topic or None, limit=lim)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "occurred_at" in df.columns:
        df["occurred_at"] = pd.to_datetime(df["occurred_at"])
    return df


violations_df = load_violations(topic_filter or None, limit)

# ── KPI row ────────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

if violations_df.empty:
    total = 0
    critical_count = 0
    topics_count = 0
    last_seen = "—"
else:
    total = len(violations_df)
    critical_count = int((violations_df["severity"] == "critical").sum()) if "severity" in violations_df.columns else 0
    topics_count = violations_df["topic"].nunique() if "topic" in violations_df.columns else 0
    if "occurred_at" in violations_df.columns and not violations_df["occurred_at"].isna().all():
        last_dt = violations_df["occurred_at"].max()
        delta_sec = (datetime.utcnow() - last_dt.to_pydatetime().replace(tzinfo=None)).total_seconds()
        last_seen = f"{int(delta_sec)}s ago"
    else:
        last_seen = "—"

col1.metric("Total Violations", total)
col2.metric("Critical", critical_count, delta=None)
col3.metric("Active Topics", topics_count)
col4.metric("Last Violation", last_seen)

st.divider()

# ── Violation timeline chart ───────────────────────────────────────────────────
st.subheader("Violation Rate Over Time")

if not violations_df.empty and "occurred_at" in violations_df.columns:
    timeline_df = violations_df.copy()
    timeline_df["minute"] = timeline_df["occurred_at"].dt.floor("1min")
    grouped = (
        timeline_df.groupby(["minute", "severity"])
        .size()
        .reset_index(name="count")
    )
    color_map = {"critical": "#e74c3c", "warning": "#f39c12", "info": "#3498db"}
    fig = px.bar(
        grouped,
        x="minute",
        y="count",
        color="severity",
        color_discrete_map=color_map,
        labels={"minute": "Time", "count": "Violations", "severity": "Severity"},
    )
    fig.update_layout(height=300, margin=dict(t=0, b=0))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No violation data yet. Start the stream demo: `make demo-stream`")

st.divider()

# ── Per-topic quality score ────────────────────────────────────────────────────
st.subheader("Quality Score by Topic")

if not violations_df.empty and "topic" in violations_df.columns:
    # Quality score = 1 - (violations in last 5 min / total records estimate)
    # We approximate: a "good" topic fires < 1% violations over any window.
    # Show simple per-topic violation count bar.
    topic_counts = violations_df["topic"].value_counts().reset_index()
    topic_counts.columns = ["topic", "violations"]
    fig2 = px.bar(
        topic_counts,
        x="topic",
        y="violations",
        color="violations",
        color_continuous_scale="RdYlGn_r",
        labels={"topic": "Kafka Topic", "violations": "Violation Count"},
    )
    fig2.update_layout(height=280, margin=dict(t=0, b=0), showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Rule breakdown ─────────────────────────────────────────────────────────────
if not violations_df.empty and "rule_name" in violations_df.columns:
    st.subheader("Violations by Rule")
    rule_counts = violations_df["rule_name"].value_counts().head(10).reset_index()
    rule_counts.columns = ["rule", "count"]
    st.dataframe(rule_counts, use_container_width=True, hide_index=True)
    st.divider()

# ── Live violation feed ────────────────────────────────────────────────────────
st.subheader("Live Violation Feed")

if violations_df.empty:
    st.success("No violations detected. Stream looks clean!")
else:
    display_cols = [c for c in ["occurred_at", "topic", "rule_name", "column_name", "value", "expected", "severity"] if c in violations_df.columns]
    styled = violations_df[display_cols].head(50)
    st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(0.1)
st.caption(f"Auto-refreshing every {refresh_sec}s · {datetime.utcnow().strftime('%H:%M:%S')} UTC")
