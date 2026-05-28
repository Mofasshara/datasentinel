"""Unit tests for the core expectation framework.

These tests mock the LLM judge so they run without an API key.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from datasentinel_semantic.core.expectation import ExpectationResult, SemanticExpectation, Verdict
from datasentinel_semantic.core.judge import JudgeVerdict, LLMJudge
from datasentinel_semantic.expectations.factual_consistency import FactualConsistencyExpectation
from datasentinel_semantic.expectations.hallucination import HallucinationDetectionExpectation
from datasentinel_semantic.expectations.label_accuracy import LabelAccuracyExpectation
from datasentinel_semantic.expectations.semantic_drift import SemanticDriftExpectation
from datasentinel_semantic.suite import SemanticExpectationSuite


def _mock_judge(passed: bool = True, confidence: float = 0.9) -> LLMJudge:
    judge = MagicMock(spec=LLMJudge)
    judge.evaluate.return_value = JudgeVerdict(
        passed=passed, confidence=confidence, reason="test", evidence={}
    )
    return judge


class TestExpectationResult:
    def test_pass_rate_calculation(self) -> None:
        result = ExpectationResult(
            expectation_name="test",
            column_name="col",
            total_records=100,
            passed_records=95,
            failed_records=5,
        )
        assert result.pass_rate == pytest.approx(0.95)

    def test_passed_at_threshold(self) -> None:
        result = ExpectationResult(
            expectation_name="test", column_name="col",
            total_records=100, passed_records=95, failed_records=5,
        ).with_threshold(0.95)
        assert result.passed is True

    def test_failed_below_threshold(self) -> None:
        result = ExpectationResult(
            expectation_name="test", column_name="col",
            total_records=100, passed_records=80, failed_records=20,
        ).with_threshold(0.95)
        assert result.passed is False

    def test_zero_records(self) -> None:
        result = ExpectationResult(
            expectation_name="test", column_name="col",
            total_records=0, passed_records=0, failed_records=0,
        )
        assert result.pass_rate == 0.0


class TestFactualConsistency:
    def test_passes_when_judge_passes(self) -> None:
        exp = FactualConsistencyExpectation(column="ai_desc", reference_column="spec")
        exp._judge = _mock_judge(passed=True)  # pre-set so lazy property is skipped
        df = pd.DataFrame([{"ai_desc": "correct text", "spec": "spec text"}])
        result = exp.evaluate(df)
        assert result.passed_records == 1
        assert result.failed_records == 0

    def test_fails_when_judge_fails(self) -> None:
        exp = FactualConsistencyExpectation(column="ai_desc", reference_column="spec", threshold=0.95)
        exp._judge = _mock_judge(passed=False)
        df = pd.DataFrame([{"ai_desc": "wrong text", "spec": "spec text"}] * 5)
        result = exp.evaluate(df)
        assert result.failed_records == 5
        assert result.passed is False

    def test_missing_column_raises(self) -> None:
        exp = FactualConsistencyExpectation(column="nonexistent", reference_column="spec")
        exp._judge = _mock_judge()  # prevent Settings load
        df = pd.DataFrame([{"spec": "text"}])
        with pytest.raises(ValueError, match="nonexistent"):
            exp.evaluate(df)

    def test_failures_are_stored_as_verdicts(self) -> None:
        exp = FactualConsistencyExpectation(column="ai_desc", reference_column="spec", threshold=0.95)
        exp._judge = _mock_judge(passed=False)
        df = pd.DataFrame([{"ai_desc": "wrong", "spec": "right"}] * 3)
        result = exp.evaluate(df)
        assert len(result.verdicts) == 3
        assert all(not v.passed for v in result.verdicts)


class TestHallucinationDetection:
    def test_passes_when_no_hallucinations(self) -> None:
        exp = HallucinationDetectionExpectation(column="ai_text", source_columns=["sku", "brand"])
        exp._judge = _mock_judge(passed=True)
        df = pd.DataFrame([{"ai_text": "real product", "sku": "SKU-1", "brand": "Brand"}])
        result = exp.evaluate(df)
        assert result.passed_records == 1

    def test_detects_hallucinated_entities(self) -> None:
        exp = HallucinationDetectionExpectation(column="ai_text", source_columns=["sku"], threshold=0.90)
        exp._judge = _mock_judge(passed=False)
        df = pd.DataFrame([{"ai_text": "invented XR-9000", "sku": "SKU-1"}] * 10)
        result = exp.evaluate(df)
        assert result.passed is False


class TestLabelAccuracy:
    def test_correct_labels_pass(self) -> None:
        exp = LabelAccuracyExpectation(column="label", content_column="text")
        exp._judge = _mock_judge(passed=True)
        df = pd.DataFrame([{"label": "positive", "text": "great product!"}])
        result = exp.evaluate(df)
        assert result.passed_records == 1

    def test_wrong_labels_fail(self) -> None:
        exp = LabelAccuracyExpectation(column="label", content_column="text", threshold=0.90)
        exp._judge = _mock_judge(passed=False)
        df = pd.DataFrame([{"label": "positive", "text": "terrible, worst ever"}] * 10)
        result = exp.evaluate(df)
        assert result.passed is False


class TestSemanticDrift:
    def test_no_baseline_always_passes(self) -> None:
        exp = SemanticDriftExpectation(column="text", threshold=0.15)
        df = pd.DataFrame([{"text": "some AI generated text about products"}] * 5)
        with patch("datasentinel_semantic.expectations.semantic_drift.SentenceTransformer") as mock_st:
            import numpy as np
            mock_model = MagicMock()
            mock_model.encode.return_value = np.random.rand(5, 384)
            mock_st.return_value = mock_model
            result = exp.evaluate(df)
        assert result.passed_records == 5

    def test_large_drift_fails(self) -> None:
        import numpy as np
        exp = SemanticDriftExpectation(column="text", threshold=0.10)
        exp._baseline_centroid = np.ones(384) / np.linalg.norm(np.ones(384))

        with patch("datasentinel_semantic.expectations.semantic_drift.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            # Return embeddings orthogonal to baseline — max drift
            orthogonal = np.zeros(384)
            orthogonal[0] = 1.0
            mock_model.encode.return_value = np.tile(orthogonal, (5, 1))
            mock_st.return_value = mock_model
            exp._model = mock_model
            result = exp.evaluate(pd.DataFrame([{"text": "x"}] * 5))
        assert result.passed is False


class TestSuite:
    def test_suite_aggregates_results(self) -> None:
        exp1 = FactualConsistencyExpectation(column="ai_desc", reference_column="spec")
        exp1._judge = _mock_judge(passed=True)  # inject before any evaluate call
        exp2 = LabelAccuracyExpectation(column="label", content_column="text")
        exp2._judge = _mock_judge(passed=True)

        suite = SemanticExpectationSuite(name="test_suite").add(exp1).add(exp2)
        df = pd.DataFrame([{"ai_desc": "a", "spec": "a", "label": "pos", "text": "great"}])
        result = suite.run(df)

        assert len(result.results) == 2
        assert result.passed is True
        assert result.overall_pass_rate == 1.0

    def test_suite_fails_when_any_expectation_fails(self) -> None:
        exp1 = FactualConsistencyExpectation(column="ai_desc", reference_column="spec", threshold=0.95)
        exp1._judge = _mock_judge(passed=True)
        exp2 = LabelAccuracyExpectation(column="label", content_column="text", threshold=0.95)
        exp2._judge = _mock_judge(passed=False)

        suite = SemanticExpectationSuite(name="test_suite").add(exp1).add(exp2)
        df = pd.DataFrame([{"ai_desc": "a", "spec": "a", "label": "pos", "text": "bad"}] * 10)
        result = suite.run(df)
        assert result.passed is False
        assert len(result.failed_expectations()) == 1
