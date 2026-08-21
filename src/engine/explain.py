"""Deterministic explanations.

No LLM. Every sentence is generated from a score component that actually fired,
so an explanation cannot claim something the scorer did not compute. The
strongest components are surfaced first, and a component that did not
participate is never mentioned.

Phase 3 may pass these reasons to an LLM to rewrite in nicer prose, but the
*content* will still originate here.
"""

from __future__ import annotations

from .schemas import ScoreComponent

# A component has to clear this to be worth mentioning as a positive reason.
MENTION_THRESHOLD = 0.55

# Below this, the component is worth mentioning as a caveat instead.
CAVEAT_THRESHOLD = 0.40

MAX_REASONS = 4

_PHRASING = {
    "colour_harmony": "Colour: {detail}",
    "occasion_suitability": "Occasion: {detail}",
    "category_affinity": "Category: {detail}",
    "preference_match": "Preference: {detail}",
    "text_relevance": "Request: {detail}",
}


def _sentence(component: ScoreComponent) -> str:
    template = _PHRASING.get(component.name, "{detail}")
    text = template.format(detail=component.detail)
    return text[0].upper() + text[1:] if text else text


def build_reasons(
    components: tuple[ScoreComponent, ...],
    diversity_note: str | None = None,
) -> tuple[str, ...]:
    """Turn the components that fired into ranked, human-readable reasons."""
    active = [c for c in components if c is not None]
    if not active:
        return ("No scoring signal was available for this product.",)

    # Rank by actual contribution, so the reason shown first is the reason the
    # product ranked where it did - not merely the first component in the list.
    ranked = sorted(active, key=lambda c: -c.contribution)

    reasons = [_sentence(c) for c in ranked if c.raw >= MENTION_THRESHOLD][:MAX_REASONS]

    if not reasons:
        # No component scored strongly; say so rather than return nothing.
        best = ranked[0]
        reasons = [f"Weak match overall - the strongest signal was only "
                   f"{best.raw:.2f}: {best.detail}"]

    caveats = [c for c in ranked if c.raw < CAVEAT_THRESHOLD]
    if caveats and len(reasons) < MAX_REASONS:
        weakest = min(caveats, key=lambda c: c.raw)
        reasons.append(f"Caveat: {weakest.detail}")

    if diversity_note:
        reasons.append(f"Shown for variety ({diversity_note}).")

    return tuple(reasons)


def explain_category(
    category_group: str,
    affinity_explanation: str,
    pool_before: int,
    pool_after: int,
    confidence: str,
) -> str:
    """Why this category was considered, and how much choice there was."""
    base = f"{category_group}: {affinity_explanation}"
    if confidence == "thin":
        return (f"{base}. Only {pool_after} products qualified, so the choice here "
                f"is limited.")
    if confidence == "none":
        return f"{base}. No product in this category met the requirements."
    return f"{base}. {pool_after} of {pool_before} products qualified."
