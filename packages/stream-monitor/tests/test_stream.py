"""Unit tests for the stream monitor — no Kafka, no Flink, no API key required."""
from __future__ import annotations

import math
import time
from unittest.mock import MagicMock, patch

import pytest

from datasentinel_stream.operators.anomaly_detector import StatisticalMonitor, _ColumnBaseline
from datasentinel_stream.operators.correlator import IncidentCorrelator
from datasentinel_stream.operators.validator import SchemaValidator
from datasentinel_stream.rules.compiler import RuleCompiler
from datasentinel_stream.rules.dsl import (
    NotNullRule,
    NullRateRule,
    QualityRuleSet,
    RangeRule,
    RegexRule,
    Severity,
    StatisticalRule,
)


# ── DSL / Pydantic ─────────────────────────────────────────────────────────────

class TestQualityRuleSet:
    def test_from_dict_range(self) -> None:
        data = {
            "topic": "test",
            "rules": [{"name": "lat_range", "type": "range", "column": "lat", "min": -90.0, "max": 90.0}],
        }
        rs = QualityRuleSet.from_dict(data)
        assert rs.topic == "test"
        assert len(rs.rules) == 1
        assert isinstance(rs.rules[0], RangeRule)

    def test_from_dict_not_null(self) -> None:
        data = {"topic": "t", "rules": [{"name": "nn", "type": "not_null", "column": "id"}]}
        rs = QualityRuleSet.from_dict(data)
        assert isinstance(rs.rules[0], NotNullRule)

    def test_from_dict_regex(self) -> None:
        data = {"topic": "t", "rules": [{"name": "ts", "type": "regex", "column": "ts", "pattern": r"^\d{4}-"}]}
        rs = QualityRuleSet.from_dict(data)
        assert isinstance(rs.rules[0], RegexRule)

    def test_invalid_regex_raises(self) -> None:
        data = {"topic": "t", "rules": [{"name": "bad", "type": "regex", "column": "x", "pattern": "[invalid"}]}
        with pytest.raises(Exception):
            QualityRuleSet.from_dict(data)

    def test_statistical_and_deterministic_split(self) -> None:
        data = {
            "topic": "t",
            "rules": [
                {"name": "range_r", "type": "range", "column": "x", "min": 0.0},
                {"name": "stat_r", "type": "statistical", "column": "x", "min_samples": 10},
            ],
        }
        rs = QualityRuleSet.from_dict(data)
        assert len(rs.statistical_rules()) == 1
        assert len(rs.deterministic_rules()) == 1

    def test_severity_defaults_to_warning(self) -> None:
        data = {"topic": "t", "rules": [{"name": "r", "type": "not_null", "column": "c"}]}
        rs = QualityRuleSet.from_dict(data)
        assert rs.rules[0].severity == Severity.WARNING


# ── SchemaValidator ────────────────────────────────────────────────────────────

@pytest.fixture
def gps_validator() -> SchemaValidator:
    rules = [
        RangeRule(name="lat_range", column="latitude", min=-90.0, max=90.0, severity=Severity.CRITICAL),
        RangeRule(name="lon_range", column="longitude", min=-180.0, max=180.0),
        NotNullRule(name="device_id_not_null", column="device_id"),
        RegexRule(name="ts_format", column="timestamp", pattern=r"^\d{4}-\d{2}-\d{2}T"),
    ]
    return SchemaValidator(topic="gps", rules=rules)


