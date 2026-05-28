"""Deterministic schema and field validation operator.

Runs rule checks that have a definitive true/false answer per record:
  - RangeRule: value must fall within [min, max]
  - NotNullRule: value must not be None / empty
  - RegexRule: string value must match pattern
  - NullRateRule: rolling null fraction must stay below threshold

The operator is stateless for RangeRule/NotNullRule/RegexRule (per-record).
NullRateRule is stateful — it maintains a sliding window counter per column.

All operators are pure Python; no Flink dependency. The PyFlink job template
wraps this class as a ProcessFunction, calling check() for each record.
"""
from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timezone

from datasentinel_stream.rules.dsl import (
    NullRateRule,
    NotNullRule,
    RangeRule,
    RegexRule,
    Severity,
    _BaseRule,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_violation(
    topic: str,
    rule_name: str,
    column: str,
    value: object,
    expected: str,
    severity: Severity,
    record: dict,
) -> dict:
    return {
        "type": "violation",
        "topic": topic,
        "rule_name": rule_name,
        "column": column,
        "value": value,
        "expected": expected,
        "severity": severity.value,
        "timestamp": _now(),
        "record_id": record.get("id") or record.get("record_id") or "",
    }


class _NullRateWindow:
    """Sliding-window null counter for a single column."""

    def __init__(self, window_size: int) -> None:
        self._window: deque[bool] = deque(maxlen=window_size)

    def push(self, is_null: bool) -> float:
        self._window.append(is_null)
        return sum(self._window) / len(self._window)

    def __len__(self) -> int:
        return len(self._window)


class SchemaValidator:
    """Apply deterministic rules to each record and emit violation dicts."""

    def __init__(self, topic: str, rules: list[_BaseRule]) -> None:
        self.topic = topic
        self._rules = rules
        self._null_windows: dict[str, _NullRateWindow] = {
            r.name: _NullRateWindow(r.window_size)
            for r in rules
            if isinstance(r, NullRateRule)
        }
        self._compiled_patterns: dict[str, re.Pattern] = {
            r.name: re.compile(r.pattern)
            for r in rules
            if isinstance(r, RegexRule)
        }

    def check(self, record: dict) -> list[dict]:
        violations: list[dict] = []
        for rule in self._rules:
            v = self._check_rule(rule, record)
            if v is not None:
                violations.append(v)
        return violations

    def _check_rule(self, rule: _BaseRule, record: dict) -> dict | None:
        value = record.get(rule.column)

        if isinstance(rule, NotNullRule):
            if value is None or value == "":
                return _make_violation(
                    self.topic, rule.name, rule.column, value,
                    "non-null value", rule.severity, record,
                )

        elif isinstance(rule, RangeRule):
            if value is None:
                return None  # nulls handled by NotNullRule if needed
            try:
                fval = float(value)
            except (TypeError, ValueError):
                return _make_violation(
                    self.topic, rule.name, rule.column, value,
                    "numeric value", rule.severity, record,
                )
            lo, hi = rule.min, rule.max
            if (lo is not None and fval < lo) or (hi is not None and fval > hi):
                expected = f"[{lo}, {hi}]"
                return _make_violation(
                    self.topic, rule.name, rule.column, value,
                    expected, rule.severity, record,
                )

        elif isinstance(rule, RegexRule):
            if value is None:
                return None
            if not self._compiled_patterns[rule.name].search(str(value)):
                return _make_violation(
                    self.topic, rule.name, rule.column, value,
                    f"matches /{rule.pattern}/", rule.severity, record,
                )

        elif isinstance(rule, NullRateRule):
            window = self._null_windows[rule.name]
            null_rate = window.push(value is None)
            if len(window) >= 10 and null_rate > rule.threshold:
                return _make_violation(
                    self.topic, rule.name, rule.column, round(null_rate, 4),
                    f"null_rate < {rule.threshold}", rule.severity, record,
                )

        return None
