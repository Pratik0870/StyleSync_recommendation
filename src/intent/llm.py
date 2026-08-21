"""LLM-backed intent extraction.

Scope is deliberately tiny: natural language in, `ExtractedIntent` out. The
model never sees the catalog, never sees a product, and has no field in which to
return one. It cannot select, rank, price or score anything.

This module is the *policy* layer - credential detection, circuit breaking,
error normalisation. The actual API call lives in `providers.py`, so changing
provider changes one class and nothing else. The recommendation engine is
untouched either way.

Failure is expected and cheap: no credentials, a rate limit, a timeout or a
malformed response all raise `IntentLLMError`, and the caller falls back to the
deterministic parser. A circuit breaker stops a broken provider from adding
latency to every request.
"""

from __future__ import annotations

import logging
import os
import time

from .providers import ProviderError, build_provider, detect_provider_name
from .schema import ExtractedIntent

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 2000

# Circuit breaker: after this many consecutive failures, stop calling out for
# `COOLDOWN_SECONDS` so a dead provider costs one timeout, not one per request.
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 60.0


def _default_model_for(provider_name: str) -> str:
    """The model a provider would use, for reporting before it is constructed."""
    from .providers import PROVIDERS

    factory = PROVIDERS.get(provider_name)
    return getattr(factory, "default_model", "") if factory else ""


# What went wrong, in terms a user interface can act on. The raw provider text
# (quota tables, request URLs, stack traces) must never reach a browser, so it
# is logged server-side and reduced to one of these.
QUOTA = "quota"
AUTH = "auth"
NETWORK = "network"
TIMEOUT = "timeout"
UNAVAILABLE = "unavailable"
NOT_CONFIGURED = "not_configured"

_TEMPORARY = "AI search is temporarily unavailable. Showing catalog-based matches."
_UNCONFIGURED = "AI search is not configured. Showing catalog-based matches."

# What the user is told. Deliberately free of provider names and error codes.
FAILURE_MESSAGES = {
    QUOTA: _TEMPORARY,
    NETWORK: _TEMPORARY,
    TIMEOUT: _TEMPORARY,
    UNAVAILABLE: _TEMPORARY,
    AUTH: _UNCONFIGURED,
    NOT_CONFIGURED: _UNCONFIGURED,
}

# The label shown as a status indicator.
STATUS_LABELS = {
    "available": "AI Search Available",
    QUOTA: "AI Search Temporarily Unavailable",
    NETWORK: "AI Search Temporarily Unavailable",
    TIMEOUT: "AI Search Temporarily Unavailable",
    UNAVAILABLE: "AI Search Temporarily Unavailable",
    AUTH: "AI Search Configuration Error",
    NOT_CONFIGURED: "AI Search Not Configured",
}

_QUOTA_MARKERS = ("429", "resource_exhausted", "quota", "rate limit", "ratelimit")
_AUTH_MARKERS = ("api key", "api_key", "unauthorized", "401", "403", "permission",
                 "authentication", "credential", "permission_denied")
_TIMEOUT_MARKERS = ("timeout", "timed out", "deadline")
_NETWORK_MARKERS = ("connection", "network", "dns", "unreachable")
# The provider answered - it is just busy. That is not a network fault.
_OVERLOADED_MARKERS = ("503", "502", "unavailable", "overloaded",
                       "temporarily unavailable")


_UNCONFIGURED_MARKERS = ("no credentials", "credentials found", "not configured",
                         "no llm provider")


def classify_failure(error: object) -> str:
    """Reduce any provider error to one actionable kind."""
    text = str(error).lower()
    # Checked first: "set ANTHROPIC_API_KEY" mentions a key but means the
    # install has none, which is not the same as a rejected one.
    if any(marker in text for marker in _UNCONFIGURED_MARKERS):
        return NOT_CONFIGURED
    if any(marker in text for marker in _QUOTA_MARKERS):
        return QUOTA
    if any(marker in text for marker in _AUTH_MARKERS):
        return AUTH
    if any(marker in text for marker in _TIMEOUT_MARKERS):
        return TIMEOUT
    if any(marker in text for marker in _NETWORK_MARKERS):
        return NETWORK
    if any(marker in text for marker in _OVERLOADED_MARKERS):
        return UNAVAILABLE
    return UNAVAILABLE


class IntentLLMError(RuntimeError):
    """Raised whenever the LLM path cannot produce a validated intent.

    `kind` is one of the constants above, so a caller can react without parsing
    the message - which is for logs only and never for a browser.
    """

    def __init__(self, message: str, kind: str = UNAVAILABLE):
        super().__init__(message)
        self.kind = kind