class TestSchemaValidator:
    def test_valid_record_no_violations(self, gps_validator: SchemaValidator) -> None:
        record = {"latitude": 1.3, "longitude": 103.8, "device_id": "d-001", "timestamp": "2026-01-01T12:00:00"}
        assert gps_validator.check(record) == []

    def test_latitude_out_of_range(self, gps_validator: SchemaValidator) -> None:
        record = {"latitude": 200.0, "longitude": 103.8, "device_id": "d-001", "timestamp": "2026-01-01T12:00:00"}
        violations = gps_validator.check(record)
        assert len(violations) == 1
        assert violations[0]["rule_name"] == "lat_range"
        assert violations[0]["severity"] == "critical"

    def test_null_device_id(self, gps_validator: SchemaValidator) -> None:
        record = {"latitude": 1.3, "longitude": 103.8, "device_id": None, "timestamp": "2026-01-01T12:00:00"}
        violations = gps_validator.check(record)
        assert any(v["rule_name"] == "device_id_not_null" for v in violations)

    def test_regex_mismatch(self, gps_validator: SchemaValidator) -> None:
        record = {"latitude": 1.3, "longitude": 103.8, "device_id": "d-001", "timestamp": "01/01/2026"}
        violations = gps_validator.check(record)
        assert any(v["rule_name"] == "ts_format" for v in violations)

    def test_multiple_violations_in_one_record(self, gps_validator: SchemaValidator) -> None:
        record = {"latitude": 999.0, "longitude": 999.0, "device_id": None, "timestamp": "bad"}
        violations = gps_validator.check(record)
        assert len(violations) >= 3

    def test_null_rate_rule_fires_after_window_fills(self) -> None:
        rule = NullRateRule(name="speed_null_rate", column="speed", threshold=0.2, window_size=20)
        validator = SchemaValidator(topic="t", rules=[rule])
        # Push 10 non-null records
        for _ in range(10):
            validator.check({"speed": 60.0})
        # Push 10 null records — null rate = 0.5 > 0.2
        violations = []
        for _ in range(10):
            violations.extend(validator.check({"speed": None}))
        assert any(v["rule_name"] == "speed_null_rate" for v in violations)

    def test_null_rate_no_fire_below_threshold(self) -> None:
        rule = NullRateRule(name="nr", column="x", threshold=0.5, window_size=20)
        validator = SchemaValidator(topic="t", rules=[rule])
        for _ in range(18):
            validator.check({"x": 1.0})
        violations = []
        for _ in range(2):  # 2/20 = 0.1 < 0.5
            violations.extend(validator.check({"x": None}))
        assert violations == []


# ── StatisticalMonitor ─────────────────────────────────────────────────────────

class TestColumnBaseline:
    def test_warmup_requires_min_samples(self) -> None:
        b = _ColumnBaseline()
        for i in range(50):
            b.update(float(i), min_samples=100)
        assert not b.warmed_up

    def test_warmup_completes_at_min_samples(self) -> None:
        b = _ColumnBaseline()
        for i in range(100):
            b.update(float(i), min_samples=100)
        assert b.warmed_up

    def test_z_score_high_for_outlier(self) -> None:
        b = _ColumnBaseline()
        for _ in range(100):
            b.update(50.0, min_samples=100)
        z = b.z_score(50000.0)
        assert z > 10.0

    def test_z_score_low_for_normal(self) -> None:
        b = _ColumnBaseline()
        for _ in range(100):
            b.update(50.0, min_samples=100)
        z = b.z_score(50.1)
        assert z < 1.0


class TestStatisticalMonitor:
    def _warmed_monitor(self, z_threshold: float = 3.0, min_samples: int = 100) -> StatisticalMonitor:
        rule = StatisticalRule(name="speed_anomaly", column="speed", z_score_threshold=z_threshold, min_samples=min_samples)
        monitor = StatisticalMonitor(topic="gps", rules=[rule])
        for _ in range(min_samples):
            monitor.check({"speed": 60.0})
        return monitor

    def test_no_violations_during_warmup(self) -> None:
        rule = StatisticalRule(name="r", column="x", z_score_threshold=2.0, min_samples=50)
        monitor = StatisticalMonitor(topic="t", rules=[rule])
        violations = []
        for _ in range(49):
            violations.extend(monitor.check({"x": 999.0}))  # extreme but warmup
        assert violations == []

    def test_fires_on_anomaly_after_warmup(self) -> None:
        monitor = self._warmed_monitor(z_threshold=3.0, min_samples=100)
        violations = monitor.check({"speed": 60000.0})
        assert len(violations) == 1
        assert violations[0]["rule_name"] == "speed_anomaly"
        assert violations[0]["z_score"] > 3.0

    def test_no_violation_for_normal_value(self) -> None:
        monitor = self._warmed_monitor()
        violations = monitor.check({"speed": 61.0})
        assert violations == []

    def test_missing_column_skipped(self) -> None:
        monitor = self._warmed_monitor()
        violations = monitor.check({"latitude": 1.3})  # no "speed" key
        assert violations == []

    def test_baseline_snapshot_has_all_rules(self) -> None:
        monitor = self._warmed_monitor()
        snapshot = monitor.get_baseline_snapshot()
        assert "speed_anomaly" in snapshot
        assert snapshot["speed_anomaly"]["warmed_up"] is True


# ── RuleCompiler ───────────────────────────────────────────────────────────────

