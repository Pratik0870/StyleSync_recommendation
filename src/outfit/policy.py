"""Which categories belong in an outfit, and in what order.

This is a *composition policy*, not a recommender. It decides which category
types to ask the Phase 2 engine for. The engine still finds, scores, ranks and
diversifies the actual products — nothing here selects a product.

Every category named below exists in the Phase 1 catalog. Nothing is invented:
if a section has no qualifying products the composer reports it as thin or drops
it rather than filling it with something irrelevant.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    """One part of an outfit."""

    key: str
    title: str
    groups: tuple[str, ...]          # Phase 1 category_group values
    # Optional product_type restriction. `ethnic_wear` holds both tops and
    # churidars, so "Main look" and "Bottoms" need to split it by product type
    # rather than by category group.
    product_types: tuple[str, ...] = ()
    limit: int = 4
    essential: bool = False          # a look is incomplete without it
    note: str | None = None
    # Clothing groups are anchors in the Phase 1 taxonomy, so the engine will
    # not return them as complements. The composer routes these through a
    # clothing view of the catalog instead. See composer.py.
    clothing: bool = False


# The ordering below is the order a person actually assembles a look: the main
# garment first, then what goes under/with it, then shoes, then the finishing
# pieces. Accessories come last deliberately - the original failure this fixes
# was accessories dominating a wedding request.

# Verified against the catalog: men's ethnic tops are Kurtas (78) and Nehru
# Jackets (5); the only men's ethnic bottom is Churidar (6), so trousers are
# offered alongside and the section reports its own thinness.
MEN_ETHNIC = (
    Section("main", "Main look", ("ethnic_wear",),
            product_types=("Kurtas", "Nehru Jackets", "Kurta Sets"),
            limit=4, essential=True, clothing=True),
    Section("bottoms", "Bottoms", ("ethnic_wear", "bottomwear"),
            product_types=("Churidar", "Patiala", "Salwar", "Trousers"),
            limit=3, clothing=True,
            note="The catalog holds few men's ethnic bottoms, so tailored "
                 "trousers are shown alongside churidars."),
    # `footwear_dress` is excluded for men: the source labels some men's shoes
    # "Heels", which is a data quirk that reads as an error to a shopper.
    # Neckwear is excluded too - the men's neckwear in this catalog is ties and
    # mufflers, and neither belongs with a kurta.
    # Flip flops and sports sandals are excluded from dressed-up looks: the
    # catalog has 644 men's flip flops, and without this they crowd out the
    # 636 formal shoes purely on colour score.
    Section("footwear", "Footwear", ("footwear_formal", "footwear_flat"),
            product_types=("Formal Shoes", "Sandals"),
            limit=3, essential=True),
    Section("accessories", "Complete the look", ("watch", "jewellery"), limit=3),
    Section("fragrance", "Fragrance", ("fragrance",), limit=2),
)

MEN_WESTERN = (
    Section("main", "Main look", ("topwear",),
            product_types=("Shirts", "Tshirts", "Sweaters", "Sweatshirts"),
            limit=4, essential=True, clothing=True),
    Section("bottoms", "Bottoms", ("bottomwear",),
            product_types=("Trousers", "Jeans", "Shorts"),
            limit=3, clothing=True),
    Section("footwear", "Footwear", ("footwear_formal", "footwear_casual"),
            product_types=("Formal Shoes", "Casual Shoes"),
            limit=3, essential=True),
    Section("accessories", "Complete the look", ("watch", "belt", "eyewear", "bag"), limit=3),
    Section("fragrance", "Fragrance", ("fragrance",), limit=2),
)

SPORTS = (
    Section("main", "Main look", ("topwear", "apparel_set"),
            product_types=("Tshirts", "Tops", "Sweatshirts", "Tracksuits"),
            limit=4, essential=True, clothing=True),
    Section("bottoms", "Bottoms", ("bottomwear",),
            product_types=("Shorts", "Track Pants", "Capris"),
            limit=3, clothing=True),
    Section("footwear", "Footwear", ("footwear_sports",),
            product_types=("Sports Shoes",),
            limit=3, essential=True),
    Section("kit", "Kit", ("accessory_other", "headwear", "bag", "watch"),
            product_types=("Socks", "Caps", "Backpacks", "Watches"),
            limit=3),
)


WOMEN_ETHNIC = (
    Section("main", "Main look", ("ethnic_wear",),
            product_types=("Sarees", "Kurtas", "Kurtis", "Kurta Sets",
                           "Lehenga Choli", "Tunics"),
            limit=4, essential=True, clothing=True),
    Section("bottoms", "Bottoms & drape", ("ethnic_wear", "bottomwear", "neckwear"),
            product_types=("Churidar", "Patiala", "Salwar", "Salwar and Dupatta",
                           "Leggings", "Dupatta", "Stoles"),
            limit=3, clothing=True),
    Section("footwear", "Footwear", ("footwear_dress", "footwear_flat"),
            product_types=("Heels", "Flats", "Sandals"),
            limit=3, essential=True),
    Section("jewellery", "Jewellery", ("jewellery",), limit=4, essential=True),
    Section("bag", "Bag", ("bag",), limit=2),
    Section("beauty", "Beauty", ("beauty_lip", "beauty_eye", "beauty_face", "beauty_nails"),
            limit=4),
)

WOMEN_WESTERN = (
    Section("main", "Main look", ("dress", "topwear"),
            product_types=("Dresses", "Jumpsuit", "Tops", "Shirts"),
            limit=4, essential=True, clothing=True),
    Section("bottoms", "Bottoms", ("bottomwear",),
            product_types=("Skirts", "Trousers", "Jeans", "Leggings", "Capris"),
            limit=3, clothing=True),
    Section("footwear", "Footwear", ("footwear_dress", "footwear_flat"),
            product_types=("Heels", "Flats", "Sandals", "Casual Shoes"),
            limit=3, essential=True),
    Section("jewellery", "Jewellery", ("jewellery",), limit=3),
    Section("bag", "Bag", ("bag",), limit=2),
    Section("beauty", "Beauty", ("beauty_lip", "beauty_eye", "beauty_face"), limit=3),
)

# Occasions where Indian ethnic wear is the natural reading of "an outfit".
ETHNIC_OCCASIONS = {"wedding", "festive"}


# Occasions where the clothing has to be dressed up, and the garment types that
# cannot be. The catalog's own `occasion` column is not enough on its own: it
# labels a novelty T-shirt "formal", so a look built purely from that column
# offers a T-shirt for a boardroom.
DRESSY_OCCASIONS = {"formal", "office", "wedding", "party"}
CASUAL_ONLY_TYPES = {"Tshirts", "Sweatshirts", "Shorts", "Jeans", "Capris",
                     "Track Pants", "Casual Shoes"}


def _dressed_up(sections: tuple[Section, ...]) -> tuple[Section, ...]:
    """Drop garment types that cannot carry a dressy occasion."""
    out = []
    for section in sections:
        types = tuple(t for t in section.product_types
                      if t not in CASUAL_ONLY_TYPES)
        # Never empty a section - if nothing survives, the catalog has only
        # casual options here and showing them is better than showing nothing.
        out.append(replace(section, product_types=types) if types else section)
    return tuple(out)


# Fragrance belongs to an occasion someone dresses up for. Adding it to every
# look meant the same two perfumes appeared under a gym kit and a work outfit
# alike, which made every search look identical.
FRAGRANCE_OCCASIONS = {"wedding", "festive", "party", "formal"}


def sections_for(gender: str | None, occasion: str | None,
                 anchor_group: str | None) -> tuple[Section, ...]:
    """The outfit shape for this request.

    `anchor_group` wins when the shopper named a garment: if they said kurta,
    the look is built around ethnic wear regardless of the occasion.
    """
    if occasion == "sports" and anchor_group is None:
        return SPORTS

    ethnic = (anchor_group == "ethnic_wear") or (
        anchor_group is None and occasion in ETHNIC_OCCASIONS)

    if gender == "men":
        shape = MEN_ETHNIC if ethnic else MEN_WESTERN
    elif gender == "women":
        shape = WOMEN_ETHNIC if ethnic else WOMEN_WESTERN
    else:
        # No gender stated. The caller is expected to ask before composing,
        # because mixing men's and women's clothing into one look is never right.
        shape = WOMEN_ETHNIC if ethnic else WOMEN_WESTERN

    if occasion not in FRAGRANCE_OCCASIONS:
        shape = tuple(sec for sec in shape if sec.key != "fragrance")

    return _dressed_up(shape) if occasion in DRESSY_OCCASIONS else shape


# A section reads better when it names the thing it holds. "Main look" is fine
# in the abstract; "Running Top" tells you what you are looking at.
SECTION_TITLES = {
    "sports": {"main": "Running Top", "bottoms": "Running Bottoms",
               "footwear": "Running Shoes", "kit": "Essentials"},
    "office": {"main": "Shirt", "bottoms": "Trousers",
               "footwear": "Formal Shoes", "accessories": "Finishing Touches"},
    "formal": {"main": "Shirt", "bottoms": "Trousers",
               "footwear": "Formal Shoes", "accessories": "Finishing Touches"},
    "casual": {"main": "Top", "bottoms": "Bottoms",
               "footwear": "Shoes", "accessories": "Accessories"},
}

DEFAULT_TITLES = {"main": "Main Piece", "bottoms": "Bottoms", "footwear": "Shoes",
                  "accessories": "Accessories", "kit": "Essentials"}


def title_for(section_key: str, occasion: str | None, default: str) -> str:
    """The heading for a section, given what the look is for."""
    by_occasion = SECTION_TITLES.get(occasion or "", {})
    return by_occasion.get(section_key) or DEFAULT_TITLES.get(section_key, default)


def requires_gender(intent_gender: str | None) -> bool:
    """An outfit needs a gender; a single product does not."""
    return intent_gender not in {"men", "women"}


# A garment can be gendered strongly enough that the catalog itself answers the
# question. This is read from the data, not assumed: only product types where
# one gender holds at least this share are treated as decided.
GENDER_DOMINANCE = 0.95


def infer_gender_from_garment(frame, product_type: str | None) -> str | None:
    """The gender a garment implies, when the catalog is near-unanimous.

    Sarees are 100% women's and ties 100% men's, so recommending a tie to
    someone in a saree is a defect rather than an open question. Shirts are only
    90% men's, so they stay ambiguous and nothing is inferred.
    """
    if not product_type:
        return None
    rows = frame[(frame.product_type == product_type) & (frame.age_group == "adult")]
    if len(rows) < 20:
        return None
    share = rows.gender.value_counts(normalize=True)
    top = share.index[0]
    if top in {"men", "women"} and share.iloc[0] >= GENDER_DOMINANCE:
        return top
    return None
