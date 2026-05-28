from __future__ import annotations

import json
from typing import Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from datasentinel_shared.config import get_settings
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)

# System prompt cached across all calls — reduces cost significantly
_SYSTEM_PROMPT = (
    "You are DataSentinel's evaluation engine. "
    "You assess data quality with precision and always respond with valid JSON. "
    "Be concise. Never fabricate evidence — only use what is provided in the record."
)


class ClaudeClient:
    """Thin wrapper around the Anthropic SDK with prompt caching and retry logic."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._max_tokens = settings.claude_max_tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def judge(
        self,
        user_prompt: str,
        *,
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Call Claude and return a parsed JSON response.

        Uses prompt caching on the system prompt to reduce costs on repeated calls.
        """
        system: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        if response_schema:
            schema_hint = f"\nRespond ONLY with a JSON object matching this schema:\n{json.dumps(response_schema, indent=2)}"
            user_prompt = user_prompt + schema_hint

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = response.content[0].text.strip()

        # Strip markdown fences if Claude wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        parsed: dict[str, Any] = json.loads(raw)
        log.debug(
            "claude_judge_complete",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read=getattr(response.usage, "cache_read_input_tokens", 0),
        )
        return parsed

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def complete(self, user_prompt: str, *, temperature: float = 0.0) -> str:
        """Plain text completion — used by the pipeline agent for SQL generation."""
        system: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": "You are DataSentinel's remediation engine. Write correct, minimal SQL and dbt model patches.",
                "cache_control": {"type": "ephemeral"},
            }
        ]

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text.strip()
