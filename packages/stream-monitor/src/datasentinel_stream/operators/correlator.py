"""Cross-stream incident correlator.

Buffers violations from any source and groups those that arrive within a
time window into a single incident. This reduces alert noise when a single
upstream issue (e.g. a bad sensor batch) triggers violations across multiple
rules simultaneously.

Grouping logic:
  1. Violations with the same (topic, column) pair that arrive within
     `window_seconds` of each other are grouped.
  2. When no new violation arrives for a group within `window_seconds`,
     the group is flushed as a single CorrelatedIncident.

Usage (standalone, non-Flink):
    correlator = IncidentCorrelator(window_seconds=60)

    for violation in stream:
        incident = correlator.push(violation)
        if incident:
            # flush ready incident
            handle(incident)

    # at end of stream, flush remaining open incidents
    for incident in correlator.flush_all():
        handle(incident)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CorrelatedIncident:
    incident_id: str
    topic: str
    column: str
    first_seen: datetime
    last_seen: datetime
    violation_count: int
    severity: str
    rule_names: list[str]
    sample_violations: list[dict]

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "topic": self.topic,
            "column": self.column,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "violation_count": self.violation_count,
            "severity": self.severity,
            "rule_names": self.rule_names,
            "sample_violations": self.sample_violations[:5],
        }


@dataclass
class _OpenGroup:
    topic: str
    column: str
    first_seen: datetime
    last_seen: datetime
    violations: list[dict] = field(default_factory=list)
    rule_names: list[str] = field(default_factory=list)
    max_severity: str = "info"

    _SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}

    def add(self, v: dict) -> None:
        self.violations.append(v)
        self.last_seen = _utcnow()
        rule = v.get("rule_name", "")
        if rule not in self.rule_names:
            self.rule_names.append(rule)
        sev = v.get("severity", "info")
        if self._SEVERITY_ORDER.get(sev, 0) > self._SEVERITY_ORDER.get(self.max_severity, 0):
            self.max_severity = sev

    def is_expired(self, window_seconds: float) -> bool:
        elapsed = (_utcnow() - self.last_seen).total_seconds()
        return elapsed >= window_seconds


class IncidentCorrelator:
    """Buffer violations and group correlated ones into incidents."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._groups: dict[str, _OpenGroup] = {}  # key: "topic::column"
        self._incident_counter = 0

    def push(self, violation: dict) -> CorrelatedIncident | None:
        """Accept one violation. Returns a flushed CorrelatedIncident if a
        previously open group just expired, otherwise None."""
        key = f"{violation.get('topic', '')}::{violation.get('column', '')}"
        now = _utcnow()

        flushed: CorrelatedIncident | None = None

        # Check if the current group for this key expired (new burst starting)
        if key in self._groups and self._groups[key].is_expired(self._window):
            flushed = self._close_group(key)

        if key not in self._groups:
            self._groups[key] = _OpenGroup(
                topic=violation.get("topic", ""),
                column=violation.get("column", ""),
                first_seen=now,
                last_seen=now,
            )

        self._groups[key].add(violation)
        return flushed

    def flush_all(self) -> list[CorrelatedIncident]:
        """Close all open groups and return their incidents."""
        keys = list(self._groups.keys())
        return [self._close_group(k) for k in keys]

    def flush_expired(self) -> list[CorrelatedIncident]:
        """Close only groups that have been quiet for window_seconds."""
        expired = [k for k, g in self._groups.items() if g.is_expired(self._window)]
        return [self._close_group(k) for k in expired]

    def _close_group(self, key: str) -> CorrelatedIncident:
        g = self._groups.pop(key)
        self._incident_counter += 1
        return CorrelatedIncident(
            incident_id=f"stream-{self._incident_counter:06d}",
            topic=g.topic,
            column=g.column,
            first_seen=g.first_seen,
            last_seen=g.last_seen,
            violation_count=len(g.violations),
            severity=g.max_severity,
            rule_names=g.rule_names,
            sample_violations=g.violations,
        )
