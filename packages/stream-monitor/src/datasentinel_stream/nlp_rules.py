"""Plain-English to YAML quality rule converter using Claude.

Accepts a natural-language description of a data quality rule and a Kafka
topic name, then uses Claude to generate a validated QualityRuleSet that
can be compiled directly into operators.

Example:
    rules = NLPRuleGenerator().generate(
        topic="gps-events",
        description="GPS latitude must be between -90 and 90. Longitude must be "
                    "between -180 and 180. The device_id field should never be empty. "
                    "Speed values more than 4 standard deviations from normal are anomalies.",
        sample_record={"latitude": 1.3, "longitude": 103.8, "device_id": "d-001", "speed": 60.0},
    )
"""
from __future__ import annotations

import json

from datasentinel_shared.claude_client import ClaudeClient

from datasentinel_stream.rules.dsl import QualityRuleSet

_SYSTEM = """\
You are a data quality rule compiler. Given a Kafka topic name, a plain-English
description of quality requirements, and an optional sample record, you produce
a YAML quality rule set for the DataSentinel stream monitor.

The YAML must match this exact schema:
  topic: <string>
  rules:
    - name: <snake_case>       # unique rule name
      type: <rule_type>        # one of: range, not_null, regex, null_rate, statistical
      column: <field_name>
      severity: <info|warning|critical>   # optional, default warning
      # type-specific fields:
      # range:       min: <float>  max: <float>
      # regex:       pattern: <python_regex>
      # null_rate:   threshold: <0.0-1.0>   window_size: <int, default 1000>
      # statistical: z_score_threshold: <float, default 3.0>  min_samples: <int, default 100>

Rules:
- Only generate rules that are explicitly implied by the description.
- Use snake_case for rule names.
- Do not invent columns that are not mentioned or in the sample record.
- Return ONLY the raw YAML, no markdown fences, no extra text.
"""


class NLPRuleGenerator:
    def __init__(self) -> None:
        self._client: ClaudeClient | None = None

    @property
    def client(self) -> ClaudeClient:
        if self._client is None:
            self._client = ClaudeClient()
        return self._client

    def generate(
        self,
        topic: str,
        description: str,
        sample_record: dict | None = None,
    ) -> QualityRuleSet:
        """Generate a QualityRuleSet from a plain-English rule description.

        Raises ValueError if the LLM output cannot be parsed or validated.
        """
        prompt = f"Topic: {topic}\n\nDescription:\n{description}"
        if sample_record:
            prompt += f"\n\nSample record:\n{json.dumps(sample_record, indent=2)}"

        yaml_text = self.client.complete(
            prompt=prompt,
            system=_SYSTEM,
        )

        try:
            import yaml
            data = yaml.safe_load(yaml_text.strip())
        except Exception as exc:
            raise ValueError(f"LLM returned invalid YAML: {exc}\n\nRaw output:\n{yaml_text}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Expected YAML dict, got {type(data)}: {yaml_text}")

        # Ensure topic matches
        data["topic"] = topic

        try:
            return QualityRuleSet.from_dict(data)
        except Exception as exc:
            raise ValueError(f"Generated YAML does not match rule schema: {exc}\n\nYAML:\n{yaml_text}") from exc

    def generate_yaml(
        self,
        topic: str,
        description: str,
        sample_record: dict | None = None,
    ) -> str:
        """Like generate() but returns the raw YAML string."""
        import yaml
        rule_set = self.generate(topic, description, sample_record)
        return yaml.dump(rule_set.model_dump(), default_flow_style=False)
