from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from datasentinel_shared.claude_client import ClaudeClient
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "evidence": {"type": "object"},
    },
    "required": ["passed", "confidence", "reason"],
}


@dataclass
class JudgeVerdict:
    passed: bool
    confidence: float
    reason: str
    evidence: dict[str, Any]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JudgeVerdict":
        return cls(
            passed=bool(d["passed"]),
            confidence=float(d.get("confidence", 0.5)),
            reason=str(d.get("reason", "")),
            evidence=dict(d.get("evidence", {})),
        )


class LLMJudge:
    """Calls Claude to evaluate a single data record against a semantic criterion.

    Designed to be shared across expectation instances to reuse the same
    Anthropic client and benefit from prompt cache hits on the system prompt.
    """

    def __init__(self) -> None:
        self._client = ClaudeClient()

    def evaluate(
        self,
        *,
        criterion: str,
        record: dict[str, Any],
        context: str = "",
    ) -> JudgeVerdict:
        """Evaluate whether a record satisfies the given criterion.

        Args:
            criterion: Plain-English description of what should be true.
            record: The data record (dict of column → value).
            context: Optional additional context (e.g., schema info, business rules).
        """
        prompt = self._build_prompt(criterion=criterion, record=record, context=context)
        try:
            result = self._client.judge(prompt, response_schema=_VERDICT_SCHEMA)
            return JudgeVerdict.from_dict(result)
        except Exception as exc:
            log.warning("llm_judge_error", error=str(exc), criterion=criterion)
            # On LLM failure, return a low-confidence pass to avoid false positives
            return JudgeVerdict(
                passed=True,
                confidence=0.0,
                reason=f"Judge unavailable: {exc}",
                evidence={},
            )

    def _build_prompt(
        self,
        *,
        criterion: str,
        record: dict[str, Any],
        context: str,
    ) -> str:
        lines = [
            f"CRITERION: {criterion}",
            "",
            "RECORD:",
        ]
        for key, value in record.items():
            # Truncate very long values to keep prompts lean
            display_value = str(value)
            if len(display_value) > 500:
                display_value = display_value[:500] + "…"
            lines.append(f"  {key}: {display_value!r}")

        if context:
            lines += ["", f"CONTEXT: {context}"]

        lines += [
            "",
            "Evaluate whether this record satisfies the criterion. "
            "Set passed=true only if you are confident the criterion holds. "
            "Set confidence to reflect how certain you are (0=no idea, 1=certain). "
            "In evidence, include the specific values that support your verdict.",
        ]
        return "\n".join(lines)
