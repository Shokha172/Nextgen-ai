"""Provider contract shared by every AI implementation."""
from __future__ import annotations

from typing import Protocol


class AIProviderError(RuntimeError):
    """Raised when a provider is unavailable or returned something unusable.

    The advisor catches this and answers with the deterministic narrator instead,
    so a provider outage never produces an error page or an invented figure.
    """


class AIProvider(Protocol):
    name: str
    model: str | None

    def complete(self, *, system: str, user: str) -> str:  # pragma: no cover - protocol
        """Return a narration for `user`, constrained by `system`."""
        ...
