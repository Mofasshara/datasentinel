"""PyFlink job template for stream quality monitoring.

Wires the DataSentinel stream operators into a Flink job:
  Kafka source → SchemaValidator → StatisticalMonitor → dq-violations Kafka topic
                                                      → Postgres (stream_violations)

Usage:
    python -m datasentinel_stream.flink_job --rules gps_rules.yaml

The job runs indefinitely until cancelled. In Flink's JobManager UI you can
see per-operator throughput metrics.

PyFlink is an optional dependency — install with:
    pip install "datasentinel-stream[flink]"
"""
from __future__ import annotations

import argparse
import json


def run(rules_yaml: str, kafka_bootstrap: str = "localhost:9092") -> None:
    try:
        from pyflink.common import SimpleStringSchema, WatermarkStrategy
        from pyflink.datastream import StreamExecutionEnvironment
        from pyflink.datastream.connectors.kafka import (
            FlinkKafkaConsumer,
            FlinkKafkaProducer,
        )
    except ImportError as exc:
        raise ImportError(
            "PyFlink not installed. Run: pip install 'datasentinel-stream[flink]'"
        ) from exc

    from datasentinel_stream.rules.compiler import RuleCompiler
    from datasentinel_stream.rules.dsl import QualityRuleSet
    from datasentinel_stream.storage.violations_repository import ViolationsRepository

    rule_set = QualityRuleSet.from_yaml(rules_yaml)
    validator, monitor = RuleCompiler.compile(rule_set)
    repo = ViolationsRepository()

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    # ── Kafka source ──────────────────────────────────────────────────────────
    consumer = FlinkKafkaConsumer(
        topics=rule_set.topic,
        deserialization_schema=SimpleStringSchema(),
        properties={
            "bootstrap.servers": kafka_bootstrap,
            "group.id": f"datasentinel-{rule_set.topic}",
            "auto.offset.reset": "latest",
        },
    )
    consumer.set_start_from_latest()

    raw_stream = env.add_source(consumer)

    # ── Quality check map ─────────────────────────────────────────────────────
    def quality_check(raw: str) -> str | None:
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            return None

        all_violations = validator.check(record) + monitor.check(record)
        for v in all_violations:
            repo.save_violation(v)

        if all_violations:
            return json.dumps(all_violations)
        return None

    violations_stream = (
        raw_stream
        .map(quality_check)
        .filter(lambda x: x is not None)
    )

    # ── Kafka sink — dq-violations topic ─────────────────────────────────────
    producer = FlinkKafkaProducer(
        topic="dq-violations",
        serialization_schema=SimpleStringSchema(),
        producer_config={"bootstrap.servers": kafka_bootstrap},
    )
    violations_stream.add_sink(producer)

    env.execute(f"DataSentinel QualityCheck — {rule_set.topic}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataSentinel stream quality monitor")
    parser.add_argument("--rules", required=True, help="Path to YAML rules file")
    parser.add_argument("--kafka", default="localhost:9092", help="Kafka bootstrap servers")
    args = parser.parse_args()
    run(rules_yaml=args.rules, kafka_bootstrap=args.kafka)
