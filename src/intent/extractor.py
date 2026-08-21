"""Intent extraction with a guaranteed deterministic floor.

    natural language
          |
     LLM (optional)  --failure-->  deterministic parser
          |                              |
          +------------ normalise -------+
                          |
                  NormalisedIntent  ->  the engine

Both paths converge on the same `normalise()` call, so whichever ran, the engine
receives values drawn only from its own vocabulary. The path that answered is
reported on every response rather than hidden.
"""

from __future__ import annotations

import logging

from . import fallback
from .llm import FAILURE_MESSAGES, UNAVAILABLE, IntentLLM, IntentLLMError
from .schema import ExtractedIntent, NormalisedIntent, normalise

logger = logging.getLogger(__name__)


class IntentExtractor:
    def __init__(self, known_groups: set[str], llm: IntentLLM | None = None,
                 use_llm: bool = True):
        self.known_groups = known_groups
        self.llm = llm if llm is not None else (IntentLLM() if use_llm else None)

    @property
    def llm_status(self) -> dict:
        """Always the same shape, so /health and the UI can rely on it."""
        if self.llm is None:
            from .providers import detect_provider_name

            return {
                "available": False,
                "reason": "LLM disabled by configuration",
                "provider": detect_provider_name() or "none",
                "model": "",
            }
        return self.llm.status

    def extract(self, query: str) -> tuple[NormalisedIntent, list[str]]:
        """Return the normalised intent plus any notes for the caller."""
        notes: list[str] = []
        text = (query or "").strip()

        extracted: ExtractedIntent | None = None
        source = "fallback"
        degraded: str | None = None

        if text and self.llm is not None and self.llm.available:
            try:
                extracted = self.llm.extract(text)
                source = "llm"
                logger.info("[LLM] Request successful")
            except IntentLLMError as exc:
                # The provider's own text can carry quota tables, request URLs
                # and stack traces. It belongs in the log, not in a browser.
                logger.warning("[LLM] Fallback activated: %s", exc.kind)
                logger.debug("[LLM] provider detail: %s", exc)
                degraded = exc.kind
        elif text and self.llm is not None:
            status = self.llm.status
            degraded = status.get("state", UNAVAILABLE)
            logger.warning("[LLM] Fallback activated: %s", degraded)
            logger.debug("[LLM] provider detail: %s", status.get("reason"))

        if extracted is None:
            extracted = fallback.parse(text)

        intent = normalise(extracted, self.known_groups, source)

        if degraded:
            notes.append(FAILURE_MESSAGES.get(degraded, FAILURE_MESSAGES[UNAVAILABLE]))

        if intent.rejected:
            notes.append(
                "Ignored values the catalog does not recognise: "
                + ", ".join(intent.rejected) + ".")
        if text and intent.is_empty():
            notes.append(
                "AI search is currently unavailable and we couldn't confidently "
                "match this request." if degraded else
                "Nothing usable could be extracted from the request - no garment, "
                "colour, occasion, style or category was recognised.")

        return intent, notes


def intent_to_engine_request(intent: NormalisedIntent, limit: int, max_per_category: int):
    """Map a normalised intent onto the Phase 2 engine's request objects."""
    from ..engine.schemas import Anchor, LookRequest, Preferences

    return LookRequest(
        anchor=Anchor(
            product_id=None,
            anchor_type=intent.anchor_type,
            colour=intent.colour,
        ),
        preferences=Preferences(
            occasion=intent.occasion,
            style=intent.style,
            gender=intent.gender,
            preferred_colours=intent.preferred_colours,
            include_categories=intent.include_categories,
            exclude_categories=intent.exclude_categories,
            free_text=intent.free_text,
            max_per_category=max_per_category,
            limit=limit,
        ),
    )
