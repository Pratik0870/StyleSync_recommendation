"""Pure normalisation functions over the raw Myntra catalog rows.

No I/O, no scoring, no ranking. Every function here is a deterministic mapping
from raw source values to the normalised catalog schema, so the whole thing is
unit-testable without touching the dataset.
"""

from __future__ import annotations

import re
from collections import Counter

from .taxonomy import (
    ANCHOR_GROUPS,
    CATEGORY_GROUP_MAP,
    COLOUR_MAP,
    COMPLEMENT_GROUPS,
    DOMAIN_MAP,
    GENDER_MAP,
    OCCASION_MAP,
    colour_role,
)

# --------------------------------------------------------------------------
# Attribute normalisation
# --------------------------------------------------------------------------


def normalise_colour(base_colour: str) -> dict:
    """Raw baseColour -> family, representative hex, and colour flags."""
    family, hex_code, is_neutral, is_metallic = COLOUR_MAP[base_colour]
    return {
        "colour_family": family,
        "colour_hex": hex_code,
        "is_neutral": is_neutral,
        "is_metallic": is_metallic,
    }


def normalise_domain(master_category: str) -> str:
    return DOMAIN_MAP[master_category]


def normalise_category_group(article_type: str) -> str:
    return CATEGORY_GROUP_MAP[article_type]


def normalise_occasion(usage: str, domain: str) -> tuple[str, bool]:
    """Return (occasion, occasion_is_reliable).

    `usage` is trustworthy for apparel/accessories/footwear. It is NOT
    trustworthy for beauty: the source labels virtually every personal-care
    product "Casual" irrespective of what it is, so we carry the value but mark
    it unreliable rather than pretending otherwise.
    """
    return OCCASION_MAP[usage], domain != "beauty"


def normalise_audience(gender: str) -> tuple[str, str]:
    return GENDER_MAP[gender]


# --------------------------------------------------------------------------
# Product finish (parsed from the product name)
# --------------------------------------------------------------------------
# Only applied to colour cosmetics, where the finish word is a genuine product
# attribute that Myntra puts in the title (e.g. "Lakme Absolute Matte Merlot").

_FINISH_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("matte",     re.compile(r"\bmatte?\b", re.I)),
    ("shimmer",   re.compile(r"\b(shimmer|glitter|sparkl\w*)\b", re.I)),
    ("metallic",  re.compile(r"\b(metallic|chrome|foil)\b", re.I)),
    ("satin",     re.compile(r"\b(satin|silk|creme|cream[yv]?)\b", re.I)),
    ("gloss",     re.compile(r"\b(gloss\w*|shine|shiny|dewy|lacquer)\b", re.I)),
]


def parse_finish(product_name: str, category_group: str) -> str | None:
    """Extract a finish keyword from the product name, or None."""
    if not category_group.startswith("beauty_"):
        return None
    for finish, pattern in _FINISH_PATTERNS:
        if pattern.search(product_name):
            return finish
    return None


# --------------------------------------------------------------------------
# Brand extraction
# --------------------------------------------------------------------------
# The dataset has no brand column; the brand is the leading token(s) of
# productDisplayName ("Lakme Absolute Matte Merlot Lipstick 45"). Rather than
# guess, we derive a lexicon from the corpus itself and then apply it.

_TOKEN_RE = re.compile(r"[A-Za-z0-9&'.\-]+")

# A brand name never *ends* on one of these. Myntra titles follow the pattern
# "<brand> <audience> <colour> <descriptor> <type>", so without this guard the
# frequency heuristic happily learns "Catwalk Women" or "Baggit Women" as brands.
_BRAND_STOP_TOKENS = {
    # audience
    "men", "women", "man", "woman", "mens", "womens", "unisex", "boys", "girls",
    "kids", "kid", "baby", "infant", "junior", "adults",
    # colour words that appear immediately after a brand
    "black", "white", "blue", "brown", "grey", "gray", "red", "green", "pink",
    "navy", "purple", "silver", "yellow", "beige", "gold", "maroon", "orange",
    "olive", "multi", "cream", "steel", "charcoal", "peach", "off", "skin",
    "lavender", "khaki", "magenta", "teal", "tan", "mustard", "bronze",
    "copper", "turquoise", "rust", "burgundy", "metallic", "coffee", "mauve",
    "sea", "nude", "rose", "mushroom", "taupe", "lime", "fluorescent",
    # frequent descriptors / product nouns
    "solid", "printed", "striped", "checked", "slim", "regular", "classic",
    "casual", "formal", "sports", "sport", "round", "neck", "shirt", "tshirt",
    "t", "shirts", "top", "tops", "jeans", "watch", "watches", "shoes", "shoe",
    "sandals", "heels", "flats", "bag", "bags", "handbag", "wallet", "belt",
    "kurta", "kurtas", "saree", "dress", "lipstick", "perfume", "deodorant",
    "eau", "de", "the", "with", "a", "an",
}

# Connector words that can sit *inside* a brand ("United Colors of Benetton")
# but never terminate one.
_BRAND_CONNECTORS = {"of", "and", "&", "by", "for", "the", "n"}

_MAX_BRAND_TOKENS = 4


def _trim_brand(tokens: list[str]) -> list[str]:
    """Drop trailing audience/colour/descriptor/connector tokens."""
    while tokens and (
        tokens[-1].lower() in _BRAND_STOP_TOKENS
        or tokens[-1].lower() in _BRAND_CONNECTORS
    ):
        tokens = tokens[:-1]
    return tokens


