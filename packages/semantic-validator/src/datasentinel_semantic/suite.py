from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from datasentinel_semantic.core.expectation import ExpectationResult, SemanticExpectation
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


@dataclass
class SuiteResult:
    suite_name: str
    run_id: str
    run_at: datetime
    results: list[ExpectationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def overall_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        total = sum(r.total_records for r in self.results)
        passed = sum(r.passed_records for r in self.results)
        return passed / total if total else 0.0

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"Suite: {self.suite_name}  [{status}]",
            f"Run:   {self.run_id}  at {self.run_at.isoformat()}",
            f"Overall pass rate: {self.overall_pass_rate:.1%}",
            "",
        ]
        for r in self.results:
            lines.append(f"  {r!r}")
        return "\n".join(lines)

    def failed_expectations(self) -> list[ExpectationResult]:
        return [r for r in self.results if not r.passed]


class SemanticExpectationSuite:
    """Runs a collection of SemanticExpectation objects against a DataFrame."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._expectations: list[SemanticExpectation] = []

    def add(self, expectation: SemanticExpectation) -> "SemanticExpectationSuite":
        """Add an expectation. Returns self for chaining."""
        self._expectations.append(expectation)
        return self

    def run(self, df: pd.DataFrame, *, sample_size: int | None = None) -> SuiteResult:
        """Run all expectations against df.

        Args:
            df: The DataFrame to validate.
            sample_size: If set, randomly sample this many rows before evaluating.
                         Useful for large datasets where LLM cost matters.
        """
        if sample_size and len(df) > sample_size:
            df = df.sample(n=sample_size, random_state=42).reset_index(drop=True)
            log.info("suite_sampled", original=len(df), sample=sample_size)

        run_id = str(uuid.uuid4())
        run_at = datetime.now(tz=timezone.utc)

        log.info("suite_started", suite=self.name, run_id=run_id, rows=len(df), expectations=len(self._expectations))

        results: list[ExpectationResult] = []
        for exp in self._expectations:
            log.info("expectation_started", name=exp.name, column=exp.column)
            result = exp.evaluate(df)
            results.append(result)
            log.info(
                "expectation_complete",
                name=exp.name,
                column=exp.column,
                pass_rate=f"{result.pass_rate:.1%}",
                passed=result.passed,
            )

        suite_result = SuiteResult(
            suite_name=self.name,
            run_id=run_id,
            run_at=run_at,
            results=results,
        )

        log.info(
            "suite_complete",
            suite=self.name,
            run_id=run_id,
            overall_pass_rate=f"{suite_result.overall_pass_rate:.1%}",
            passed=suite_result.passed,
        )
        return suite_result
