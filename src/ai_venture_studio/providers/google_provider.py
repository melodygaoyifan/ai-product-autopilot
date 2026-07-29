from __future__ import annotations

import os

import httpx

from ai_venture_studio.providers.base import (
    Provider,
    ProviderError,
    record_stop_reason,
    register,
)


@register
class GoogleProvider(Provider):
    name = "google"

    def chat(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
    ) -> str:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ProviderError("GEMINI_API_KEY / GOOGLE_API_KEY is not set")
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
        ]
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": contents,
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=120,
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usageMetadata") or {}
        if usage:
            from ai_venture_studio import spend

            spend.record(
                model,
                usage.get("promptTokenCount"),
                usage.get("candidatesTokenCount"),
            )
        candidate = body["candidates"][0]
        # Gemini spells it finishReason / "MAX_TOKENS"; the shared reason set in
        # providers/base.py carries both spellings.
        record_stop_reason(candidate.get("finishReason"))
        parts = candidate["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
