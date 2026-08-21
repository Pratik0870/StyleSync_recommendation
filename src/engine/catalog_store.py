"""Catalog access and anchor resolution.

The single path by which a product reaches a recommendation. Every id returned
by the engine is resolved through `CatalogStore`, so a product that is not in
the Phase 1 catalog cannot appear in a response.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import cached_property, lru_cache

import pandas as pd

from ..catalog.taxonomy import ANCHOR_GROUPS, COLOUR_MAP

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CATALOG = os.path.join(ROOT, "data", "processed", "catalog.parquet")


# --------------------------------------------------------------------------
# Free-text -> catalog vocabulary
# --------------------------------------------------------------------------

# Anchor garment words a user might type, mapped onto the Phase 1 taxonomy.
ANCHOR_TYPE_HINTS: dict[str, tuple[str, str | None]] = {
    # ethnic
    "saree": ("ethnic_wear", "Sarees"), "sari": ("ethnic_wear", "Sarees"),
    "lehenga": ("ethnic_wear", "Lehenga Choli"),
    "kurta": ("ethnic_wear", "Kurtas"), "kurti": ("ethnic_wear", "Kurtis"),
    "kurta set": ("ethnic_wear", "Kurta Sets"),
    "salwar": ("ethnic_wear", "Salwar"), "churidar": ("ethnic_wear", "Churidar"),
    "anarkali": ("ethnic_wear", "Kurtas"), "tunic": ("ethnic_wear", "Tunics"),
    "ethnic": ("ethnic_wear", None),
    # western
    "dress": ("dress", "Dresses"), "gown": ("dress", "Dresses"),
    "jumpsuit": ("dress", "Jumpsuit"),
    "top": ("topwear", "Tops"), "shirt": ("topwear", "Shirts"),
    "tshirt": ("topwear", "Tshirts"), "t-shirt": ("topwear", "Tshirts"),
    "blouse": ("topwear", "Tops"), "sweater": ("topwear", "Sweaters"),
    "sweatshirt": ("topwear", "Sweatshirts"),
    "jeans": ("bottomwear", "Jeans"), "trousers": ("bottomwear", "Trousers"),
    "skirt": ("bottomwear", "Skirts"), "shorts": ("bottomwear", "Shorts"),
    "leggings": ("bottomwear", "Leggings"), "palazzo": ("bottomwear", "Trousers"),
    "jacket": ("outerwear", "Jackets"), "blazer": ("outerwear", "Blazers"),
    "coat": ("outerwear", "Jackets"),
}


def _colour_lookup() -> dict[str, str]:
    """Every word a user might use for a colour -> normalised family."""
    table: dict[str, str] = {}
    for raw, (family, _, _, _) in COLOUR_MAP.items():
        table[raw.lower()] = family
    for family in {v[0] for v in COLOUR_MAP.values()}:
        table.setdefault(family, family)
    # common phrasings the source vocabulary does not contain
    table.update({
        "navy": "blue", "sky blue": "blue", "royal blue": "blue",
        "wine": "red", "crimson": "red", "scarlet": "red", "cherry": "red",
        "berry": "purple", "plum": "purple", "violet": "purple",
        "fuchsia": "pink", "blush": "pink", "rose gold": "gold",
        "ivory": "white", "off-white": "white", "champagne": "beige",
        "tan": "brown", "chocolate": "brown", "camel": "beige",
        "emerald": "green", "mint": "green", "grey": "grey", "gray": "grey",
        "silver": "silver", "golden": "gold", "multicolour": "multi",
        "multicolor": "multi", "multi-coloured": "multi",
    })
    return table


COLOUR_LOOKUP = _colour_lookup()


@lru_cache(maxsize=512)
def _phrase_pattern(phrase: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")


def _match_phrase(text: str, vocabulary) -> str | None:
    """Longest whole-word phrase from `vocabulary` occurring in `text`.

    Word boundaries are load-bearing, not cosmetic: plain substring matching
    resolved "ultraviolet" to purple (it contains "violet"), "blackberry" to
    black, and "laptop bag" to a topwear anchor (it contains "top"). Free text
    reaches this function from users and from an LLM, so a loose match here
    silently feeds the engine a garment or colour nobody asked for.
    """
    best: str | None = None
    for phrase in vocabulary:
        if (best is None or len(phrase) > len(best)) and _phrase_pattern(phrase).search(text):
            best = phrase
    return best


def resolve_colour(text: str | None) -> str | None:
    """Free-text colour -> normalised family, or None."""
    if not text:
        return None
    lowered = text.strip().lower()
    if lowered in COLOUR_LOOKUP:
        return COLOUR_LOOKUP[lowered]
    # longest phrase first, so "navy blue" beats "blue"
    phrase = _match_phrase(lowered, COLOUR_LOOKUP)
    return COLOUR_LOOKUP[phrase] if phrase else None


def resolve_anchor_type(text: str | None) -> tuple[str | None, str | None]:
    """Free-text garment -> (category_group, product_type or None)."""
    if not text:
        return None, None
    lowered = text.strip().lower()
    if lowered in ANCHOR_TYPE_HINTS:
        return ANCHOR_TYPE_HINTS[lowered]
    phrase = _match_phrase(lowered, ANCHOR_TYPE_HINTS)
    return ANCHOR_TYPE_HINTS[phrase] if phrase else (None, None)


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedAnchor:
    category_group: str | None
    product_type: str | None
    colour_family: str | None
    gender: str | None
    source: str                 # "catalog_product" | "described" | "partial"
    product_id: int | None = None
    name: str | None = None
    base_colour: str | None = None
    unresolved: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "product_id": self.product_id,
            "name": self.name,
            "category_group": self.category_group,
            "product_type": self.product_type,
            "colour_family": self.colour_family,
            "base_colour": self.base_colour,
            "gender": self.gender,
            "unresolved": list(self.unresolved),
        }


class UnknownProduct(Exception):
    pass


class CatalogStore:
    """Read-only view over the Phase 1 catalog."""

    def __init__(self, path: str | None = None, frame: pd.DataFrame | None = None):
        if frame is not None:
            self.df = frame.reset_index(drop=True)
        else:
            self.df = pd.read_parquet(path or DEFAULT_CATALOG).reset_index(drop=True)
        self._by_id = {int(p): i for i, p in enumerate(self.df.product_id)}

    def __len__(self) -> int:
        return len(self.df)

    @cached_property
    def complements(self) -> pd.DataFrame:
        return self.df[self.df.can_be_complement].reset_index(drop=True)

    @cached_property
    def available_complement_groups(self) -> set[str]:
        return set(self.complements.category_group.unique())

    def get(self, product_id: int) -> pd.Series:
        index = self._by_id.get(int(product_id))
        if index is None:
            raise UnknownProduct(f"product_id {product_id} is not in the catalog")
        return self.df.iloc[index]

    def exists(self, product_id: int) -> bool:
        return int(product_id) in self._by_id

    # ---- anchor resolution -------------------------------------------

    def resolve_anchor(
        self,
        product_id: int | None,
        anchor_type: str | None,
        colour: str | None,
        gender_hint: str | None = None,
    ) -> ResolvedAnchor:
        if product_id is not None:
            row = self.get(product_id)          # raises UnknownProduct
            return ResolvedAnchor(
                category_group=row.category_group,
                product_type=row.product_type,
                colour_family=row.colour_family,
                gender=row.gender,
                source="catalog_product",
                product_id=int(row.product_id),
                name=row["name"],
                base_colour=row.base_colour,
            )

        group, ptype = resolve_anchor_type(anchor_type)
        family = resolve_colour(colour)
        unresolved = []
        if anchor_type and group is None:
            unresolved.append(f"garment '{anchor_type}'")
        if colour and family is None:
            unresolved.append(f"colour '{colour}'")

        return ResolvedAnchor(
            category_group=group,
            product_type=ptype,
            colour_family=family,
            gender=gender_hint,
            source="described" if (group or family) else "partial",
            unresolved=tuple(unresolved),
        )

    # ---- candidate pools ---------------------------------------------

    def candidate_pool(
        self,
        category_group: str,
        gender: str | None = None,
        adults_only: bool = True,
    ) -> pd.DataFrame:
        """Legal candidates for one complement category, before scoring.

        Note what is deliberately *not* filtered here: `colour_role`. A perfume
        whose colour is packaging is still a legitimate recommendation - it just
        must not be colour-matched. That is a scoring rule, applied in
        `scoring.py`, not a reason to drop the product.
        """
        pool = self.complements[self.complements.category_group == category_group]
        if adults_only:
            pool = pool[pool.age_group == "adult"]
        if gender:
            pool = pool[pool.gender.isin([gender, "unisex"])]
        return pool.reset_index(drop=True)
