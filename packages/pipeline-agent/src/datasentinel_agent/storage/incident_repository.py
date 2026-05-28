"""Postgres persistence for pipeline incidents."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from datasentinel_agent.state import IncidentState
from datasentinel_shared.config import get_settings
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


class IncidentRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        if engine is None:
            settings = get_settings()
            engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
        self._engine = engine

    def upsert(self, state: IncidentState) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO pipeline_incidents
                        (incident_id, table_name, anomaly_type, root_cause, root_cause_table,
                         status, proposed_fix, sandbox_result, created_at)
                    VALUES
                        (:incident_id, :table_name, :anomaly_type, :root_cause, :root_cause_table,
                         :status, :proposed_fix, :sandbox_result::jsonb, :created_at)
                    ON CONFLICT (incident_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        anomaly_type = EXCLUDED.anomaly_type,
                        root_cause = EXCLUDED.root_cause,
                        root_cause_table = EXCLUDED.root_cause_table,
                        proposed_fix = EXCLUDED.proposed_fix,
                        sandbox_result = EXCLUDED.sandbox_result
                """),
                {
                    "incident_id": state.get("incident_id", ""),
                    "table_name": state.get("table_name", ""),
                    "anomaly_type": state.get("anomaly_type", ""),
                    "root_cause": state.get("root_cause_report", {}).get("root_cause_explanation", ""),
                    "root_cause_table": state.get("root_cause_table", ""),
                    "status": state.get("status", "open"),
                    "proposed_fix": state.get("proposed_fix_sql", ""),
                    "sandbox_result": json.dumps(state.get("sandbox_output", {})),
                    "created_at": datetime.now(tz=timezone.utc),
                },
            )
        log.info("incident_saved", incident_id=state.get("incident_id"), status=state.get("status"))

    def mark_resolved(self, incident_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE pipeline_incidents
                    SET status = 'resolved', resolved_at = NOW()
                    WHERE incident_id = :incident_id
                """),
                {"incident_id": incident_id},
            )

    def mark_rejected(self, incident_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE pipeline_incidents SET status = 'escalated' WHERE incident_id = :id"),
                {"id": incident_id},
            )

    def list_pending(self) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT incident_id, table_name, anomaly_type, root_cause,
                           root_cause_table, status, proposed_fix, sandbox_result, created_at
                    FROM pipeline_incidents
                    WHERE status = 'pending_approval'
                    ORDER BY created_at DESC
                """)
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get(self, incident_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM pipeline_incidents WHERE incident_id = :id"),
                {"id": incident_id},
            ).fetchone()
        return dict(row._mapping) if row else None
