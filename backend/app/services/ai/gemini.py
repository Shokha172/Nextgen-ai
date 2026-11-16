"""Google Gemini provider (optional, replaceable).

Only the aggregated fact bundle is sent — never raw readings, member records or
another tenant's data. Any transport or schema failure raises AIProviderError so
the advisor can fall back to the deterministic, fully grounded narrator.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.services.ai.base import AIProviderError

log = logging.getLogger("nextgen.ai")

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 timeout: float | None = None) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.timeout = timeout or settings.GEMINI_TIMEOUT_S
        if not self.api_key:
            raise AIProviderError("GEMINI_API_KEY is not configured")

    def complete(self, *, system: str, user: str) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2,
                                 "maxOutputTokens": settings.AI_MAX_TOKENS},
        }
        try:
            response = httpx.post(ENDPOINT.format(model=self.model),
                                  params={"key": self.api_key}, json=payload,
                                  timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError(f"Gemini request failed: {exc}") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            raise AIProviderError("Gemini returned no candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise AIProviderError("Gemini returned an empty answer")
        return text
