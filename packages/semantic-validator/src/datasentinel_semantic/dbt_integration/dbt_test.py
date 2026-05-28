"""dbt test integration for datasentinel-semantic.

Usage in dbt schema.yml:
    models:
      - name: products_enriched
        columns:
          - name: ai_description
            tests:
              - datasentinel.semantic_factual_consistency:
                  reference_column: spec_sheet
                  threshold: 0.95
              - datasentinel.hallucination_detection:
                  source_columns: [sku, brand, model_number]

Or invoke programmatically from a dbt on-run-end hook:
    from datasentinel_semantic.dbt_integration import run_dbt_model_checks
    run_dbt_model_checks(model_name="products_enriched", suite_config="config/semantic_suites.yml")
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from datasentinel_semantic.expectations import (
    FactualConsistencyExpectation,
    HallucinationDetectionExpectation,
    LabelAccuracyExpectation,
    SemanticDriftExpectation,
)
from datasentinel_semantic.suite import SemanticExpectationSuite, SuiteResult
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)

_EXPECTATION_MAP = {
    "factual_consistency": FactualConsistencyExpectation,
    "hallucination_detection": HallucinationDetectionExpectation,
    "label_accuracy": LabelAccuracyExpectation,
    "semantic_drift": SemanticDriftExpectation,
}


def run_dbt_model_checks(
    df: pd.DataFrame,
    suite_config: str | Path,
    model_name: str,
    fail_on_error: bool = True,
) -> SuiteResult:
    """Run semantic checks on a dbt model's output DataFrame.

    Args:
        df: The materialized model DataFrame.
        suite_config: Path to a YAML file defining suites and expectations.
        model_name: Used to look up the right suite in the config file.
        fail_on_error: If True, sys.exit(1) on suite failure (for dbt hook use).
    """
    config = yaml.safe_load(Path(suite_config).read_text())
    model_config = config.get("models", {}).get(model_name)
    if not model_config:
        log.warning("no_suite_config_for_model", model=model_name)
        return SemanticExpectationSuite(name=model_name).run(df)

    suite = SemanticExpectationSuite(name=model_name)
    for check in model_config.get("checks", []):
        exp_type = check.get("type")
        cls = _EXPECTATION_MAP.get(exp_type)
        if cls is None:
            log.warning("unknown_expectation_type", type=exp_type)
            continue
        params = {k: v for k, v in check.items() if k != "type"}
        suite.add(cls(**params))

    result = suite.run(df)
    if fail_on_error and not result.passed:
        log.error("suite_failed_dbt_model", model=model_name, summary=result.summary())
        sys.exit(1)

    return result


def suite_config_template() -> str:
    """Returns a starter YAML config template."""
    return """# DataSentinel semantic suite configuration
# Place this file at: config/datasentinel_suites.yml

models:
  products_enriched:
    checks:
      - type: factual_consistency
        column: ai_description
        reference_column: spec_sheet
        threshold: 0.95

      - type: hallucination_detection
        column: ai_description
        source_columns: [sku, brand, model_number]
        threshold: 0.95

      - type: semantic_drift
        column: ai_description
        threshold: 0.15
        lookback_days: 7

  customer_reviews_classified:
    checks:
      - type: label_accuracy
        column: sentiment_label
        content_column: review_text
        threshold: 0.90
        label_descriptions:
          positive: overwhelmingly positive sentiment
          neutral: mixed or neutral sentiment
          negative: predominantly negative sentiment
"""
