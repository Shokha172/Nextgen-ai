"""Grounded AI layer.

Provider-agnostic: a Gemini implementation is used when a key is configured,
otherwise a deterministic narrator renders the same validated fact bundle. No
path in this package may state a number that is not in that bundle.
"""
from app.services.ai.advisor import analyze, ask, build_facts, savings_advice
from app.services.ai.registry import get_provider

__all__ = ["analyze", "ask", "build_facts", "savings_advice", "get_provider"]
