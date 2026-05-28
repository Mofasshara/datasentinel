from __future__ import annotations

from typing import Any

from datasentinel_semantic.core.expectation import SemanticExpectation, Verdict
from datasentinel_semantic.core.judge import LLMJudge


class HallucinationDetectionExpectation(SemanticExpectation):
    """Detects hallucinated entities in AI-generated text.

    Checks that names, identifiers, numbers, and dates mentioned in an
    AI-generated column are traceable to the provided source columns —
    not invented by the model.
    """

    name = "expect_column_to_not_hallucinate_entities"

    def __init__(
        self,
        column: str,
        source_columns: list[str],
        entity_types: list[str] | None = None,
        threshold: float = 0.95,
    ) -> None:
        super().__init__(column)
        self.source_columns = source_columns
        self.entity_types = entity_types or ["product codes", "brand names", "model numbers", "dates", "prices"]
        self.threshold = threshold
        self._judge: LLMJudge | None = None

    @property
    def judge(self) -> LLMJudge:
        if self._judge is None:
            self._judge = LLMJudge()
        return self._judge

    def evaluate_record(self, record: dict[str, Any], index: int) -> Verdict:
        ai_value = record.get(self.column, "")
        source_values = {col: record.get(col, "") for col in self.source_columns}

        entity_list = ", ".join(self.entity_types)
        criterion = (
            f"The AI-generated field '{self.column}' must not contain hallucinated entities. "
            f"Check for: {entity_list}. "
            f"Every specific {entity_list} mentioned in the AI text must be verifiable "
            f"from the provided source fields. Flag any that cannot be confirmed."
        )

        record_for_judge = {f"AI-generated ({self.column})": ai_value}
        record_for_judge.update({f"Source ({k})": v for k, v in source_values.items()})

        verdict = self.judge.evaluate(criterion=criterion, record=record_for_judge)

        return Verdict(
            record_index=index,
            passed=verdict.passed,
            confidence=verdict.confidence,
            reason=verdict.reason,
            evidence={
                "ai_value": str(ai_value)[:300],
                "source_values": {k: str(v)[:100] for k, v in source_values.items()},
                **verdict.evidence,
            },
        )
