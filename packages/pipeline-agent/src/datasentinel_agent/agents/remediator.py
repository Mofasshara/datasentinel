"""Remediator Agent — generates a targeted SQL fix based on the diagnosis."""
from __future__ import annotations

import re
from typing import Any

from datasentinel_agent.state import IncidentState
from datasentinel_shared.claude_client import ClaudeClient
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


def remediator_node(state: IncidentState) -> dict[str, Any]:
    """Generate a SQL fix for the diagnosed anomaly."""
    log.info(
        "remediator_started",
        anomaly_type=state.get("anomaly_type"),
        iteration=state.get("iteration_count", 0),
    )

    client = ClaudeClient()
    prompt = _build_fix_prompt(state)

    try:
        raw = client.complete(prompt, temperature=0.0)
        fix_sql, explanation = _parse_fix_response(raw)

        log.info("remediator_complete", fix_length=len(fix_sql))
        return {
            "proposed_fix_sql": fix_sql,
            "proposed_fix_explanation": explanation,
            "iteration_count": state.get("iteration_count", 0),
            "status": "sandbox",
        }
    except Exception as exc:
        log.error("remediator_failed", error=str(exc))
        return {
            "proposed_fix_sql": "",
            "proposed_fix_explanation": f"Fix generation failed: {exc}",
            "status": "escalated",
        }


def _build_fix_prompt(state: IncidentState) -> str:
    anomaly_type = state.get("anomaly_type", "logic_error")
    root_cause_report = state.get("root_cause_report", {})
    failing_tests = state.get("failing_tests", [])
    table_name = state.get("table_name", "")
    root_cause_col = state.get("root_cause_column", "")
    iteration = state.get("iteration_count", 0)
    prev_result = state.get("sandbox_output", {})

    lines = [
        f"Generate a minimal SQL fix for the following data pipeline incident.",
        f"",
        f"FAILING MODEL: {table_name}",
        f"ANOMALY TYPE: {anomaly_type}",
        f"ROOT CAUSE COLUMN: {root_cause_col or 'unknown'}",
        f"",
        f"DIAGNOSIS:",
        root_cause_report.get("root_cause_explanation", ""),
        f"",
        f"RECOMMENDED FIX APPROACH:",
        root_cause_report.get("recommended_fix_approach", ""),
        f"",
        f"FAILING TESTS:",
    ]

    for t in failing_tests[:3]:
        lines.append(f"  - {t.get('node_name', '')}: {t.get('test_type', '')} on {t.get('column_name', '')}")

    if iteration > 0 and prev_result:
        lines += [
            f"",
            f"PREVIOUS FIX ATTEMPT (iteration {iteration}) FAILED. Remaining failures:",
        ]
        for detail in prev_result.get("details", []):
            if not detail.get("passed"):
                lines.append(f"  - {detail['name']}: {detail.get('failures', 0)} failing rows")

    lines += [
        f"",
        "Write the corrected SQL as a complete SELECT statement (the fixed dbt model body).",
        "Use COALESCE, NULLIF, CASE WHEN, or JOIN fixes as appropriate for the anomaly type.",
        "",
        "Respond in this exact format:",
        "EXPLANATION: <one sentence explaining what the fix does>",
        "```sql",
        "<your corrected SQL here>",
        "```",
    ]

    return "\n".join(lines)


def _parse_fix_response(raw: str) -> tuple[str, str]:
    """Extract explanation and SQL from the LLM response."""
    explanation = ""
    exp_match = re.search(r"EXPLANATION:\s*(.+?)(?:\n|```)", raw, re.IGNORECASE | re.DOTALL)
    if exp_match:
        explanation = exp_match.group(1).strip()

    sql_match = re.search(r"```sql\s*\n(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip(), explanation

    # Fallback: try to find any SQL-looking block
    lines = [l for l in raw.split("\n") if l.strip().upper().startswith(("SELECT", "WITH", "CREATE", "INSERT"))]
    if lines:
        return "\n".join(lines), explanation

    return raw, explanation
