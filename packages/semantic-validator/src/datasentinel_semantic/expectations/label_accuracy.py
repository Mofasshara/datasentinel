from __future__ import annotations

from typing import Any

from datasentinel_semantic.core.expectation import SemanticExpectation, Verdict
from datasentinel_semantic.core.judge import LLMJudge


class LabelAccuracyExpectation(SemanticExpectation):
    """Verifies that AI-assigned classification labels match the record content.

    Example: a sentiment label of "positive" should genuinely reflect
    the sentiment of the review text in another column.
    """

    name = "expect_label_to_match_content"

    def __init__(
        self,
        column: str,
        content_column: str,
        label_descriptions: dict[str, str] | None = None,
        threshold: float = 0.90,
    ) -> None:
        super().__init__(column)
        self.content_column = content_column
        self.label_descriptions = label_descriptions or {}
        self.threshold = threshold
        self._judge: LLMJudge | None = None

    @property
    def judge(self) -> LLMJudge:
        if self._judge is None:
            self._judge = LLMJudge()
        return self._judge

    def evaluate_record(self, record: dict[str, Any], index: int) -> Verdict:
        label = record.get(self.column, "")
        content = record.get(self.content_column, "")

        label_hint = ""
        if self.label_descriptions:
            label_hint = " Label meanings: " + "; ".join(
                f"{k}={v}" for k, v in self.label_descriptions.items()
            )

        criterion = (
            f"The AI-assigned label in '{self.column}' must accurately reflect "
            f"the content in '{self.content_column}'.{label_hint} "
            f"Judge whether the label genuinely matches the content."
        )

        verdict = self.judge.evaluate(
            criterion=criterion,
            record={
                f"AI label ({self.column})": label,
                f"Content ({self.content_column})": content,
            },
        )

        return Verdict(
            record_index=index,
            passed=verdict.passed,
            confidence=verdict.confidence,
            reason=verdict.reason,
            evidence={
                "label": str(label),
                "content_snippet": str(content)[:200],
                **verdict.evidence,
            },
        )
