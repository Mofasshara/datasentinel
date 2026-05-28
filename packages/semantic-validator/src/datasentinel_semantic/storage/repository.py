from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from datasentinel_semantic.core.expectation import ExpectationResult, Verdict
from datasentinel_semantic.suite import SuiteResult
from datasentinel_shared.config import get_settings
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


class ResultRepository:
    """Persists suite and expectation results to Postgres."""

    def __init__(self, engine: Engine | None = None) -> None:
        if engine is None:
            settings = get_settings()
            engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
        self._engine = engine

    def save_suite_result(self, suite_result: SuiteResult, dataset_name: str = "") -> None:
        with self._engine.begin() as conn:
            for result in suite_result.results:
                self._insert_expectation_result(
                    conn,
                    suite_result=suite_result,
                    result=result,
                    dataset_name=dataset_name,
                )
                self._insert_verdicts(conn, run_id=suite_result.run_id, result=result)

        log.info("results_saved", suite=suite_result.suite_name, run_id=suite_result.run_id)

    def _insert_expectation_result(
        self,
        conn: object,
        *,
        suite_result: SuiteResult,
        result: ExpectationResult,
        dataset_name: str,
    ) -> None:
        conn.execute(  # type: ignore[attr-defined]
            text("""
                INSERT INTO semantic_expectation_results
                    (run_id, suite_name, expectation, column_name, dataset_name,
                     total_records, passed_records, failed_records, pass_rate, run_at, metadata)
                VALUES
                    (:run_id, :suite_name, :expectation, :column_name, :dataset_name,
                     :total_records, :passed_records, :failed_records, :pass_rate, :run_at, :metadata::jsonb)
            """),
            {
                "run_id": suite_result.run_id,
                "suite_name": suite_result.suite_name,
                "expectation": result.expectation_name,
                "column_name": result.column_name,
                "dataset_name": dataset_name,
                "total_records": result.total_records,
                "passed_records": result.passed_records,
                "failed_records": result.failed_records,
                "pass_rate": result.pass_rate,
                "run_at": suite_result.run_at,
                "metadata": json.dumps({}),
            },
        )

    def _insert_verdicts(
        self,
        conn: object,
        *,
        run_id: str,
        result: ExpectationResult,
    ) -> None:
        for v in result.verdicts:
            conn.execute(  # type: ignore[attr-defined]
                text("""
                    INSERT INTO semantic_verdicts
                        (run_id, expectation, column_name, record_index,
                         passed, confidence, reason, evidence)
                    VALUES
                        (:run_id, :expectation, :column_name, :record_index,
                         :passed, :confidence, :reason, :evidence::jsonb)
                """),
                {
                    "run_id": run_id,
                    "expectation": result.expectation_name,
                    "column_name": result.column_name,
                    "record_index": v.record_index,
                    "passed": v.passed,
                    "confidence": v.confidence,
                    "reason": v.reason,
                    "evidence": json.dumps(v.evidence),
                },
            )

    def get_pass_rate_history(
        self,
        suite_name: str,
        column_name: str,
        expectation: str,
        limit: int = 30,
    ) -> list[dict[str, object]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT run_at, pass_rate, total_records, failed_records
                    FROM semantic_expectation_results
                    WHERE suite_name = :suite AND column_name = :col AND expectation = :exp
                    ORDER BY run_at DESC
                    LIMIT :limit
                """),
                {"suite": suite_name, "col": column_name, "exp": expectation, "limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
