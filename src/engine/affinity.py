"""Category affinity: which complement categories are worth considering at all.

Rather than hand-writing a flat anchor x complement matrix (6 anchor groups x 17
complement groups = 102 opaque numbers), affinity is *composed* from three
factors, each of which can be stated in a sentence:

    affinity = base_relevance x occasion_fit x anchor_fit

    base_relevance   how universally this category completes a look at all
                     (footwear is near-mandatory; a wallet rarely matters)
    occasion_fit     how much the occasion calls for it
                     (jewellery matters far more at a wedding than at the gym)
    anchor_fit       how well it pairs with this kind of anchor garment
                     (heels with a saree, trainers with joggers)

Every factor is a configurable constant with a documented rationale, so the
engine can always answer "why was this category considered?" with the actual
arithmetic rather than a post-hoc story.

These are editorial priors, not learned weights - the Phase 1 catalog has no
interaction data to learn from. They are declared as priors and can be replaced
with mined affinities if behavioural data is ever added.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Factor 1 - base relevance
# --------------------------------------------------------------------------
# "If someone is putting a look together, how often does this category come into
# it at all?" Independent of occasion and of the garment.

BASE_RELEVANCE: dict[str, tuple[float, str]] = {
    "footwear_dress":  (0.95, "footwear is part of essentially every look"),
    "footwear_flat":   (0.95, "footwear is part of essentially every look"),
    "footwear_formal": (0.95, "footwear is part of essentially every look"),
    "footwear_casual": (0.95, "footwear is part of essentially every look"),
    "bag":             (0.85, "a bag is carried with most going-out looks"),
    "jewellery":       (0.80, "jewellery is the primary way a look is dressed up"),
    "beauty_lip":      (0.80, "lip colour is the most visible makeup decision"),
    "beauty_eye":      (0.70, "eye makeup is a core part of a finished look"),
    "beauty_face":     (0.55, "base makeup matters but is chosen by skin, not outfit"),
    "beauty_nails":    (0.50, "nails are a supporting detail"),
    "neckwear":        (0.50, "scarves and dupattas are occasional additions"),
    "fragrance":       (0.45, "fragrance completes a look but is outfit-independent"),
    "watch":           (0.45, "a watch is habitual rather than look-driven"),
    "eyewear":         (0.35, "sunglasses depend on setting more than on outfit"),
    "belt":            (0.30, "a belt is usually functional"),
    "headwear":        (0.20, "headwear is situational"),
    "wallet":          (0.15, "a wallet is rarely a styling decision"),
    # Clothing. These groups are anchors in the Phase 1 taxonomy, so they never
    # appear as complements in the normal path and these entries have no effect
    # there. They matter only to the outfit composer, which asks the engine for
    # clothing through a catalog view - without them a garment the shopper
    # explicitly asked for scores 0.25 ("no declared styling role") and is
    # dropped by the acceptance floor.
    "ethnic_wear":     (0.95, "the garment is the look"),
    "dress":           (0.95, "the garment is the look"),
    "topwear":         (0.92, "the garment is the look"),
    "apparel_set":     (0.90, "a coordinated set is the look"),
    "bottomwear":      (0.85, "bottoms complete the garment"),
    "outerwear":       (0.70, "outerwear layers over the look"),
}

# --------------------------------------------------------------------------
# Factor 2 - occasion fit
# --------------------------------------------------------------------------
# Multipliers applied when the user names an occasion. Unlisted combinations
# default to 1.0 (no opinion).

OCCASION_FIT: dict[str, dict[str, float]] = {
    "wedding": {
        "jewellery": 1.20, "beauty_lip": 1.20, "beauty_eye": 1.15,
        "beauty_face": 1.10, "beauty_nails": 1.10, "footwear_dress": 1.15,
        "bag": 1.05, "fragrance": 1.10,
        "watch": 0.50, "eyewear": 0.30, "belt": 0.40, "wallet": 0.30,
        "headwear": 0.40, "footwear_casual": 0.35, "footwear_flat": 0.70,
        "footwear_formal": 0.45,
    },
    "festive": {
        "jewellery": 1.20, "beauty_lip": 1.15, "beauty_eye": 1.10,
        "beauty_nails": 1.10, "footwear_dress": 1.10, "neckwear": 1.10,
        "watch": 0.60, "eyewear": 0.40, "wallet": 0.40, "footwear_casual": 0.50,
        "footwear_formal": 0.50,
    },
    "party": {
        "beauty_lip": 1.20, "beauty_eye": 1.20, "beauty_nails": 1.15,
        "jewellery": 1.10, "footwear_dress": 1.20, "bag": 1.10,
        "fragrance": 1.10,
        "watch": 0.60, "eyewear": 0.40, "belt": 0.50, "wallet": 0.40,
        "footwear_casual": 0.40, "headwear": 0.40, "footwear_formal": 0.55,
    },
    "formal": {
        "watch": 1.20, "belt": 1.10, "footwear_formal": 1.25, "bag": 1.05,
        "beauty_face": 1.05,
        "beauty_nails": 0.70, "beauty_eye": 0.85, "headwear": 0.30,
        "footwear_casual": 0.50, "footwear_dress": 0.90,
    },
    "casual": {
        "eyewear": 1.15, "watch": 1.10, "footwear_casual": 1.25,
        "footwear_flat": 1.10, "bag": 1.00,
        "jewellery": 0.70, "beauty_eye": 0.75, "beauty_nails": 0.80,
        "footwear_dress": 0.55, "fragrance": 0.85,
    },
    "office": {
        "watch": 1.20, "belt": 1.10, "footwear_formal": 1.20, "bag": 1.10,
        "beauty_lip": 0.90, "beauty_eye": 0.80, "beauty_nails": 0.70,
        "jewellery": 0.80, "headwear": 0.20, "footwear_casual": 0.60,
    },
    "sports": {
        "footwear_casual": 1.20, "eyewear": 1.10, "watch": 1.10,
        "jewellery": 0.20, "beauty_lip": 0.25, "beauty_eye": 0.20,
        "beauty_nails": 0.30, "beauty_face": 0.30, "footwear_dress": 0.10,
        "bag": 0.60, "neckwear": 0.30,
    },
}

# --------------------------------------------------------------------------
# Factor 3 - anchor fit
# --------------------------------------------------------------------------
# How well a complement category pairs with the *kind of garment* the user has.

ANCHOR_FIT: dict[str, dict[str, float]] = {
    "ethnic_wear": {
        "jewellery": 1.20, "beauty_lip": 1.10, "neckwear": 1.15,
        "footwear_flat": 1.10, "footwear_dress": 1.05, "bag": 1.00,
        "belt": 0.25, "watch": 0.70, "footwear_sports": 0.10,
        "footwear_casual": 0.40, "eyewear": 0.60, "footwear_formal": 0.30,
    },
    "dress": {
        "jewellery": 1.10, "footwear_dress": 1.15, "bag": 1.10,
        "beauty_lip": 1.05, "belt": 0.80, "neckwear": 0.70,
        "footwear_casual": 0.60,
    },
    "topwear": {
        "footwear_casual": 1.10, "watch": 1.05, "eyewear": 1.05,
        "bag": 0.95, "jewellery": 0.90, "neckwear": 0.85,
    },
    "bottomwear": {
        "belt": 1.30, "footwear_casual": 1.10, "footwear_formal": 1.05,
        "watch": 1.00, "jewellery": 0.80, "neckwear": 0.60,
    },
    "outerwear": {
        "neckwear": 1.20, "headwear": 1.15, "footwear_formal": 1.05,
        "belt": 0.70, "beauty_nails": 0.80,
    },
    "apparel_set": {
        "footwear_casual": 1.10, "watch": 1.00, "jewellery": 0.85,
    },
}

# --------------------------------------------------------------------------
# Product-type refinement
# --------------------------------------------------------------------------
# A category group is sometimes coarser than the styling decision. `fragrance`
# contains both perfume (a styling choice) and deodorant (a commodity nobody
# picks to match a saree); `beauty_face` contains blush (a styling choice) and
# concealer (bought to match skin). Without this, a request for an elegant
# wedding look surfaces "Reebok Women Reeshine Deo" purely because nothing in
# the category could be colour-matched.

PRODUCT_TYPE_RELEVANCE: dict[str, tuple[float, str]] = {
    "Deodorant":              (0.40, "a deodorant is a commodity, not a styling choice"),
    "Perfume and Body Mist":  (1.00, "perfume is chosen to finish a look"),
    "Fragrance Gift Set":     (0.80, "a fragrance set suits an occasion"),
    "Concealer":              (0.55, "concealer is chosen to match skin, not an outfit"),
    "Foundation and Primer":  (0.55, "foundation is chosen to match skin, not an outfit"),
    "Compact":                (0.60, "compact powder is chosen to match skin"),
    "Highlighter and Blush":  (1.00, "blush and highlighter are styling decisions"),
    "Lip Care":               (0.45, "lip balm is functional rather than a colour choice"),
    "Nail Essentials":        (0.40, "nail care is functional"),
    "Eye Cream":              (0.30, "eye cream is skincare, not a look decision"),
    "Socks":                  (0.30, "socks are rarely a styling decision"),
    "Stockings":              (0.45, "hosiery is occasionally a styling decision"),
    # `bag` spans evening clutches and laptop cases. Without this a
    # "Belkin Unisex Black Dash Laptop 16 Toploader" scores as a party bag.
    "Clutches":               (1.00, "a clutch is an occasion bag"),
    "Handbags":               (0.95, "a handbag suits most looks"),
    "Laptop Bag":             (0.20, "a laptop bag is work equipment, not a look"),
    "Tablet Sleeve":          (0.15, "a tablet sleeve is not a styling choice"),
    "Trolley Bag":            (0.15, "luggage is not part of a look"),
    "Duffel Bag":             (0.25, "a duffel is gym or travel kit"),
    "Rucksacks":              (0.25, "a rucksack is travel kit"),
    "Backpacks":              (0.35, "a backpack is casual utility"),
    "Messenger Bag":          (0.35, "a messenger bag is work utility"),
    "Waist Pouch":            (0.20, "a waist pouch is utility"),
    "Mobile Pouch":           (0.20, "a phone pouch is utility"),
}


def product_type_relevance(product_type: str) -> tuple[float, str | None]:
    return PRODUCT_TYPE_RELEVANCE.get(product_type, (1.0, None))


MIN_AFFINITY = 0.15   # below this a category is not worth showing at all


@dataclass(frozen=True)
class Affinity:
    category_group: str
    score: float
    base: float
    occasion_multiplier: float
    anchor_multiplier: float
    rationale: str

    @property
    def explanation(self) -> str:
        parts = [f"{self.rationale} (base {self.base:.2f}"]
        if self.occasion_multiplier != 1.0:
            parts.append(f"x{self.occasion_multiplier:.2f} for the occasion")
        if self.anchor_multiplier != 1.0:
            parts.append(f"x{self.anchor_multiplier:.2f} for this anchor")
        return ", ".join(parts) + f") = {self.score:.2f}"


def affinity_for(
    complement_group: str,
    anchor_group: str | None,
    occasion: str | None,
) -> Affinity:
    """Compose the affinity of one complement category."""
    base, rationale = BASE_RELEVANCE.get(
        complement_group, (0.25, "category has no declared styling role"))
    occasion_mult = OCCASION_FIT.get(occasion or "", {}).get(complement_group, 1.0)
    anchor_mult = ANCHOR_FIT.get(anchor_group or "", {}).get(complement_group, 1.0)
    score = min(1.0, base * occasion_mult * anchor_mult)
    return Affinity(complement_group, score, base, occasion_mult, anchor_mult, rationale)


def ranked_categories(
    anchor_group: str | None,
    occasion: str | None,
    available_groups: set[str],
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> list[Affinity]:
    """All complement categories worth considering, best affinity first."""
    groups = set(available_groups)
    if include:
        groups &= set(include)
    groups -= set(exclude)
    scored = [affinity_for(g, anchor_group, occasion) for g in sorted(groups)]

    # MIN_AFFINITY is a default-relevance floor, not a veto over the user. If a
    # category was explicitly asked for, it is returned however low its affinity
    # is - the honest response to "show me headwear for a wedding" is a weak
    # selection with the weakness reported, not a silent refusal.
    if not include:
        scored = [a for a in scored if a.score >= MIN_AFFINITY]

    return sorted(scored, key=lambda a: (-a.score, a.category_group))


def known_occasions() -> set[str]:
    return set(OCCASION_FIT)
