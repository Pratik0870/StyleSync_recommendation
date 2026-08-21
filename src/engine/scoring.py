"""The hybrid score.

    score = sum(weight_i * raw_i) / sum(weight_i)   over *active* components

Components are only active when the request actually supplies the signal, and
the divisor renormalises accordingly. This matters: if the user names no
occasion, occasion suitability is not silently scored 0.5 and mixed in - it is
absent, and the remaining components carry the full weight. A missing signal
should not look like a mediocre one.

Every component returns a `raw` value in 0..1, its weight, and a sentence
explaining itself, so the final number is always decomposable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .affinity import product_type_relevance
from .colour import harmony, hue_distance
from .occasion import beauty_suitability, catalog_suitability
from .relevance import Relevance
from .schemas import ScoreComponent

# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreConfig:
    """All tunable weights in one place.

    Rationale for the ordering:

      colour       the largest weight, because colour coordination is the whole
                   premise of cross-category complementary recommendation and
                   is the one signal the catalog supports at 100% coverage.
      occasion     second, because it is what makes a wedding answer differ from
                   an everyday one, and it is reliable for 41,032 products and
                   derived transparently for the remaining 2,133.
      affinity     third: it decides *which categories* appear, so it already
                   exerts influence through category selection; weighting it
                   heavily again inside the item score would double-count it.
      preference   explicit user asks, applied as a moderate nudge rather than a
                   filter so a good match is not lost on a soft preference.
      text         smallest, and deliberately so - measured to add value only
                   for material/pattern terms (see relevance.py).
    """

    colour: float = 0.35
    occasion: float = 0.25
    affinity: float = 0.18
    preference: float = 0.14
    text: float = 0.08

    def as_dict(self) -> dict[str, float]:
        return {
            "colour_harmony": self.colour,
            "occasion_suitability": self.occasion,
            "category_affinity": self.affinity,
            "preference_match": self.preference,
            "text_relevance": self.text,
        }


DEFAULT_CONFIG = ScoreConfig()


# --------------------------------------------------------------------------
# Style profiles - what a style word means in terms the catalog can express
# --------------------------------------------------------------------------
# The catalog carries colour family, metallic/neutral flags, and a parsed
# finish. A style profile can therefore only be expressed in those terms, which
# is exactly what these are. Anything not listed scores `neutral_preference`.

@dataclass(frozen=True)
class StyleProfile:
    colours: dict[str, float] = field(default_factory=dict)
    finishes: dict[str, float] = field(default_factory=dict)
    prefers_metallic: bool | None = None
    description: str = ""


STYLE_PROFILES: dict[str, StyleProfile] = {
    "elegant": StyleProfile(
        colours={"black": 0.95, "gold": 1.00, "red": 0.90, "purple": 0.88,
                 "silver": 0.90, "beige": 0.82, "brown": 0.80, "white": 0.75,
                 "green": 0.70, "blue": 0.70, "pink": 0.68, "multi": 0.50,
                 "orange": 0.50, "yellow": 0.45},
        finishes={"matte": 1.00, "satin": 0.95, "metallic": 0.88,
                  "shimmer": 0.72, "gloss": 0.62},
        prefers_metallic=True,
        description="elegant looks favour deep or metallic tones and matte finishes",
    ),
    "minimal": StyleProfile(
        colours={"black": 0.95, "white": 0.95, "beige": 0.95, "grey": 0.92,
                 "silver": 0.85, "brown": 0.75, "gold": 0.60, "blue": 0.60,
                 "red": 0.45, "pink": 0.45, "multi": 0.20},
        finishes={"matte": 1.00, "satin": 0.88, "gloss": 0.70,
                  "shimmer": 0.40, "metallic": 0.45},
        prefers_metallic=False,
        description="minimal looks stay with neutral tones and understated finishes",
    ),
    "bold": StyleProfile(
        colours={"red": 1.00, "purple": 0.92, "pink": 0.90, "orange": 0.85,
                 "yellow": 0.80, "green": 0.78, "blue": 0.78, "multi": 0.75,
                 "gold": 0.80, "black": 0.70, "beige": 0.35, "white": 0.35},
        finishes={"shimmer": 1.00, "metallic": 0.95, "gloss": 0.85,
                  "matte": 0.75, "satin": 0.70},
        description="bold looks lean on saturated colour and high-impact finishes",
    ),
    "traditional": StyleProfile(
        colours={"gold": 1.00, "red": 0.98, "green": 0.85, "purple": 0.82,
                 "brown": 0.78, "silver": 0.72, "pink": 0.70, "multi": 0.70,
                 "black": 0.55, "white": 0.45, "grey": 0.35},
        finishes={"matte": 0.90, "shimmer": 0.85, "metallic": 0.90,
                  "satin": 0.80, "gloss": 0.70},
        prefers_metallic=True,
        description="traditional looks centre on gold and rich festive colour",
    ),
    "modern": StyleProfile(
        colours={"black": 0.95, "silver": 0.92, "white": 0.88, "grey": 0.85,
                 "blue": 0.80, "beige": 0.75, "pink": 0.65, "gold": 0.60,
                 "multi": 0.45},
        finishes={"matte": 0.95, "gloss": 0.85, "satin": 0.80,
                  "metallic": 0.80, "shimmer": 0.65},
        description="modern looks favour clean neutrals and cool metallics",
    ),
    "glam": StyleProfile(
        colours={"gold": 1.00, "red": 0.95, "silver": 0.92, "purple": 0.88,
                 "pink": 0.85, "black": 0.85, "multi": 0.60, "beige": 0.40},
        finishes={"shimmer": 1.00, "metallic": 1.00, "gloss": 0.88,
                  "satin": 0.72, "matte": 0.68},
        prefers_metallic=True,
        description="glam looks want shimmer, metallics and statement colour",
    ),
}

_STYLE_SYNONYMS = {
    "elegant": "elegant", "classy": "elegant", "sophisticated": "elegant",
    "graceful": "elegant", "understated": "minimal", "minimal": "minimal",
    "simple": "minimal", "subtle": "minimal", "clean": "minimal",
    "bold": "bold", "statement": "bold", "vibrant": "bold", "bright": "bold",
    "traditional": "traditional", "ethnic": "traditional",
    "festive": "traditional", "classic": "traditional",
    "modern": "modern", "contemporary": "modern", "chic": "modern",
    "sleek": "modern", "glam": "glam", "glamorous": "glam",
    "party": "glam", "dramatic": "glam",
}

NEUTRAL_PREFERENCE = 0.60      # score when we have no opinion


def normalise_style(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.strip().lower()
    if lowered in _STYLE_SYNONYMS:
        return _STYLE_SYNONYMS[lowered]
    for word, canonical in _STYLE_SYNONYMS.items():
        if word in lowered:
            return canonical
    return None


# --------------------------------------------------------------------------
# Component builders
# --------------------------------------------------------------------------


def colour_component(
    anchor_family: str | None,
    product_colour_family: str,
    product_colour_role: str,
    weight: float,
) -> ScoreComponent | None:
    """Colour harmony - only for products whose colour is a styling decision.

    This enforces the Phase 1 rule directly: a foundation shade (`skin_match`)
    matches a face, and a bottle colour (`packaging`) matches nothing. Neither
    may be compared against an outfit colour, so no colour component is produced
    for them at all and the remaining components carry the full weight.
    """
    if anchor_family is None:
        return None
    if product_colour_role != "style":
        return None
    result = harmony(anchor_family, product_colour_family)
    return ScoreComponent("colour_harmony", result.score, weight, result.explanation)


def occasion_component(
    domain: str,
    requested_occasion: str | None,
    product_occasion: str,
    category_group: str,
    colour_family: str,
    colour_role: str,
    finish: str | None,
    weight: float,
) -> ScoreComponent | None:
    if requested_occasion is None:
        return None
    if domain == "beauty":
        result = beauty_suitability(
            category_group, colour_family, colour_role, finish, requested_occasion)
    else:
        result = catalog_suitability(product_occasion, requested_occasion)
    return ScoreComponent("occasion_suitability", result.score, weight, result.explanation)


def affinity_component(
    affinity_score: float,
    explanation: str,
    weight: float,
    product_type: str | None = None,
) -> ScoreComponent:
    """Category affinity, refined by product type where the group is too coarse.

    `fragrance` holds both perfume and deodorant; `beauty_face` holds both blush
    and concealer. One affinity number for the whole group would rank a
    deodorant as highly as a perfume for a wedding.
    """
    raw, note = affinity_score, None
    if product_type is not None:
        modifier, reason = product_type_relevance(product_type)
        if modifier != 1.0:
            raw = affinity_score * modifier
            note = reason
    detail = explanation if note is None else f"{explanation}; {note}"
    return ScoreComponent("category_affinity", raw, weight, detail)


def preference_component(
    style: str | None,
    preferred_colours: tuple[str, ...],
    product_colour_family: str,
    product_colour_role: str,
    is_metallic: bool,
    finish: str | None,
    weight: float,
) -> ScoreComponent | None:
    """Explicit user preferences: requested colours and requested style."""
    signals: list[float] = []
    details: list[str] = []

    if preferred_colours:
        if product_colour_family in preferred_colours:
            signals.append(1.0)
            details.append(f"is the requested {product_colour_family}")
        else:
            best = max(
                (harmony(c, product_colour_family).score for c in preferred_colours),
                default=NEUTRAL_PREFERENCE,
            )
            signals.append(best)
            details.append(
                f"{product_colour_family} works with the requested "
                f"{'/'.join(preferred_colours)}")

    canonical_style = normalise_style(style)
    if canonical_style:
        profile = STYLE_PROFILES[canonical_style]
        # Style is expressed through colour and finish; a product whose colour
        # is packaging or a skin match cannot express it, so only finish counts.
        if product_colour_role == "style":
            colour_fit = profile.colours.get(product_colour_family, NEUTRAL_PREFERENCE)
        else:
            colour_fit = NEUTRAL_PREFERENCE
        finish_fit = profile.finishes.get(finish, NEUTRAL_PREFERENCE) if finish else None

        style_signal = colour_fit if finish_fit is None else 0.7 * colour_fit + 0.3 * finish_fit
        if profile.prefers_metallic is True and is_metallic:
            style_signal = min(1.0, style_signal + 0.05)
        signals.append(style_signal)
        details.append(f"suits a {canonical_style} brief - {profile.description}")

    if not signals:
        return None
    raw = sum(signals) / len(signals)
    return ScoreComponent("preference_match", raw, weight, "; ".join(details))


def text_component(relevance: Relevance, weight: float) -> ScoreComponent | None:
    if relevance.score <= 0.0 and not relevance.matched_terms:
        return None
    return ScoreComponent("text_relevance", relevance.score, weight, relevance.explanation)


# --------------------------------------------------------------------------
# Combination
# --------------------------------------------------------------------------


def combine(components: list[ScoreComponent]) -> float:
    """Weighted mean over active components only."""
    active = [c for c in components if c is not None]
    total_weight = sum(c.weight for c in active)
    if total_weight == 0:
        return 0.0
    return sum(c.contribution for c in active) / total_weight


# --------------------------------------------------------------------------
# Scoring the product the shopper actually asked for
# --------------------------------------------------------------------------

# A complement is scored on how well it goes *with* an anchor. The requested
# garment has no anchor to go with - it IS the anchor - so the same weights
# answer the wrong question and produce numbers that are not comparable. These
# weights score the only question that matters for a search result: how closely
# does this product match what was asked for?
# Two colour families this close on the wheel read as the same colour to a
# shopper - red and pink at 16 degrees, red and orange at 35. Beyond that a
# request for red is simply not being met.
NEAR_COLOUR_DEGREES = 30.0

REQUEST_WEIGHTS = {
    "category_match": 0.34,
    "colour_match": 0.26,
    "occasion_suitability": 0.22,
    "style_match": 0.10,
    "text_relevance": 0.08,
}


def category_match_component(
    requested_type: str | None,
    requested_group: str | None,
    product_type: str,
    category_group: str,
) -> ScoreComponent | None:
    """How exactly the product is the kind of thing that was asked for."""
    if requested_type:
        if product_type.lower() == requested_type.lower():
            return ScoreComponent("category_match", 1.0,
                                  REQUEST_WEIGHTS["category_match"],
                                  f"is exactly what you asked for: {product_type.lower()}")
        if requested_group and category_group == requested_group:
            return ScoreComponent("category_match", 0.75,
                                  REQUEST_WEIGHTS["category_match"],
                                  f"is {category_group.replace('_', ' ')}, close to the "
                                  f"{requested_type.lower()} you asked for")
        return ScoreComponent("category_match", 0.4,
                              REQUEST_WEIGHTS["category_match"],
                              f"is a {product_type.lower()} rather than the "
                              f"{requested_type.lower()} you asked for")
    if requested_group:
        exact = category_group == requested_group
        return ScoreComponent(
            "category_match", 1.0 if exact else 0.5,
            REQUEST_WEIGHTS["category_match"],
            f"is {category_group.replace('_', ' ')}, which is what you asked for"
            if exact else f"is {category_group.replace('_', ' ')}")
    return None


def colour_match_component(
    requested_colour: str | None,
    product_colour_family: str,
) -> ScoreComponent | None:
    """Whether the product is the colour asked for, or merely near it.

    A requested colour is a requirement, not a harmony problem: someone asking
    for a red shirt wants red, and a compatible navy is a fallback, not a match.
    """
    if not requested_colour:
        return None
    weight = REQUEST_WEIGHTS["colour_match"]
    if product_colour_family == requested_colour:
        return ScoreComponent("colour_match", 1.0, weight,
                              f"is {product_colour_family}, the colour you asked for")
    distance = hue_distance(requested_colour, product_colour_family)
    if distance is not None and distance <= NEAR_COLOUR_DEGREES:
        return ScoreComponent("colour_match", 0.6, weight,
                              f"{product_colour_family} is a close shade of "
                              f"{requested_colour}")
    return ScoreComponent("colour_match", 0.2, weight,
                          f"is {product_colour_family}, not the {requested_colour} "
                          f"you asked for")


def request_match(
    requested_type: str | None,
    requested_group: str | None,
    requested_colour: str | None,
    requested_occasion: str | None,
    requested_style: str | None,
    product_type: str,
    category_group: str,
    product_occasion: str,
    colour_family: str,
    colour_role: str,
    is_metallic: bool,
    finish: str | None,
    relevance: Relevance | None = None,
) -> tuple[float, tuple[ScoreComponent, ...]]:
    """Score a product against the request, in the order the request implies.

    Category first, then colour, then occasion, then style, then text. Gender is
    not scored because it is a hard filter - a product of the wrong gender is
    never a candidate at all.
    """
    components = [
        category_match_component(requested_type, requested_group,
                                 product_type, category_group),
        colour_match_component(requested_colour, colour_family),
        occasion_component("apparel", requested_occasion, product_occasion,
                           category_group, colour_family, colour_role, finish,
                           REQUEST_WEIGHTS["occasion_suitability"]),
    ]
    canonical_style = normalise_style(requested_style)
    if canonical_style:
        profile = STYLE_PROFILES[canonical_style]
        fit = profile.colours.get(colour_family, NEUTRAL_PREFERENCE)
        if finish:
            fit = 0.7 * fit + 0.3 * profile.finishes.get(finish, NEUTRAL_PREFERENCE)
        components.append(ScoreComponent(
            "style_match", fit, REQUEST_WEIGHTS["style_match"],
            f"suits a {canonical_style} brief - {profile.description}"))
    if relevance is not None:
        components.append(text_component(relevance, REQUEST_WEIGHTS["text_relevance"]))

    active = tuple(c for c in components if c is not None)
    return combine(list(active)), active
