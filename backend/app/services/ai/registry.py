"""Provider selection: Gemini when configured, deterministic otherwise."""
from __future__ import annotations

import logging

from app.core.config import settings
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.gemini import GeminiProvider
from app.services.ai.rule import RuleBasedProvider

log = logging.getLogger("nextgen.ai")


def get_provider(*, language: str = "uz") -> AIProvider:
    choice = settings.AI_PROVIDER
    if choice == "rule_based":
        return RuleBasedProvider(language)
    if choice in ("auto", "gemini") and settings.GEMINI_API_KEY:
        try:
            return GeminiProvider()
        except AIProviderError as exc:
            log.warning("Gemini unavailable, using deterministic narrator: %s", exc)
    return RuleBasedProvider(language)
