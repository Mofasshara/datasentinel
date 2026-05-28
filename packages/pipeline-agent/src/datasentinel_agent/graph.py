"""LangGraph graph for the Self-Healing Pipeline Agent.

Flow:
  observer → lineage_tracer → diagnoser → remediator → sandbox
                                                            │
                              ┌─────────── (failed, retry) ◄┤
                              │                              │
                           remediator              (passed) → END (pending_approval)
                                                  (max iter) → END (escalated)
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from datasentinel_agent.agents import (
    diagnoser_node,
    lineage_tracer_node,
    observer_node,
    remediator_node,
    sandbox_node,
)
from datasentinel_agent.state import IncidentState
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


def _route_after_sandbox(state: IncidentState) -> str:
    """Decide what happens after the sandbox runs."""
    status = state.get("status", "")
    if status == "pending_approval":
        return END
    if status == "escalated":
        return END
    if status == "fixing":
        return "remediator"   # retry loop
    return END


def build_graph() -> Any:
    """Build and compile the LangGraph pipeline."""
    graph = StateGraph(IncidentState)

    graph.add_node("observer", observer_node)
    graph.add_node("lineage_tracer", lineage_tracer_node)
    graph.add_node("diagnoser", diagnoser_node)
    graph.add_node("remediator", remediator_node)
    graph.add_node("sandbox", sandbox_node)

    graph.set_entry_point("observer")

    graph.add_edge("observer", "lineage_tracer")
    graph.add_edge("lineage_tracer", "diagnoser")
    graph.add_edge("diagnoser", "remediator")
    graph.add_edge("remediator", "sandbox")

    graph.add_conditional_edges(
        "sandbox",
        _route_after_sandbox,
        {
            "remediator": "remediator",
            END: END,
        },
    )

    return graph.compile()


def run_incident(
    table_name: str,
    failing_tests: list[dict[str, Any]],
    dataset_name: str = "",
    incident_id: str | None = None,
) -> IncidentState:
    """Convenience entry point: run the full agent pipeline for a dbt incident.

    Args:
        table_name: The failing dbt model name.
        failing_tests: List of dbt test failure dicts (from DbtReader).
        dataset_name: Optional schema/dataset name.
        incident_id: Optional pre-assigned incident ID.

    Returns:
        Final IncidentState after the graph completes.
    """
    pipeline = build_graph()

    initial: IncidentState = {
        "table_name": table_name,
        "failing_tests": failing_tests,
        "dataset_name": dataset_name,
        "incident_id": incident_id or "",
        "iteration_count": 0,
        "status": "observing",
    }

    log.info("incident_pipeline_started", table=table_name, tests=len(failing_tests))
    final_state: IncidentState = pipeline.invoke(initial)
    log.info(
        "incident_pipeline_complete",
        incident_id=final_state.get("incident_id"),
        status=final_state.get("status"),
        anomaly_type=final_state.get("anomaly_type"),
    )
    return final_state