def build_brand_lexicon(
    names: list[str],
    min_support: int = 5,
    multiword_ratio: float = 0.6,
) -> dict[str, str]:
    """Derive a brand lexicon from the corpus.

    Returns ``{lowercased_prefix: canonical_casing}``. Matching is
    case-insensitive because the source is inconsistent - "United Colors of
    Benetton" also appears as "United Colors Of Benetton", "United colors of
    benetton" and "united Colors Of Benetton".

    A one-token prefix is a brand candidate if it starts at least `min_support`
    products. It is then extended token by token while the longer prefix still
    accounts for at least `multiword_ratio` of the shorter one's products, which
    separates a real multi-word brand ("Lino Perros") from a brand followed by an
    audience word ("Catwalk Women ..."). Every trimmed prefix along that chain is
    kept, so both "Lencia" and a longer genuine form remain matchable and
    `extract_brand` can prefer the longest.
    """
    prefixes: list[Counter] = [Counter() for _ in range(_MAX_BRAND_TOKENS + 1)]
    casings: dict[str, Counter] = {}
    for name in names:
        tokens = _TOKEN_RE.findall(name or "")
        for n in range(1, min(_MAX_BRAND_TOKENS, len(tokens)) + 1):
            prefix = " ".join(tokens[:n])
            prefixes[n][prefix.lower()] += 1
            casings.setdefault(prefix.lower(), Counter())[prefix] += 1

    lexicon: set[str] = set()

    def accept(tokens: list[str]) -> None:
        trimmed = _trim_brand(tokens)
        if trimmed:
            lexicon.add(" ".join(trimmed).lower())

    for token, count in prefixes[1].items():
        if count < min_support:
            continue

        # The first token can itself be a colour word ("Red Tape", "Rose Taylor").
        # Such a unigram trims to nothing, so the brand has to be found among the
        # two-token prefixes instead of by following a single extension chain.
        if not _trim_brand([token]):
            for prefix, prefix_count in prefixes[2].items():
                if prefix.startswith(token + " ") and prefix_count >= min_support:
                    trimmed = _trim_brand(prefix.split(" "))
                    if len(trimmed) >= 2:
                        lexicon.add(" ".join(trimmed).lower())
                    else:
                        # Both tokens are colour words, so trimming destroys the
                        # name - but real brands look like this ("Red Rose",
                        # "Black Coffee"). Support alone has to carry it.
                        lexicon.add(prefix)
            continue

        current, current_count = [token], count
        accept(current)
        for n in range(2, _MAX_BRAND_TOKENS + 1):
            stem = " ".join(current) + " "
            best = max(
                ((p, c) for p, c in prefixes[n].items() if p.startswith(stem)),
                key=lambda kv: kv[1],
                default=None,
            )
            # keep extending through connectors regardless of ratio, since
            # "United Colors of" is a dead end that must reach "... Benetton"
            through_connector = current[-1].lower() in _BRAND_CONNECTORS
            if best and (through_connector or best[1] >= multiword_ratio * current_count):
                current, current_count = best[0].split(" "), best[1]
                accept(current)
            else:
                break

    return {
        key: casings[key].most_common(1)[0][0]
        for key in lexicon
        if key in casings
    }


def extract_brand(product_name: str, lexicon: dict[str, str]) -> str | None:
    """Longest-prefix, case-insensitive brand match against the lexicon."""
    tokens = _TOKEN_RE.findall(product_name or "")
    for n in range(min(_MAX_BRAND_TOKENS, len(tokens)), 0, -1):
        candidate = " ".join(tokens[:n]).lower()
        if candidate in lexicon:
            return lexicon[candidate]
    return None


# --------------------------------------------------------------------------
# Roles and searchable text
# --------------------------------------------------------------------------


def product_roles(category_group: str) -> tuple[bool, bool]:
    """(can_be_anchor, can_be_complement) for a category group."""
    return category_group in ANCHOR_GROUPS, category_group in COMPLEMENT_GROUPS


def classify_colour_role(article_type: str, category_group: str) -> str:
    """What the product's colour means: style, skin_match, or packaging."""
    return colour_role(article_type, category_group)


def colour_is_meaningful(article_type: str, category_group: str) -> bool:
    """True only when the colour is a style decision.

    False for foundation (matches a face, not an outfit) and for skincare or
    fragrance (the colour describes the container).
    """
    return colour_role(article_type, category_group) == "style"


def build_text_blob(
    product_name: str,
    brand: str | None,
    article_type: str,
    base_colour: str,
    colour_family: str,
    occasion: str,
    gender: str,
    finish: str | None,
) -> str:
    """Flat text representation, used later for semantic retrieval."""
    parts = [
        product_name,
        brand or "",
        article_type,
        base_colour,
        f"{colour_family} colour",
        f"{occasion} occasion",
        f"for {gender}",
        f"{finish} finish" if finish else "",
    ]
    return " | ".join(p.strip() for p in parts if p and p.strip())


# --------------------------------------------------------------------------
# Name hygiene
# --------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")


def clean_name(raw: object) -> str | None:
    """Collapse whitespace; return None for blank/unusable names."""
    if raw is None:
        return None
    text = _WS_RE.sub(" ", str(raw)).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    return text


def name_key(name: str, article_type: str, base_colour: str, gender: str) -> str:
    """Grouping key for products sharing an identical display name.

    NOT a de-duplication key. Myntra reuses generic display names across
    genuinely distinct products - "Lucera Women Silver Earrings" covers 82
    different designs, "Catwalk Women Black Heels" 49 - each with its own
    photograph. Collapsing on this key would delete real catalog variety, so it
    is only used to flag a name as generic.

    True duplicate listings are detected by identical image bytes instead.
    """
    return "|".join([name.lower(), article_type.lower(), base_colour.lower(), gender.lower()])
