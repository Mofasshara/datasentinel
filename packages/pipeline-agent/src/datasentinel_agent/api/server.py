"""FastAPI server — exposes incident management endpoints for the HITL approval UI."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from datasentinel_agent.graph import run_incident
from datasentinel_agent.storage.incident_repository import IncidentRepository

app = FastAPI(
    title="DataSentinel Pipeline Agent",
    description="Self-healing pipeline incident API",
    version="0.1.0",
)

_repo = IncidentRepository()


class RunIncidentRequest(BaseModel):
    table_name: str
    failing_tests: list[dict[str, Any]]
    dataset_name: str = ""


@app.post("/incidents/run", summary="Trigger the full agent pipeline for a dbt incident")
async def trigger_incident(req: RunIncidentRequest) -> dict[str, Any]:
    final_state = run_incident(
        table_name=req.table_name,
        failing_tests=req.failing_tests,
        dataset_name=req.dataset_name,
    )
    try:
        _repo.upsert(final_state)
    except Exception:
        pass  # DB may not be available in dev — still return the result

    return {
        "incident_id": final_state.get("incident_id"),
        "status": final_state.get("status"),
        "anomaly_type": final_state.get("anomaly_type"),
        "root_cause_table": final_state.get("root_cause_table"),
        "proposed_fix_explanation": final_state.get("proposed_fix_explanation"),
        "sandbox_passed": final_state.get("sandbox_passed"),
    }


@app.get("/incidents", summary="List incidents pending human approval")
async def list_incidents() -> list[dict[str, Any]]:
    try:
        return _repo.list_pending()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")


@app.get("/incidents/{incident_id}", summary="Get a specific incident")
async def get_incident(incident_id: str) -> dict[str, Any]:
    incident = _repo.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.post("/incidents/{incident_id}/approve", summary="Approve and deploy the proposed fix")
async def approve_incident(incident_id: str) -> dict[str, str]:
    incident = _repo.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident["status"] != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Incident is in status '{incident['status']}', not pending_approval")

    # In production: apply the fix to the actual warehouse / create a PR
    # For now: mark resolved and return the fix SQL for manual application
    _repo.mark_resolved(incident_id)
    return {
        "status": "resolved",
        "message": "Fix approved. In production this would open a dbt PR or apply the SQL directly.",
        "fix_sql": incident.get("proposed_fix", ""),
    }


@app.post("/incidents/{incident_id}/reject", summary="Reject the proposed fix and escalate")
async def reject_incident(incident_id: str) -> dict[str, str]:
    incident = _repo.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    _repo.mark_rejected(incident_id)
    return {"status": "escalated", "message": "Fix rejected. Incident escalated to the data engineering team."}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
