"""YAML rule schema for streaming data quality checks.

Rules are loaded from YAML and validated with Pydantic, then compiled into
operator chains. No code is required for standard checks — define rules in YAML.

Example YAML:
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
      - name: speed_anomaly
        type: statistical
        column: speed
        z_score_threshold: 3.0
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class _BaseRule(BaseModel):
    name: str
    column: str
    severity: Severity = Severity.WARNING
    description: str = ""


class RangeRule(_BaseRule):
    type: Literal["range"] = "range"
    min: float | None = None
    max: float | None = None

    @field_validator("min", "max", mode="before")
    @classmethod
    def allow_none(cls, v: object) -> object:
        return v


class NotNullRule(_BaseRule):
    type: Literal["not_null"] = "not_null"


class RegexRule(_BaseRule):
    type: Literal["regex"] = "regex"
    pattern: str

    @field_validator("pattern")
    @classmethod
    def valid_regex(cls, v: str) -> str:
        re.compile(v)  # raises re.error if invalid
        return v


class NullRateRule(_BaseRule):
    """Fires when the rolling null fraction exceeds threshold over a window of records."""
    type: Literal["null_rate"] = "null_rate"
    threshold: float = Field(gt=0.0, le=1.0)
    window_size: int = Field(default=1000, ge=10)


class StatisticalRule(_BaseRule):
    """Fires when a value deviates more than z_score_threshold standard deviations
    from the rolling baseline mean for that column."""
    type: Literal["statistical"] = "statistical"
    z_score_threshold: float = Field(default=3.0, gt=0.0)
    min_samples: int = Field(default=100, ge=10)


AnyRule = Annotated[
    Union[RangeRule, NotNullRule, RegexRule, NullRateRule, StatisticalRule],
    Field(discriminator="type"),
]


class QualityRuleSet(BaseModel):
    """A collection of rules for a single Kafka topic."""
    topic: str
    rules: list[AnyRule]

    @classmethod
    def from_yaml(cls, path: str) -> "QualityRuleSet":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    @classmethod
    def from_dict(cls, data: dict) -> "QualityRuleSet":
        return cls.model_validate(data)

    def statistical_rules(self) -> list[StatisticalRule]:
        return [r for r in self.rules if isinstance(r, StatisticalRule)]

    def deterministic_rules(self) -> list[_BaseRule]:
        return [r for r in self.rules if not isinstance(r, StatisticalRule)]
