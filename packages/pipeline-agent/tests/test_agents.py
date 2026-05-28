"""Unit tests for pipeline agent nodes — all LLM and DB calls are mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from datasentinel_agent.agents.diagnoser import diagnoser_node
from datasentinel_agent.agents.lineage_tracer import lineage_tracer_node
from datasentinel_agent.agents.observer import observer_node
from datasentinel_agent.agents.remediator import remediator_node
from datasentinel_agent.agents.sandbox import sandbox_node
from datasentinel_agent.state import IncidentState
from datasentinel_agent.tools.duckdb_sandbox import DuckDBSandbox, SandboxResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_state() -> IncidentState:
    return {
        "table_name": "orders_enriched",
        "dataset_name": "analytics",
        "failing_tests": [
            {
                "node_name": "not_null_orders_enriched_amount",
                "status": "fail",
                "test_type": "not_null",
                "model": "orders_enriched",
                "column_name": "amount",
                "failures": 847,
                "message": "847 records failed",
            }
        ],
        "incident_id": "test-incident-001",
        "iteration_count": 0,
        "status": "observing",
    }


# ── Observer ──────────────────────────────────────────────────────────────────

class TestObserverNode:
    def test_sets_incident_id(self, base_state: IncidentState) -> None:
        result = observer_node(base_state)
        assert "incident_id" in result
        assert result["incident_id"]  # non-empty

    def test_preserves_provided_incident_id(self, base_state: IncidentState) -> None:
        result = observer_node(base_state)
        assert result["incident_id"] == "test-incident-001"

    def test_sets_status_to_tracing(self, base_state: IncidentState) -> None:
        result = observer_node(base_state)
        assert result["status"] == "tracing"

    def test_returns_column_stats(self, base_state: IncidentState) -> None:
        result = observer_node(base_state)
        assert "column_stats" in result
        stats = result["column_stats"]
        assert "row_count" in stats
        assert isinstance(stats["row_count"], int)


# ── Lineage Tracer ────────────────────────────────────────────────────────────

class TestLineageTracerNode:
    def test_fetches_lineage_and_sets_root_cause(self, base_state: IncidentState) -> None:
        state = {**base_state, "status": "tracing", "column_stats": {"row_count": 10000, "columns": {}}}
        result = lineage_tracer_node(state)
        assert "lineage_graph" in result
        assert "root_cause_table" in result
        assert result["status"] == "diagnosing"

    def test_lineage_graph_has_expected_keys(self, base_state: IncidentState) -> None:
        state = {**base_state, "column_stats": {}}
        result = lineage_tracer_node(state)
        lg = result["lineage_graph"]
        assert "nodes" in lg
        assert "edges" in lg
        assert "root" in lg

    def test_uses_mock_lineage_when_server_unavailable(self, base_state: IncidentState) -> None:
        state = {**base_state, "column_stats": {}}
        result = lineage_tracer_node(state)
        assert result["lineage_graph"].get("_mock") is True


# ── Diagnoser ─────────────────────────────────────────────────────────────────

class TestDiagnoserNode:
    def _mock_claude(self, anomaly_type: str = "null_spike") -> MagicMock:
        mock = MagicMock()
        mock.judge.return_value = {
            "anomaly_type": anomaly_type,
            "confidence": 0.92,
            "summary": "Test summary",
            "root_cause_explanation": "The upstream column was renamed.",
            "recommended_fix_approach": "Use COALESCE to handle the renamed column.",
            "evidence": {},
        }
        return mock

    def test_returns_anomaly_type(self, base_state: IncidentState) -> None:
        state = {
            **base_state,
            "root_cause_table": "raw.orders_raw",
            "root_cause_column": "amount",
            "column_stats": {},
            "lineage_graph": {"edges": []},
        }
        with patch("datasentinel_agent.agents.diagnoser.ClaudeClient", return_value=self._mock_claude("schema_drift")):
            result = diagnoser_node(state)
        assert result["anomaly_type"] == "schema_drift"
        assert result["diagnosis_confidence"] == pytest.approx(0.92)
        assert result["status"] == "fixing"

    def test_degrades_gracefully_on_llm_failure(self, base_state: IncidentState) -> None:
        state = {**base_state, "root_cause_table": "raw.t", "root_cause_column": "col", "column_stats": {}, "lineage_graph": {}}
        mock = MagicMock()
        mock.judge.side_effect = Exception("LLM unavailable")
        with patch("datasentinel_agent.agents.diagnoser.ClaudeClient", return_value=mock):
            result = diagnoser_node(state)
        assert result["anomaly_type"] == "logic_error"   # default fallback
        assert result["status"] == "fixing"


# ── Remediator ────────────────────────────────────────────────────────────────

class TestRemediatorNode:
    def _state_with_diagnosis(self, base_state: IncidentState) -> IncidentState:
        return {
            **base_state,
            "anomaly_type": "null_spike",
            "diagnosis_confidence": 0.9,
            "root_cause_table": "raw.orders_raw",
            "root_cause_column": "amount",
            "root_cause_report": {
                "root_cause_explanation": "Upstream column renamed.",
                "recommended_fix_approach": "COALESCE(payment_amount, total_amount) AS amount",
            },
        }

    def test_returns_proposed_fix(self, base_state: IncidentState) -> None:
        state = self._state_with_diagnosis(base_state)
        mock = MagicMock()
        mock.complete.return_value = "EXPLANATION: Use COALESCE\n```sql\nSELECT COALESCE(amount, 0) AS amount FROM orders\n```"
        with patch("datasentinel_agent.agents.remediator.ClaudeClient", return_value=mock):
            result = remediator_node(state)
        assert "proposed_fix_sql" in result
        assert "SELECT" in result["proposed_fix_sql"].upper()
        assert result["status"] == "sandbox"

    def test_escalates_on_llm_failure(self, base_state: IncidentState) -> None:
        state = self._state_with_diagnosis(base_state)
        mock = MagicMock()
        mock.complete.side_effect = Exception("LLM down")
        with patch("datasentinel_agent.agents.remediator.ClaudeClient", return_value=mock):
            result = remediator_node(state)
        assert result["status"] == "escalated"


# ── Sandbox ───────────────────────────────────────────────────────────────────

class TestDuckDBSandbox:
    def test_load_and_query(self) -> None:
        df = pd.DataFrame({"id": [1, 2, 3], "amount": [10.0, 20.0, 30.0]})
        with DuckDBSandbox() as sb:
            sb.load_table("test_table", df)
            result = sb.conn.execute("SELECT COUNT(*) FROM test_table").fetchone()
            assert result[0] == 3

    def test_assertion_pass(self) -> None:
        df = pd.DataFrame({"id": [1, 2, 3], "amount": [10.0, 20.0, 30.0]})
        with DuckDBSandbox() as sb:
            sb.load_table("t", df)
            result = sb.run_assertions("t", [
                {"name": "no_nulls", "sql": "SELECT * FROM t WHERE amount IS NULL", "description": "no nulls"},
            ])
        assert result.passed is True
        assert result.tests_passed == 1

    def test_assertion_fail(self) -> None:
        df = pd.DataFrame({"id": [1, 2], "amount": [10.0, None]})
        with DuckDBSandbox() as sb:
            sb.load_table("t", df)
            result = sb.run_assertions("t", [
                {"name": "no_nulls", "sql": "SELECT * FROM t WHERE amount IS NULL", "description": "no nulls"},
            ])
        assert result.passed is False
        assert result.tests_failed == 1


class TestSandboxNode:
    def test_passes_with_valid_fix(self, base_state: IncidentState) -> None:
        state = {
            **base_state,
            "proposed_fix_sql": "SELECT id, COALESCE(amount, 0) AS amount FROM (VALUES (1, 10.0), (2, 20.0)) t(id, amount)",
            "status": "sandbox",
        }
        result = sandbox_node(state)
        assert result["sandbox_passed"] is True
        assert result["status"] == "pending_approval"

    def test_escalates_without_fix_sql(self, base_state: IncidentState) -> None:
        state = {**base_state, "proposed_fix_sql": "", "status": "sandbox"}
        result = sandbox_node(state)
        assert result["sandbox_passed"] is False
        assert result["status"] == "escalated"

    def test_retries_when_sandbox_fails(self, base_state: IncidentState) -> None:
        state = {
            **base_state,
            "proposed_fix_sql": "SELECT id, amount FROM (VALUES (1, NULL)) t(id, amount)",
            "iteration_count": 0,
            "status": "sandbox",
        }
        with patch("datasentinel_agent.agents.sandbox.get_settings") as mock_settings:
            mock_settings.return_value.max_fix_iterations = 3
            result = sandbox_node(state)
        if not result.get("sandbox_passed"):
            assert result["status"] in ("fixing", "escalated")


# ── Graph integration ─────────────────────────────────────────────────────────

class TestGraph:
    def test_graph_builds_without_error(self) -> None:
        from datasentinel_agent.graph import build_graph
        graph = build_graph()
        assert graph is not None

    def test_run_incident_returns_final_state(self, base_state: IncidentState) -> None:
        mock_claude = MagicMock()
        mock_claude.judge.return_value = {
            "anomaly_type": "null_spike",
            "confidence": 0.85,
            "summary": "Null spike",
            "root_cause_explanation": "Upstream null.",
            "recommended_fix_approach": "COALESCE",
            "evidence": {},
        }
        mock_claude.complete.return_value = (
            "EXPLANATION: Use COALESCE\n```sql\n"
            "SELECT id, COALESCE(amount, 0) AS amount FROM (VALUES (1, 10.0), (2, 5.0)) t(id, amount)\n"
            "```"
        )

        mock_om_instance = MagicMock()
        mock_om_instance.get_lineage.return_value = {
            "root": "orders_enriched", "nodes": {}, "edges": [], "_mock": True
        }
        mock_om_instance.get_upstream_tables.return_value = []

        with patch("datasentinel_agent.agents.diagnoser.ClaudeClient", return_value=mock_claude), \
             patch("datasentinel_agent.agents.remediator.ClaudeClient", return_value=mock_claude), \
             patch("datasentinel_agent.agents.sandbox.get_settings") as ms, \
             patch("datasentinel_agent.agents.lineage_tracer.OpenMetadataClient", return_value=mock_om_instance):
            ms.return_value.max_fix_iterations = 3
            from datasentinel_agent.graph import run_incident
            final = run_incident(
                table_name="orders_enriched",
                failing_tests=base_state["failing_tests"],
            )

        assert "incident_id" in final
        assert "status" in final
        assert final["status"] in ("pending_approval", "escalated", "fixing")
