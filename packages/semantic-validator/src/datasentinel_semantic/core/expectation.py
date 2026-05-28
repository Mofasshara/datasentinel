from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class Verdict:
    """Result for a single record evaluation."""
    record_index: int
    passed: bool
    confidence: float        # 0.0 – 1.0
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExpectationResult:
    """Aggregated result for one expectation run over a dataset."""
    expectation_name: str
    column_name: str
    total_records: int
    passed_records: int
    failed_records: int
    verdicts: list[Verdict] = field(default_factory=list)  # sampled failures only

    @property
    def pass_rate(self) -> float:
        return self.passed_records / self.total_records if self.total_records else 0.0

    @property
    def passed(self) -> bool:
        return self.pass_rate >= self._threshold

    def __post_init__(self) -> None:
        self._threshold: float = 0.95

    def with_threshold(self, threshold: float) -> "ExpectationResult":
        self._threshold = threshold
        return self

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.expectation_name}({self.column_name}) "
            f"pass_rate={self.pass_rate:.1%} "
            f"({self.passed_records}/{self.total_records})"
        )


class SemanticExpectation(ABC):
    """Base class for all semantic expectations.

    Subclasses implement evaluate_record() for per-row LLM judgement
    and can override evaluate() for batch/embedding-based checks.
    """

    #: Override in subclasses — used as the expectation name in results
    name: str = "semantic_expectation"

    #: Minimum pass rate to consider the expectation met (overridable per instance)
    threshold: float = 0.95

    #: Max number of failure verdicts to store (avoids unbounded memory)
    max_failures_stored: int = 100

    def __init__(self, column: str, **kwargs: Any) -> None:
        self.column = column

    @abstractmethod
    def evaluate_record(
        self,
        record: dict[str, Any],
        index: int,
    ) -> Verdict:
        """Evaluate a single record. Called row-by-row by evaluate()."""

    def evaluate(self, df: pd.DataFrame) -> ExpectationResult:
        """Run the expectation over an entire DataFrame.

        Default implementation calls evaluate_record() per row.
        Override for batch-efficient checks (e.g., embedding-based drift).
        """
        if self.column not in df.columns:
            raise ValueError(f"Column '{self.column}' not found in DataFrame. Available: {list(df.columns)}")

        verdicts: list[Verdict] = []
        passed = 0
        failures_stored = 0

        for idx, row in df.iterrows():
            v = self.evaluate_record(row.to_dict(), int(str(idx)))
            if v.passed:
                passed += 1
            else:
                if failures_stored < self.max_failures_stored:
                    verdicts.append(v)
                    failures_stored += 1

        total = len(df)
        result = ExpectationResult(
            expectation_name=self.name,
            column_name=self.column,
            total_records=total,
            passed_records=passed,
            failed_records=total - passed,
            verdicts=verdicts,
        ).with_threshold(self.threshold)

        return result
