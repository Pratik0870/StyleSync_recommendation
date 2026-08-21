"""Colour harmony over the 15 normalised colour families.

Deterministic and explainable: every pairing returns a score, a named relation,
and a sentence saying why. Nothing is learned, nothing is random.

The hue angles are *computed* from the representative hex codes in
`src.catalog.taxonomy`, not typed in by hand, so the colour model stays tied to
the same values the catalog was built with.

Design note - why this is not simply "match the same colour":

    A complement is not a duplicate. Recommending a black lipstick for a black
    saree is a correct *similarity* answer and a useless *complementary* one.
    The rules below deliberately reward an accent on a neutral base and a
    grounding neutral on a saturated base, which is what coordinating a look
    actually means.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

from ..catalog.taxonomy import COLOUR_MAP

# --------------------------------------------------------------------------
# Family properties, derived from the catalog's own representative hexes
# --------------------------------------------------------------------------

NEUTRAL_FAMILIES = {"black", "white", "grey", "beige"}
METALLIC_FAMILIES = {"gold", "silver"}
UNRESOLVED_FAMILIES = {"multi"}

# Hues below this saturation carry no reliable hue signal (black/white/grey).
_MIN_SATURATION = 0.10


def _canonical_hex() -> dict[str, str]:
    """One representative hex per family.

    Prefer the source colour whose own name *is* the family name ("Grey" ->
    #808080). Taking simply the first mapped colour would hand `grey` the hex of
    "Charcoal" (#36454F), which is blue-tinted and would give the grey family a
    spurious 204deg hue.
    """
    out: dict[str, str] = {}
    for raw, (family, hex_code, _, _) in COLOUR_MAP.items():
        if hex_code and raw.strip().lower() == family:
            out[family] = hex_code
    for _, (family, hex_code, _, _) in COLOUR_MAP.items():
        if hex_code and family not in out:
            out[family] = hex_code
    return out


CANONICAL_HEX = _canonical_hex()


def _hue_of(hex_code: str) -> float | None:
    r, g, b = (int(hex_code[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < _MIN_SATURATION:
        return None
    return h * 360.0


FAMILY_HUE: dict[str, float | None] = {
    family: _hue_of(hex_code) for family, hex_code in CANONICAL_HEX.items()
}
FAMILY_HUE["multi"] = None

# Warm hues sit either side of red/orange/yellow; cool covers green/blue/purple.
WARM_ARC = (300.0, 90.0)      # wraps through 0


def is_warm(family: str) -> bool | None:
    hue = FAMILY_HUE.get(family)
    if hue is None:
        return None
    lo, hi = WARM_ARC
    return hue >= lo or hue <= hi


def hue_distance(a: str, b: str) -> float | None:
    """Smallest angular distance between two families, in degrees."""
    ha, hb = FAMILY_HUE.get(a), FAMILY_HUE.get(b)
    if ha is None or hb is None:
        return None
    diff = abs(ha - hb) % 360.0
    return min(diff, 360.0 - diff)


def family_class(family: str) -> str:
    if family in UNRESOLVED_FAMILIES:
        return "unresolved"
    if family in METALLIC_FAMILIES:
        return "metallic"
    if family in NEUTRAL_FAMILIES:
        return "neutral"
    return "chromatic"


# --------------------------------------------------------------------------
# Harmony
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Harmony:
    score: float          # 0..1
    relation: str         # named relation, for explanations and tests
    explanation: str


# Tunable, documented, and all in one place.
HARMONY_SCORES = {
    "metallic_on_neutral":   0.95,
    "metallic_tone_match":   0.92,   # gold with warm, silver with cool
    "accent_on_neutral":     0.90,   # saturated complement, neutral anchor
    "neutral_grounding":     0.85,   # neutral complement, saturated anchor
    "metallic_tone_clash":   0.78,   # gold with cool, silver with warm
    "analogous":             0.80,
    "complementary":         0.75,
    "same_family":           0.68,   # tonal; correct but can read flat
    "near_analogous":        0.66,   # 45-90deg; neither harmonious nor striking
    "neutral_on_neutral":    0.62,   # safe, low interest
    "triadic":               0.60,
    "unresolved":            0.50,   # "Multi" - no single hue to reason about
}

# Hue bands, in degrees of separation.
#
# Deliberately absent: a "clash" verdict. Fifteen coarse families carry hue but
# not saturation or lightness, and discord is mostly a saturation/value effect -
# a pale sage and a neon lime share a hue family and behave completely
# differently. Claiming to detect a clash at this granularity would be false
# precision, so the model expresses a *preference ordering* (0.50-0.95) rather
# than a pass/fail judgement. This is stated as a limitation, not hidden.
ANALOGOUS_MAX = 45.0
NEAR_ANALOGOUS_MAX = 90.0
TRIADIC_MAX = 150.0


def harmony(anchor_family: str, complement_family: str) -> Harmony:
    """Score how well a complement colour works against an anchor colour."""
    a_class = family_class(anchor_family)
    c_class = family_class(complement_family)

    if "unresolved" in (a_class, c_class):
        return Harmony(
            HARMONY_SCORES["unresolved"], "unresolved",
            "one of the colours is multi-coloured, so no single hue relationship "
            "can be established",
        )

    # Metallics act as accents rather than hues.
    if c_class == "metallic":
        if a_class == "neutral":
            return Harmony(
                HARMONY_SCORES["metallic_on_neutral"], "metallic_on_neutral",
                f"{complement_family} metallic lifts a {anchor_family} base",
            )
        warm_anchor = is_warm(anchor_family)
        warm_metal = complement_family == "gold"
        if warm_anchor is None or warm_anchor == warm_metal:
            return Harmony(
                HARMONY_SCORES["metallic_tone_match"], "metallic_tone_match",
                f"{complement_family} suits the "
                f"{'warm' if warm_metal else 'cool'} tone of {anchor_family}",
            )
        return Harmony(
            HARMONY_SCORES["metallic_tone_clash"], "metallic_tone_clash",
            f"{complement_family} runs {'warm' if warm_metal else 'cool'} against a "
            f"{'warm' if warm_anchor else 'cool'} {anchor_family}",
        )

    if a_class == "metallic":
        # A metallic anchor behaves like a neutral for the complement's purposes.
        if c_class == "neutral":
            return Harmony(
                HARMONY_SCORES["neutral_grounding"], "neutral_grounding",
                f"{complement_family} grounds a {anchor_family} anchor",
            )
        return Harmony(
            HARMONY_SCORES["accent_on_neutral"], "accent_on_neutral",
            f"{complement_family} reads as an accent against {anchor_family}",
        )

    if a_class == "neutral" and c_class == "neutral":
        return Harmony(
            HARMONY_SCORES["neutral_on_neutral"], "neutral_on_neutral",
            f"{complement_family} with {anchor_family} is safe but low-contrast",
        )

    if a_class == "neutral":
        return Harmony(
            HARMONY_SCORES["accent_on_neutral"], "accent_on_neutral",
            f"{complement_family} gives a {anchor_family} base a colour accent",
        )

    if c_class == "neutral":
        return Harmony(
            HARMONY_SCORES["neutral_grounding"], "neutral_grounding",
            f"{complement_family} grounds a saturated {anchor_family} look",
        )

    # Both chromatic - fall through to hue geometry.
    if anchor_family == complement_family:
        return Harmony(
            HARMONY_SCORES["same_family"], "same_family",
            f"tonal match with {anchor_family}",
        )

    distance = hue_distance(anchor_family, complement_family)
    if distance is None:
        return Harmony(
            HARMONY_SCORES["unresolved"], "unresolved",
            "no hue information available for one of the colours",
        )

    if distance <= ANALOGOUS_MAX:
        return Harmony(
            HARMONY_SCORES["analogous"], "analogous",
            f"{complement_family} sits close to {anchor_family} on the colour "
            f"wheel ({distance:.0f}deg apart)",
        )
    if distance > TRIADIC_MAX:
        return Harmony(
            HARMONY_SCORES["complementary"], "complementary",
            f"{complement_family} is opposite {anchor_family} on the colour "
            f"wheel ({distance:.0f}deg apart), a high-contrast pairing",
        )
    if distance <= NEAR_ANALOGOUS_MAX:
        return Harmony(
            HARMONY_SCORES["near_analogous"], "near_analogous",
            f"{complement_family} is a near neighbour of {anchor_family} "
            f"({distance:.0f}deg apart)",
        )
    return Harmony(
        HARMONY_SCORES["triadic"], "triadic",
        f"{complement_family} and {anchor_family} sit a third of the wheel "
        f"apart ({distance:.0f}deg)",
    )


def harmony_table() -> dict[str, dict[str, Harmony]]:
    """Full precomputed 15x15 matrix - used by docs and tests."""
    families = sorted(FAMILY_HUE)
    return {a: {b: harmony(a, b) for b in families} for a in families}
