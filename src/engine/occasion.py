"""Occasion suitability.

Two completely separate paths, for a reason established in Phase 1:

    non-beauty   the catalog's `occasion` column is trustworthy (41,032 rows)
                 and is used directly through a documented compatibility map.

    beauty       the catalog's `occasion` column is NOT trustworthy - the source
                 labels 2,136 of 2,139 personal-care products "Casual"
                 regardless of what they are. Reading it would be a bug. Beauty
                 suitability is therefore *derived* from attributes that are
                 real: category, shade family, and finish.

Every beauty product in the catalog carries `occasion_reliable = 0`, and
`beauty_suitability()` never looks at the `occasion` column.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

CANONICAL_OCCASIONS = ("wedding", "festive", "party", "formal", "office", "casual", "sports")

_OCCASION_SYNONYMS: dict[str, str] = {
    "wedding": "wedding", "marriage": "wedding", "shaadi": "wedding",
    "reception": "wedding", "sangeet": "wedding", "mehendi": "wedding",
    "bridal": "wedding", "engagement": "wedding",
    "festive": "festive", "festival": "festive", "diwali": "festive",
    "puja": "festive", "pooja": "festive", "navratri": "festive",
    "eid": "festive", "onam": "festive", "traditional": "festive",
    "ethnic": "festive",
    "party": "party", "cocktail": "party", "clubbing": "party",
    "night out": "party", "nightout": "party", "birthday": "party",
    "celebration": "party", "evening": "party",
    # Evening social outings. The catalog has no "dinner" occasion, and
    # inventing one would mean inventing a formality band to go with it. These
    # map onto the nearest supported equivalent - the same one "evening"
    # already used. `party` spreads across party/formal/ethnic/smart-casual in
    # CATALOG_OCCASION_FIT, which is the right band for dinner out.
    "dinner": "party", "date night": "party", "date": "party",
    "drinks": "party", "reunion": "party",
    "formal": "formal", "business": "formal", "conference": "formal",
    "office": "office", "work": "office", "meeting": "office",
    "interview": "office", "presentation": "office",
    "casual": "casual", "daily": "casual", "everyday": "casual",
    "brunch": "casual", "outing": "casual", "college": "casual",
    "lunch": "casual", "shopping": "casual", "weekend": "casual",
    "sports": "sports", "sport": "sports", "gym": "sports", "workout": "sports",
    "running": "sports", "run": "sports", "athletic": "sports",
    "marathon": "sports", "jogging": "sports", "jog": "sports",
    "cycling": "sports", "yoga": "sports", "fitness": "sports", "trek": "sports",
    "hiking": "sports", "5k": "sports", "10k": "sports",
    # "sporty"/"active" describe the occasion, not a style - the style
    # vocabulary has no athletic entry and adding a fake one would let the
    # scorer pretend to a signal the catalog cannot express.
    "sporty": "sports", "active": "sports", "activewear": "sports",
    "training": "sports", "exercise": "sports",
}


def normalise_occasion(text: str | None) -> str | None:
    """Free text -> canonical occasion, or None if unrecognised."""
    if not text:
        return None
    lowered = text.strip().lower()
    if lowered in _OCCASION_SYNONYMS:
        return _OCCASION_SYNONYMS[lowered]
    for phrase, canonical in _OCCASION_SYNONYMS.items():
        if phrase in lowered:
            return canonical
    return None


# --------------------------------------------------------------------------
# Path 1 - non-beauty, from the reliable `occasion` column
# --------------------------------------------------------------------------
# Rows are the requested occasion; columns are the catalog's own labels.
# Values are how acceptable a product with that label is for that request.
#
# Note the catalog labels available: casual, ethnic, formal, sports,
# smart_casual, party, travel. "party" holds only 28 products and
# "smart_casual" 67, so a request for a party CANNOT be served by filtering to
# the literal label - the map below deliberately spreads across ethnic/formal,
# and the engine reports when it has done so.

CATALOG_OCCASION_FIT: dict[str, dict[str, float]] = {
    "wedding": {"ethnic": 1.00, "party": 0.90, "formal": 0.80,
                "smart_casual": 0.50, "casual": 0.30, "travel": 0.20, "sports": 0.05},
    "festive": {"ethnic": 1.00, "party": 0.90, "formal": 0.70,
                "smart_casual": 0.55, "casual": 0.40, "travel": 0.25, "sports": 0.05},
    "party":   {"party": 1.00, "formal": 0.78, "ethnic": 0.72,
                "smart_casual": 0.72, "casual": 0.45, "travel": 0.25, "sports": 0.05},
    "formal":  {"formal": 1.00, "smart_casual": 0.80, "party": 0.55,
                "ethnic": 0.45, "casual": 0.40, "travel": 0.30, "sports": 0.05},
    "office":  {"formal": 1.00, "smart_casual": 0.85, "casual": 0.55,
                "party": 0.35, "ethnic": 0.40, "travel": 0.35, "sports": 0.10},
    "casual":  {"casual": 1.00, "smart_casual": 0.90, "travel": 0.75,
                "sports": 0.50, "ethnic": 0.45, "formal": 0.45, "party": 0.45},
    "sports":  {"sports": 1.00, "casual": 0.70, "travel": 0.50,
                "smart_casual": 0.35, "formal": 0.10, "ethnic": 0.10, "party": 0.10},
}

# Catalog labels that are too sparse to be filtered on directly.
SPARSE_CATALOG_OCCASIONS = {"party": 28, "smart_casual": 67, "travel": 26}


# --------------------------------------------------------------------------
# Path 2 - beauty, derived (never read from the source column)
# --------------------------------------------------------------------------
# Two axes, both grounded in attributes Phase 1 verified as reliable:
#
#   shade intensity   how much presence a colour family has as makeup.
#                     Only consulted when colour_role == "style" - a foundation
#                     shade (skin_match) or a bottle colour (packaging) says
#                     nothing about how dressy the product is.
#   finish dressiness parsed from the product name; shimmer and metallic read
#                     as evening, gloss and satin as daytime.
#
# Suitability then falls off with the distance between the product's derived
# "dressiness" and the occasion's.

OCCASION_DRESSINESS: dict[str, float] = {
    "wedding": 1.00, "festive": 0.90, "party": 0.88,
    "formal": 0.62, "office": 0.50, "casual": 0.30, "sports": 0.10,
}

SHADE_INTENSITY: dict[str, float] = {
    "red": 0.95, "purple": 0.85, "black": 0.85, "brown": 0.80,
    "gold": 0.90, "silver": 0.78, "blue": 0.70, "green": 0.70,
    "yellow": 0.60, "multi": 0.60, "orange": 0.55, "pink": 0.50,
    "grey": 0.50, "beige": 0.25, "white": 0.22,
}

FINISH_DRESSINESS: dict[str | None, float] = {
    "metallic": 0.95, "shimmer": 0.90, "matte": 0.70,
    "satin": 0.60, "gloss": 0.52, None: 0.60,
}

# How much of the derived dressiness comes from shade vs finish.
SHADE_WEIGHT, FINISH_WEIGHT = 0.65, 0.35

# Penalty per unit of mismatch between product dressiness and occasion dressiness.
MISMATCH_PENALTY = 0.75

# Categories whose relevance is not shade-driven at all.
_SHADE_BLIND_ROLES = {"skin_match", "packaging"}


@dataclass(frozen=True)
class Suitability:
    score: float
    basis: str            # "catalog_occasion" | "derived_from_attributes"
    explanation: str


def catalog_suitability(product_occasion: str, requested: str) -> Suitability:
    """Non-beauty path: read the trustworthy occasion column."""
    table = CATALOG_OCCASION_FIT.get(requested)
    if table is None:
        return Suitability(0.6, "catalog_occasion",
                           f"'{requested}' is not a recognised occasion, so occasion "
                           "was not used to rank this item")
    score = table.get(product_occasion, 0.35)
    return Suitability(
        score, "catalog_occasion",
        f"catalogued as {product_occasion} wear, which suits a {requested} "
        f"({score:.2f})",
    )


def beauty_suitability(
    category_group: str,
    colour_family: str,
    colour_role: str,
    finish: str | None,
    requested: str,
) -> Suitability:
    """Beauty path: derive suitability, never read the source occasion column."""
    dressiness = OCCASION_DRESSINESS.get(requested)
    if dressiness is None:
        return Suitability(0.6, "derived_from_attributes",
                           f"'{requested}' is not a recognised occasion, so occasion "
                           "was not used to rank this item")

    finish_value = FINISH_DRESSINESS.get(finish, FINISH_DRESSINESS[None])

    if colour_role in _SHADE_BLIND_ROLES:
        product_dressiness = finish_value
        basis_text = (
            f"shade is not a styling signal for this product "
            f"({colour_role}), so suitability comes from its "
            f"{finish or 'unstated'} finish"
        )
    else:
        shade_value = SHADE_INTENSITY.get(colour_family, 0.5)
        product_dressiness = SHADE_WEIGHT * shade_value + FINISH_WEIGHT * finish_value
        basis_text = (
            f"{colour_family} shade"
            + (f" with a {finish} finish" if finish else "")
            + f" reads as {_describe(product_dressiness)}"
        )

    score = max(0.0, 1.0 - MISMATCH_PENALTY * abs(product_dressiness - dressiness))
    return Suitability(
        score, "derived_from_attributes",
        f"{basis_text}, which suits a {requested} ({score:.2f}); "
        "derived from product attributes because the source occasion label is "
        "unreliable for beauty products",
    )


def _describe(dressiness: float) -> str:
    if dressiness >= 0.80:
        return "an evening/occasion look"
    if dressiness >= 0.60:
        return "a dressed-up look"
    if dressiness >= 0.40:
        return "an everyday look"
    return "a soft daytime look"