class TestRuleCompiler:
    def test_compiles_to_validator_and_monitor(self) -> None:
        data = {
            "topic": "events",
            "rules": [
                {"name": "lat", "type": "range", "column": "lat", "min": -90.0, "max": 90.0},
                {"name": "speed_stat", "type": "statistical", "column": "speed", "min_samples": 10},
            ],
        }
        rs = QualityRuleSet.from_dict(data)
        validator, monitor = RuleCompiler.compile(rs)
        assert isinstance(validator, SchemaValidator)
        assert isinstance(monitor, StatisticalMonitor)
        assert len(validator._rules) == 1
        assert len(monitor._rules) == 1


# ── IncidentCorrelator ─────────────────────────────────────────────────────────

class TestIncidentCorrelator:
    def _violation(self, topic: str = "gps", column: str = "latitude", severity: str = "critical") -> dict:
        return {
            "type": "violation",
            "topic": topic,
            "column": column,
            "rule_name": "lat_range",
            "value": 200.0,
            "severity": severity,
            "timestamp": "2026-01-01T00:00:00",
        }

    def test_single_violation_opens_group(self) -> None:
        c = IncidentCorrelator(window_seconds=60.0)
        result = c.push(self._violation())
        assert result is None  # group open, not flushed yet

    def test_flush_all_returns_open_groups(self) -> None:
        c = IncidentCorrelator(window_seconds=60.0)
        c.push(self._violation())
        c.push(self._violation())
        incidents = c.flush_all()
        assert len(incidents) == 1
        assert incidents[0].violation_count == 2

    def test_two_different_columns_produce_two_groups(self) -> None:
        c = IncidentCorrelator(window_seconds=60.0)
        c.push(self._violation(column="latitude"))
        c.push(self._violation(column="longitude"))
        incidents = c.flush_all()
        assert len(incidents) == 2

    def test_expired_group_auto_flushes(self) -> None:
        c = IncidentCorrelator(window_seconds=0.05)  # 50ms window
        c.push(self._violation())
        time.sleep(0.1)
        c.push(self._violation())  # triggers flush of expired group
        # At this point the old group should have been flushed and a new one started
        remaining = c.flush_all()
        assert len(remaining) == 1  # the new group

    def test_severity_escalates_to_highest(self) -> None:
        c = IncidentCorrelator(window_seconds=60.0)
        c.push(self._violation(severity="info"))
        c.push(self._violation(severity="critical"))
        incidents = c.flush_all()
        assert incidents[0].severity == "critical"

    def test_incident_to_dict(self) -> None:
        c = IncidentCorrelator(window_seconds=60.0)
        c.push(self._violation())
        incidents = c.flush_all()
        d = incidents[0].to_dict()
        assert "incident_id" in d
        assert "violation_count" in d
        assert d["violation_count"] == 1


# ── NLP rule generator (mocked) ────────────────────────────────────────────────

class TestNLPRuleGenerator:
    def test_generates_rule_set_from_llm_yaml(self) -> None:
        mock_yaml = """\
topic: gps-events
rules:
  - name: valid_latitude
    type: range
    column: latitude
    min: -90.0
    max: 90.0
    severity: critical
  - name: no_null_device_id
    type: not_null
    column: device_id
"""
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_yaml

        from datasentinel_stream.nlp_rules import NLPRuleGenerator
        gen = NLPRuleGenerator()
        gen._client = mock_client

        rs = gen.generate(
            topic="gps-events",
            description="GPS lat must be -90..90. device_id must not be null.",
        )
        assert rs.topic == "gps-events"
        assert len(rs.rules) == 2
        assert isinstance(rs.rules[0], RangeRule)

    def test_raises_on_invalid_yaml(self) -> None:
        mock_client = MagicMock()
        mock_client.complete.return_value = "this is not yaml: [{{{"

        from datasentinel_stream.nlp_rules import NLPRuleGenerator
        gen = NLPRuleGenerator()
        gen._client = mock_client

        with pytest.raises(ValueError, match="invalid YAML"):
            gen.generate(topic="t", description="anything")

    def test_raises_on_schema_mismatch(self) -> None:
        mock_client = MagicMock()
        mock_client.complete.return_value = "topic: t\nrules:\n  - name: r\n    type: unknown_type\n    column: x\n"

        from datasentinel_stream.nlp_rules import NLPRuleGenerator
        gen = NLPRuleGenerator()
        gen._client = mock_client

        with pytest.raises(ValueError):
            gen.generate(topic="t", description="anything")
