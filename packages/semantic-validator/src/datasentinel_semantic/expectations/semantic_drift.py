from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from datasentinel_semantic.core.expectation import ExpectationResult, SemanticExpectation, Verdict
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


class SemanticDriftExpectation(SemanticExpectation):
    """Detects semantic drift in an AI-generated column over time.

    Computes embeddings for the current batch and compares their centroid
    against a stored historical baseline. Fires if cosine distance exceeds
    the threshold — indicating the AI's output character has shifted.

    Unlike the other expectations, this uses embeddings rather than LLM-per-row,
    making it efficient for large datasets. The baseline is updated on each run.
    """

    name = "expect_semantic_drift_below"

    def __init__(
        self,
        column: str,
        threshold: float = 0.15,
        lookback_days: int = 7,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        super().__init__(column)
        self.threshold = threshold
        self.lookback_days = lookback_days
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._baseline_centroid: np.ndarray | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            log.info("loading_embedding_model", model=self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def set_baseline(self, baseline_centroid: np.ndarray) -> None:
        """Inject a pre-computed baseline centroid (e.g., loaded from Postgres)."""
        self._baseline_centroid = baseline_centroid

    def evaluate_record(self, record: dict[str, Any], index: int) -> Verdict:
        raise NotImplementedError("SemanticDriftExpectation overrides evaluate() directly")

    def evaluate(self, df: pd.DataFrame) -> ExpectationResult:
        if self.column not in df.columns:
            raise ValueError(f"Column '{self.column}' not found in DataFrame")

        texts = df[self.column].fillna("").astype(str).tolist()
        embeddings = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        current_centroid = np.mean(embeddings, axis=0)

        if self._baseline_centroid is None:
            # First run — store baseline, pass with full confidence
            self._baseline_centroid = current_centroid
            log.info("drift_baseline_initialized", column=self.column)
            return ExpectationResult(
                expectation_name=self.name,
                column_name=self.column,
                total_records=len(df),
                passed_records=len(df),
                failed_records=0,
                verdicts=[],
            ).with_threshold(self.threshold)

        # Cosine distance: 1 - cosine_similarity (embeddings are already L2-normalized)
        cosine_sim = float(np.dot(current_centroid, self._baseline_centroid))
        drift = 1.0 - cosine_sim

        passed = drift <= self.threshold
        log.info("drift_computed", column=self.column, drift=f"{drift:.4f}", threshold=self.threshold, passed=passed)

        # Update baseline with exponential moving average to track slow evolution
        alpha = 0.1
        self._baseline_centroid = (1 - alpha) * self._baseline_centroid + alpha * current_centroid

        if not passed:
            verdict = Verdict(
                record_index=-1,
                passed=False,
                confidence=1.0,
                reason=(
                    f"Semantic drift detected: cosine distance {drift:.4f} "
                    f"exceeds threshold {self.threshold}. "
                    f"The AI-generated outputs in '{self.column}' have shifted "
                    f"significantly from the {self.lookback_days}-day baseline."
                ),
                evidence={"drift_score": drift, "threshold": self.threshold, "cosine_similarity": cosine_sim},
            )
            verdicts = [verdict]
        else:
            verdicts = []

        return ExpectationResult(
            expectation_name=self.name,
            column_name=self.column,
            total_records=len(df),
            passed_records=len(df) if passed else 0,
            failed_records=0 if passed else len(df),
            verdicts=verdicts,
        ).with_threshold(self.threshold)
