"""Stateful statistical anomaly detection operator.

Maintains a rolling baseline (mean + variance via Welford's online algorithm)
per column. When a new value deviates more than z_score_threshold standard
deviations from the baseline, a violation is emitted.

Cold-start behavior: the first min_samples records are used to build the
baseline. No violations are emitted until min_samples is reached — this
prevents false alerts on fresh topics.

After baseline is established, the baseline itself updates with an exponential
moving average (alpha = 0.05) so slow drift in legitimate data does not trigger
permanent alerts. Only sharp deviations fire.

The operator is pure Python. The PyFlink job saves/restores the per-column
state objects via Flink keyed state (ListState or ValueState).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from datasentinel_stream.rules.dsl import Severity, StatisticalRule


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _ColumnBaseline:
    """Welford's online mean/variance tracker with EMA blending after warmup."""
    n: int = 0
    mean: float = 0.0
    M2: float = 0.0          # sum of squared deviations — Welford accumulator
    ema_mean: float = 0.0
    ema_var: float = 1.0
    warmed_up: bool = False

    # EMA blending weight — low alpha means slow adaptation (drift tolerance)
    EMA_ALPHA: float = field(default=0.05, init=False, repr=False)

    def update(self, value: float, min_samples: int) -> None:
        self.n += 1
        # Welford's online algorithm
        delta = value - self.mean
        self.mean += delta / self.n
        delta2 = value - self.mean
        self.M2 += delta * delta2

        if self.n >= min_samples and not self.warmed_up:
            # Seed EMA from Welford baseline on first warmup completion
            self.ema_mean = self.mean
            self.ema_var = self.variance or 1.0
            self.warmed_up = True
        elif self.warmed_up:
            # Blend current observation into EMA baseline
            self.ema_mean = self.EMA_ALPHA * value + (1 - self.EMA_ALPHA) * self.ema_mean
            obs_var = (value - self.ema_mean) ** 2
            self.ema_var = self.EMA_ALPHA * obs_var + (1 - self.EMA_ALPHA) * self.ema_var

    @property
    def variance(self) -> float:
        return self.M2 / self.n if self.n > 1 else 0.0

    @property
    def std(self) -> float:
        v = self.ema_var if self.warmed_up else self.variance
        return math.sqrt(v) if v > 0 else 1.0

    def z_score(self, value: float) -> float:
        baseline = self.ema_mean if self.warmed_up else self.mean
        return abs(value - baseline) / self.std


class StatisticalMonitor:
    """Apply statistical anomaly detection rules to a stream of records."""

    def __init__(self, topic: str, rules: list[StatisticalRule]) -> None:
        self.topic = topic
        self._rules = rules
        # Per-rule, per-column baseline state
        self._baselines: dict[str, _ColumnBaseline] = {
            r.name: _ColumnBaseline() for r in rules
        }

    def check(self, record: dict) -> list[dict]:
        violations = []
        for rule in self._rules:
            v = self._check_rule(rule, record)
            if v is not None:
                violations.append(v)
        return violations

    def _check_rule(self, rule: StatisticalRule, record: dict) -> dict | None:
        raw = record.get(rule.column)
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None

        baseline = self._baselines[rule.name]
        baseline.update(value, rule.min_samples)

        if not baseline.warmed_up:
            return None  # still learning baseline

        z = baseline.z_score(value)
        if z > rule.z_score_threshold:
            return {
                "type": "violation",
                "topic": self.topic,
                "rule_name": rule.name,
                "column": rule.column,
                "value": value,
                "expected": f"within {rule.z_score_threshold} std dev of baseline "
                            f"(mean={baseline.ema_mean:.3f}, std={baseline.std:.3f})",
                "z_score": round(z, 3),
                "severity": rule.severity.value,
                "timestamp": _now(),
                "record_id": record.get("id") or record.get("record_id") or "",
            }
        return None

    def get_baseline_snapshot(self) -> dict:
        """Return current baseline stats for all monitored columns (for dashboard)."""
        return {
            name: {
                "n": b.n,
                "mean": round(b.ema_mean if b.warmed_up else b.mean, 4),
                "std": round(b.std, 4),
                "warmed_up": b.warmed_up,
            }
            for name, b in self._baselines.items()
        }