class IntentLLM:
    """Provider-agnostic wrapper around intent extraction."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._init_error: str | None = None
        self._consecutive_failures = 0
        self._last_failure_kind = UNAVAILABLE
        self._open_until = 0.0
        self._client = None                     # the provider, once constructed

        self.provider_name = detect_provider_name() or "none"
        self.model = model or os.environ.get("LLM_MODEL") or _default_model_for(
            self.provider_name)

        try:
            provider = build_provider(api_key=api_key, model=model)
        except ProviderError as exc:
            self._init_error = str(exc)
            return
        except Exception as exc:                 # pragma: no cover - defensive
            self._init_error = f"{type(exc).__name__}: {exc}"
            return

        self._client = provider
        self.provider_name = provider.name
        self.model = provider.model

    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        if self._client is None:
            return False
        return time.monotonic() >= self._open_until

    @property
    def status(self) -> dict:
        """Provider health.

        `state` and `label` are safe to show anywhere. `reason` carries the
        provider's own wording and belongs in logs and the developer status
        endpoint, never on a product page.
        """
        base = {"provider": getattr(self, "provider_name", "unknown"),
                "model": self.model}
        if self._client is None:
            state = classify_failure(self._init_error) if self._init_error \
                else NOT_CONFIGURED
            return {**base, "available": False, "state": state,
                    "label": STATUS_LABELS.get(state, STATUS_LABELS[UNAVAILABLE]),
                    "reason": self._init_error or "not configured"}
        if time.monotonic() < self._open_until:
            state = self._last_failure_kind
            return {**base, "available": False, "state": state,
                    "label": STATUS_LABELS.get(state, STATUS_LABELS[UNAVAILABLE]),
                    "reason": f"circuit breaker open after "
                              f"{self._consecutive_failures} consecutive failures "
                              f"({state})",
                    "retry_in_seconds": round(self._open_until - time.monotonic(), 1)}
        # The breaker opens only after several consecutive failures, so a
        # provider that just rejected a call still reports as callable. It is
        # callable, but it is not working - and a status badge must say the
        # second thing, not the first.
        if self._consecutive_failures:
            state = self._last_failure_kind
            return {**base, "available": True, "state": state,
                    "label": STATUS_LABELS.get(state, STATUS_LABELS[UNAVAILABLE]),
                    "last_failure": state,
                    "reason": f"{self._consecutive_failures} recent failure(s) "
                              f"({state})"}
        return {**base, "available": True, "state": "available",
                "label": STATUS_LABELS["available"],
                "last_failure": self._last_failure_kind}

    # ------------------------------------------------------------------

    def extract(self, query: str) -> ExtractedIntent:
        """Natural language -> validated `ExtractedIntent`.

        Raises `IntentLLMError` for every failure mode so the caller has exactly
        one thing to catch.
        """
        if self._client is None:
            raise IntentLLMError(self._init_error or "no LLM provider configured",
                                 NOT_CONFIGURED)
        if time.monotonic() < self._open_until:
            raise IntentLLMError("LLM circuit breaker is open",
                                 self._last_failure_kind)

        text = (query or "").strip()[:MAX_QUERY_CHARS]
        if not text:
            raise IntentLLMError("empty query", UNAVAILABLE)

        try:
            parsed = self._client.extract(text)
        except ProviderError as exc:
            kind = classify_failure(exc)
            self._record_failure(kind)
            # Full detail goes to the server log; the caller gets the kind only.
            logger.warning("LLM intent extraction failed (%s): %s", kind, exc)
            raise IntentLLMError(str(exc), kind) from exc
        except Exception as exc:
            kind = classify_failure(exc)
            self._record_failure(kind)
            logger.warning("unexpected LLM failure (%s): %s", kind, exc)
            raise IntentLLMError(f"unexpected LLM failure: {exc}", kind) from exc

        if not isinstance(parsed, ExtractedIntent):
            self._record_failure(UNAVAILABLE)
            raise IntentLLMError(
                "LLM response did not validate against the intent schema", UNAVAILABLE)

        self._consecutive_failures = 0
        self._last_failure_kind = UNAVAILABLE
        return parsed

    # ------------------------------------------------------------------

    def _record_failure(self, kind: str = UNAVAILABLE) -> None:
        self._last_failure_kind = kind
        self._consecutive_failures += 1
        if self._consecutive_failures >= FAILURE_THRESHOLD:
            self._open_until = time.monotonic() + COOLDOWN_SECONDS
            logger.warning(
                "LLM circuit breaker opened for %ss after %d consecutive failures",
                COOLDOWN_SECONDS, self._consecutive_failures)
