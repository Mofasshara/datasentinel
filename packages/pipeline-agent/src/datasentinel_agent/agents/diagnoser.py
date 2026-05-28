"""Diagnoser Agent — classifies the anomaly type and generates a structured root cause report."""
from __future__ import annotations

import json
from typing import Any

from datasentinel_agent.state import IncidentState
from datasentinel_shared.claude_client import ClaudeClient
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)

_ANOMALY_TYPES = [
    "schema_drift",       # upstream column renamed or dropped
    "volume_drop",        # row count collapsed unexpectedly
    "null_spike",         # null rate jumped on a previously clean column
    "distribution_shift", # value distribution changed (different categories, range)
    "logic_error",        # transformation SQL produces wrong output due to a bug
]

_DIAGNOSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "anomaly_type": {"type": "string", "enum": _ANOMALY_TYPES},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "root_cause_explanation": {"type": "string"},
        "evidence": {"type": "object"},
        "recommended_fix_approach": {"type": "string"},
    },
    "required": ["anomaly_type", "confidence", "summary", "root_cause_explanation", "recommended_fix_approach"],
}


def diagnoser_node(state: IncidentState) -> dict[str, Any]:
    """Use Claude to classify the anomaly and produce a structured root cause report."""
    log.info("diagnoser_started", table=state.get("table_name"))

    client = ClaudeClient()
    prompt = _build_diagnosis_prompt(state)

    try:
        result = client.judge(prompt, response_schema=_DIAGNOSIS_SCHEMA)
        log.info(
            "diagnoser_complete",
            anomaly_type=result.get("anomaly_type"),
            confidence=result.get("confidence"),
        )
        return {
            "anomaly_type": result["anomaly_type"],
            "diagnosis_confidence": float(result.get("confidence", 0.5)),
            "root_cause_report": result,
            "status": "fixing",
        }
    except Exception as exc:
        log.error("diagnoser_failed", error=str(exc))
        return {
            "anomaly_type": "logic_error",
            "diagnosis_confidence": 0.0,
            "root_cause_report": {"error": str(exc), "summary": "Diagnosis failed — defaulting to logic_error"},
            "status": "fixing",
        }


def _build_diagnosis_prompt(state: IncidentState) -> str:
    failing_tests = state.get("failing_tests", [])
    column_stats = state.get("column_stats", {})
    root_cause_table = state.get("root_cause_table", state.get("table_name", ""))
    root_cause_column = state.get("root_cause_column", "")
    lineage = state.get("lineage_graph", {})

    tests_summary = json.dumps(failing_tests[:5], indent=2)
    stats_summary = json.dumps(column_stats, indent=2)
    lineage_edges = json.dumps(lineage.get("edges", []), indent=2)

    return f"""You are diagnosing a data quality incident in a data pipeline.

FAILING TABLE: {state.get("table_name")}
ROOT CAUSE TABLE (where anomaly first appeared): {root_cause_table}
ROOT CAUSE COLUMN: {root_cause_column or "unknown"}

FAILING dbt TESTS (up to 5 shown):
{tests_summary}

COLUMN STATISTICS at failing table:
{stats_summary}

LINEAGE (upstream edges):
{lineage_edges}

Classify this incident into one of these anomaly types:
- schema_drift: an upstream column was renamed, removed, or changed type
- volume_drop: row count dropped unexpectedly (source data missing)
- null_spike: null rate jumped on a previously non-null column
- distribution_shift: values are present but distribution changed significantly
- logic_error: the transformation SQL itself has a bug producing wrong output

Provide a concise root_cause_explanation (2-3 sentences) and a recommended_fix_approach
describing the type of SQL change needed to resolve it."""
