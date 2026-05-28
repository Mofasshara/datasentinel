"""Postgres persistence for stream violations and baseline snapshots."""
from __future__ import annotations

import json
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False

from datasentinel_shared.logging import get_logger

logger = get_logger(__name__)


class ViolationsRepository:
    """Persist stream violations and baseline snapshots to Postgres.

    Degrades gracefully when Postgres is unavailable — violations are
    logged but not stored, so the operators keep running.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        self._conn = None

    def _get_conn(self):
        if not _PSYCOPG2_AVAILABLE:
            return None
        if self._conn is None or self._conn.closed:
            try:
                dsn = self._dsn
                if dsn is None:
                    from datasentinel_shared.config import get_settings
                    dsn = get_settings().postgres_dsn
                self._conn = psycopg2.connect(dsn)
            except Exception as exc:
                logger.warning("postgres_unavailable", error=str(exc))
                return None
        return self._conn

    def save_violation(self, violation: dict) -> None:
        conn = self._get_conn()
        if conn is None:
            logger.debug("violation_not_persisted", rule=violation.get("rule_name"))
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stream_violations
                        (topic, rule_name, column_name, value, expected,
                         severity, z_score, record_id, occurred_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        violation.get("topic"),
                        violation.get("rule_name"),
                        violation.get("column"),
                        str(violation.get("value", "")),
                        violation.get("expected", ""),
                        violation.get("severity", "warning"),
                        violation.get("z_score"),
                        violation.get("record_id", ""),
                        violation.get("timestamp"),
                    ),
                )
            conn.commit()
        except Exception as exc:
            logger.error("violation_persist_failed", error=str(exc))
            conn.rollback()

    def save_baseline_snapshot(self, topic: str, snapshot: dict) -> None:
        conn = self._get_conn()
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                for rule_name, stats in snapshot.items():
                    cur.execute(
                        """
                        INSERT INTO stream_baselines
                            (topic, rule_name, mean_value, std_value, sample_count,
                             warmed_up, snapshot_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (topic, rule_name) DO UPDATE SET
                            mean_value = EXCLUDED.mean_value,
                            std_value  = EXCLUDED.std_value,
                            sample_count = EXCLUDED.sample_count,
                            warmed_up  = EXCLUDED.warmed_up,
                            snapshot_at = EXCLUDED.snapshot_at
                        """,
                        (
                            topic,
                            rule_name,
                            stats.get("mean"),
                            stats.get("std"),
                            stats.get("n"),
                            stats.get("warmed_up", False),
                            datetime.utcnow().isoformat(),
                        ),
                    )
            conn.commit()
        except Exception as exc:
            logger.error("baseline_persist_failed", error=str(exc))
            conn.rollback()

    def get_recent_violations(
        self,
        topic: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        conn = self._get_conn()
        if conn is None:
            return []
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if topic:
                    cur.execute(
                        "SELECT * FROM stream_violations WHERE topic = %s "
                        "ORDER BY occurred_at DESC LIMIT %s",
                        (topic, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM stream_violations "
                        "ORDER BY occurred_at DESC LIMIT %s",
                        (limit,),
                    )
                return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            logger.error("violations_fetch_failed", error=str(exc))
            return []
