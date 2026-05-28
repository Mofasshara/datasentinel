"""Stream Monitor demo — synthetic GPS event producer with injected anomalies.

Simulates a Kafka stream of GPS telemetry events. After a warmup period,
anomalous latitude values are injected. The stream monitor should detect these
within seconds and emit violations.

Usage (with Kafka running):
    make demo-stream

Usage (standalone, no Kafka — processes locally and prints violations):
    python demo/scenarios/stream_demo.py --standalone

The standalone mode is identical to the Kafka path except events go through
the operators directly rather than through a Kafka broker. Good for demos
without Docker.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone

from datasentinel_stream.operators.correlator import IncidentCorrelator
from datasentinel_stream.rules.compiler import RuleCompiler
from datasentinel_stream.rules.dsl import QualityRuleSet

# ── Rule set ──────────────────────────────────────────────────────────────────
GPS_RULES = {
    "topic": "gps-events",
    "rules": [
        {
            "name": "valid_latitude",
            "type": "range",
            "column": "latitude",
            "min": -90.0,
            "max": 90.0,
            "severity": "critical",
        },
        {
            "name": "valid_longitude",
            "type": "range",
            "column": "longitude",
            "min": -180.0,
            "max": 180.0,
            "severity": "critical",
        },
        {
            "name": "no_null_device_id",
            "type": "not_null",
            "column": "device_id",
            "severity": "warning",
        },
        {
            "name": "speed_anomaly",
            "type": "statistical",
            "column": "speed",
            "z_score_threshold": 3.5,
            "min_samples": 100,
        },
    ],
}

# Coordinates cluster around Singapore
BASE_LAT = 1.3521
BASE_LON = 103.8198
BASE_SPEED = 60.0  # km/h


def _generate_record(device_id: str, inject_anomaly: bool = False) -> dict:
    if inject_anomaly:
        # GPS sensor glitch: latitude jumps to an impossible value
        lat = random.uniform(200.0, 400.0)
    else:
        lat = BASE_LAT + random.gauss(0, 0.05)

    return {
        "id": f"{device_id}-{int(time.time() * 1000)}",
        "device_id": device_id,
        "latitude": round(lat, 6),
        "longitude": round(BASE_LON + random.gauss(0, 0.05), 6),
        "speed": round(BASE_SPEED + random.gauss(0, 5), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _run_standalone(
    total_records: int = 300,
    warmup_records: int = 150,
    anomaly_rate: float = 0.3,
    delay_ms: int = 50,
) -> None:
    """Process records locally through operators without Kafka."""
    rule_set = QualityRuleSet.from_dict(GPS_RULES)
    validator, monitor = RuleCompiler.compile(rule_set)
    correlator = IncidentCorrelator(window_seconds=10.0)

    devices = [f"device-{i:03d}" for i in range(5)]
    total_violations = 0
    anomaly_phase_started = False

    print(f"\n{'=' * 60}")
    print("DataSentinel Stream Monitor — GPS Demo (Standalone)")
    print(f"{'=' * 60}")
    print(f"Warmup: {warmup_records} records | Then injecting anomalies (rate={anomaly_rate})")
    print(f"Total records: {total_records}")
    print()

    for i in range(total_records):
        device = random.choice(devices)
        in_anomaly_phase = i >= warmup_records
        inject = in_anomaly_phase and (random.random() < anomaly_rate)

        if in_anomaly_phase and not anomaly_phase_started:
            anomaly_phase_started = True
            print(f"\n⚡ Anomaly injection started at record {i}")

        record = _generate_record(device, inject_anomaly=inject)
        violations = validator.check(record) + monitor.check(record)

        for v in violations:
            total_violations += 1
            incident = correlator.push(v)
            severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(v["severity"], "⚪")
            print(
                f"  {severity_icon} VIOLATION [{v['rule_name']}] "
                f"column={v['column']} value={v['value']} "
                f"expected={v['expected']}"
            )
            if incident:
                print(f"  📦 Incident correlated: {incident.incident_id} "
                      f"({incident.violation_count} violations)")

        # Flush expired incidents every 50 records
        if i % 50 == 0 and i > 0:
            for incident in correlator.flush_expired():
                print(f"\n  📦 Incident flushed: {incident.incident_id} | "
                      f"topic={incident.topic} column={incident.column} | "
                      f"{incident.violation_count} violations | severity={incident.severity}")

        if delay_ms:
            time.sleep(delay_ms / 1000)

    # Final flush
    for incident in correlator.flush_all():
        print(f"\n  📦 Final incident: {incident.incident_id} | "
              f"{incident.violation_count} violations | severity={incident.severity}")

    snapshot = monitor.get_baseline_snapshot()
    print(f"\n{'=' * 60}")
    print(f"Demo complete. Total violations detected: {total_violations}")
    print(f"Baseline snapshot: {json.dumps(snapshot, indent=2)}")
    print(f"{'=' * 60}\n")


def _run_kafka(kafka_bootstrap: str = "localhost:9092") -> None:
    """Produce records to Kafka — run alongside the Flink job."""
    try:
        from kafka import KafkaProducer
    except ImportError:
        print("kafka-python-ng not installed. Run: pip install kafka-python-ng")
        return

    rule_set = QualityRuleSet.from_dict(GPS_RULES)
    topic = rule_set.topic
    producer = KafkaProducer(
        bootstrap_servers=kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    devices = [f"device-{i:03d}" for i in range(5)]
    print(f"Producing to Kafka topic: {topic} @ {kafka_bootstrap}")
    print("Press Ctrl+C to stop.\n")

    record_count = 0
    try:
        while True:
            device = random.choice(devices)
            inject = record_count >= 200 and random.random() < 0.25
            record = _generate_record(device, inject_anomaly=inject)
            producer.send(topic, record)
            record_count += 1
            if inject:
                print(f"  [injected anomaly] lat={record['latitude']}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        producer.flush()
        print(f"\nSent {record_count} records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataSentinel stream demo")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Run locally without Kafka (good for demos)",
    )
    parser.add_argument("--kafka", default="localhost:9092", help="Kafka bootstrap servers")
    parser.add_argument("--records", type=int, default=300, help="Total records (standalone)")
    parser.add_argument("--warmup", type=int, default=150, help="Warmup records before anomaly injection")
    args = parser.parse_args()

    if args.standalone:
        _run_standalone(total_records=args.records, warmup_records=args.warmup)
    else:
        _run_kafka(kafka_bootstrap=args.kafka)
