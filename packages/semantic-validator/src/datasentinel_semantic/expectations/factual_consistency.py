from __future__ import annotations

from typing import Any

from datasentinel_semantic.core.expectation import SemanticExpectation, Verdict
from datasentinel_semantic.core.judge import LLMJudge


class FactualConsistencyExpectation(SemanticExpectation):
    """Checks that an AI-generated column is factually consistent with a reference column.

    Example: an AI-generated product description should not contradict
    the product's spec sheet stored in another column.
    """

    name = "expect_column_to_be_factually_consistent_with"

    def __init__(
        self,
        column: str,
        reference_column: str,
        context: str = "",
        threshold: float = 0.95,
    ) -> None:
        super().__init__(column)
        self.reference_column = reference_column
        self.context = context
        self.threshold = threshold
        self._judge: LLMJudge | None = None

    @property
    def judge(self) -> LLMJudge:
        if self._judge is None:
            self._judge = LLMJudge()
        return self._judge

    def evaluate_record(self, record: dict[str, Any], index: int) -> Verdict:
        ai_value = record.get(self.column, "")
        reference_value = record.get(self.reference_column, "")

        criterion = (
            f"The AI-generated field '{self.column}' must be factually consistent with "
            f"the reference field '{self.reference_column}'. "
            f"Check that no facts in the AI-generated text contradict the reference. "
            f"Minor paraphrasing is acceptable; factual contradictions are not."
        )

        verdict = self.judge.evaluate(
            criterion=criterion,
            record={
                f"AI-generated ({self.column})": ai_value,
                f"Reference ({self.reference_column})": reference_value,
            },
            context=self.context,
        )

        return Verdict(
            record_index=index,
            passed=verdict.passed,
            confidence=verdict.confidence,
            reason=verdict.reason,
            evidence={
                "ai_value": str(ai_value)[:300],
                "reference_value": str(reference_value)[:300],
                **verdict.evidence,
            },
        )
