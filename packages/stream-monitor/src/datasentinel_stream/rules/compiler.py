"""Compiles a QualityRuleSet into a ready-to-use operator chain.

The compiler is the bridge between the YAML DSL and the runtime operators.
It instantiates SchemaValidator with all deterministic rules and StatisticalMonitor
with all statistical rules, returning a pair that can be applied to any record stream.

Usage:
    rule_set = QualityRuleSet.from_yaml("gps_rules.yaml")
    validator, monitor = RuleCompiler.compile(rule_set)

    for record in records:
        violations = validator.check(record) + monitor.check(record)
"""
from __future__ import annotations

from datasentinel_stream.operators.anomaly_detector import StatisticalMonitor
from datasentinel_stream.operators.validator import SchemaValidator
from datasentinel_stream.rules.dsl import QualityRuleSet


class RuleCompiler:
    @staticmethod
    def compile(rule_set: QualityRuleSet) -> tuple[SchemaValidator, StatisticalMonitor]:
        """Return (SchemaValidator, StatisticalMonitor) compiled from rule_set."""
        validator = SchemaValidator(
            topic=rule_set.topic,
            rules=rule_set.deterministic_rules(),
        )
        monitor = StatisticalMonitor(
            topic=rule_set.topic,
            rules=rule_set.statistical_rules(),
        )
        return validator, monitor
