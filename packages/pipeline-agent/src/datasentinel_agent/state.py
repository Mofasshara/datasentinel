"""LangGraph state for the Self-Healing Pipeline Agent."""
from __future__ import annotations

from typing import Any, TypedDict


class IncidentState(TypedDict, total=False):
    # ── Incident identity ──────────────────────────────────────────────────
    incident_id: str
    table_name: str                  # the failing dbt model / table
    dataset_name: str                # dataset / schema

    # ── Observer output ────────────────────────────────────────────────────
    failing_tests: list[dict[str, Any]]   # raw dbt test failure records
    column_stats: dict[str, Any]          # null rate, row count, etc. at failing table

    # ── Lineage Tracer output ──────────────────────────────────────────────
    lineage_graph: dict[str, Any]         # upstream tables keyed by table name
    root_cause_table: str                 # table where anomaly first appeared
    root_cause_column: str                # column at root cause table

    # ── Diagnoser output ───────────────────────────────────────────────────
    anomaly_type: str                     # schema_drift | volume_drop | null_spike | distribution_shift | logic_error
    diagnosis_confidence: float
    root_cause_report: dict[str, Any]     # structured diagnosis

    # ── Remediator output ──────────────────────────────────────────────────
    proposed_fix_sql: str                 # the SQL patch
    proposed_fix_explanation: str        # plain-English explanation for the human

    # ── Sandbox output ─────────────────────────────────────────────────────
    sandbox_passed: bool
    sandbox_output: dict[str, Any]        # test results after applying fix
    iteration_count: int

    # ── Resolution ─────────────────────────────────────────────────────────
    status: str   # observing | tracing | diagnosing | fixing | sandbox | pending_approval | resolved | escalated
    error: str    # non-empty if an agent step failed
