"""The intent contract between natural language and the recommendation engine.

`ExtractedIntent` is the ONLY thing an LLM is allowed to produce. Read its
fields: there is no `product_id`, no `product_name`, no `price`, no `score`, no
`image`. A model that hallucinated a product would have nowhere to put it, so
hallucinated products cannot reach a response - not because we filter them out
afterwards, but because the schema has no channel for them.

`NormalisedIntent` is what the engine receives. Getting from one to the other
runs every field through the engine's *own* vocabulary resolvers, so the LLM
also cannot introduce a colour, garment, occasion, style or category the engine
does not already understand. Anything unrecognised is dropped and reported in
`rejected`, never guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ..engine.catalog_store import resolve_anchor_type, resolve_colour
from ..engine.occasion import CANONICAL_OCCASIONS, normalise_occasion
from ..engine.scoring import STYLE_PROFILES, normalise_style

VALID_GENDERS = {"women", "men", "unisex"}

# Words a user might use for a group of categories, mapped onto the Phase 1
# taxonomy. Kept here rather than in the LLM prompt so the mapping is testable
# and identical on the LLM and fallback paths.
CATEGORY_PHRASES: dict[str, tuple[str, ...]] = {
    "makeup": ("beauty_lip", "beauty_eye", "beauty_face", "beauty_nails"),
    "make-up": ("beauty_lip", "beauty_eye", "beauty_face", "beauty_nails"),
    "cosmetics": ("beauty_lip", "beauty_eye", "beauty_face", "beauty_nails"),
    "beauty": ("beauty_lip", "beauty_eye", "beauty_face", "beauty_nails"),
    "lipstick": ("beauty_lip",), "lip": ("beauty_lip",), "gloss": ("beauty_lip",),
    "eyeliner": ("beauty_eye",), "kajal": ("beauty_eye",), "eyeshadow": ("beauty_eye",),
    "mascara": ("beauty_eye",), "eye makeup": ("beauty_eye",),
    "foundation": ("beauty_face",), "blush": ("beauty_face",),
    "highlighter": ("beauty_face",), "compact": ("beauty_face",),
    "nail": ("beauty_nails",), "nails": ("beauty_nails",),
    "nail polish": ("beauty_nails",),
    "perfume": ("fragrance",), "fragrance": ("fragrance",), "deodorant": ("fragrance",),
    "jewellery": ("jewellery",), "jewelry": ("jewellery",),
    "earrings": ("jewellery",), "necklace": ("jewellery",), "bangle": ("jewellery",),
    "bracelet": ("jewellery",), "ring": ("jewellery",), "pendant": ("jewellery",),
    "accessories": ("jewellery", "bag"),
    "bag": ("bag",), "bags": ("bag",), "handbag": ("bag",), "clutch": ("bag",),
    "purse": ("bag",), "wallet": ("wallet",),
    "footwear": ("footwear_dress", "footwear_flat", "footwear_casual", "footwear_formal"),
    "shoes": ("footwear_dress", "footwear_flat", "footwear_casual", "footwear_formal"),
    "heels": ("footwear_dress",), "sandals": ("footwear_flat",),
    "flats": ("footwear_flat",), "sneakers": ("footwear_casual",),
    "watch": ("watch",), "watches": ("watch",),
    "sunglasses": ("eyewear",), "eyewear": ("eyewear",),
    "belt": ("belt",), "scarf": ("neckwear",), "dupatta": ("neckwear",),
    "stole": ("neckwear",), "tie": ("neckwear",),
    "cap": ("headwear",), "hat": ("headwear",),
}


# --------------------------------------------------------------------------
# What the LLM may return
# --------------------------------------------------------------------------


class ExtractedIntent(BaseModel):
    """Strict schema for LLM output. Free text in, structured attributes out.

    Every field is optional: the model is told to omit anything the user did
    not say rather than invent a plausible value.
    """

    intent_type: str | None = Field(
        None, description="'outfit' when the shopper wants a whole look put "
                          "together, 'product' when they want one kind of item.")
    time_context: str | None = Field(
        None, description="A time reference the shopper used, e.g. 'tomorrow'. "
                          "Context only - it says nothing about availability.")
    owns_anchor: bool | None = Field(
        None, description="True when the shopper already has or is wearing the "
                          "garment ('I'm wearing a red saree'). Then they want "
                          "things to go WITH it, not more of it.")
    anchor_type: str | None = Field(
        None, description="The garment the user already has or plans to wear, "
                          "e.g. 'saree', 'dress', 'kurta', 'shirt', 'jeans'.")
    colour: str | None = Field(
        None, description="Colour of that garment, e.g. 'black', 'navy blue'.")
    occasion: str | None = Field(
        None, description=f"One of: {', '.join(CANONICAL_OCCASIONS)}. "
                          "Map synonyms (shaadi -> wedding, diwali -> festive).")
    style: str | None = Field(
        None, description=f"One of: {', '.join(sorted(STYLE_PROFILES))}.")
    gender: str | None = Field(
        None, description="One of: women, men, unisex. Only if stated or clearly implied.")
    preferred_colours: list[str] = Field(
        default_factory=list,
        description="Colours the user asked the RECOMMENDATIONS to be, "
                    "not the colour of their garment.")
    include_categories: list[str] = Field(
        default_factory=list,
        description="Product categories the user explicitly asked for, "
                    "e.g. 'makeup', 'jewellery', 'footwear'.")
    exclude_categories: list[str] = Field(
        default_factory=list,
        description="Product categories the user explicitly does not want.")
    descriptors: list[str] = Field(
        default_factory=list,
        description="Material, pattern or cut words only, e.g. 'silk', 'printed', "
                    "'leather'. Not colours, not occasions, not styles.")

    model_config = {"extra": "forbid"}


# --------------------------------------------------------------------------
# What the engine receives
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalisedIntent:
    intent_type: str = "product"          # "product" | "outfit"
    owns_anchor: bool = False             # they already have the named garment
    time_context: str | None = None
    gender_explicit: bool = False         # user actually stated it
    anchor_type: str | None = None
    anchor_category_group: str | None = None
    anchor_product_type: str | None = None    # e.g. "Sarees", from the taxonomy
    colour: str | None = None
    occasion: str | None = None
    style: str | None = None
    gender: str | None = None
    preferred_colours: tuple[str, ...] = ()
    include_categories: tuple[str, ...] = ()
    exclude_categories: tuple[str, ...] = ()
    free_text: str | None = None
    source: str = "fallback"            # "llm" | "fallback"
    rejected: tuple[str, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return not any([
            self.anchor_type, self.colour, self.occasion, self.style,
            self.preferred_colours, self.include_categories, self.free_text,
        ])

    @property
    def is_outfit(self) -> bool:
        return self.intent_type == "outfit"

    def to_dict(self) -> dict:
        return {
            "intent_type": self.intent_type,
            "owns_anchor": self.owns_anchor,
            "time_context": self.time_context,
            "gender_explicit": self.gender_explicit,
            "anchor_type": self.anchor_type,
            "anchor_category": self.anchor_category_group,
            "anchor_product_type": self.anchor_product_type,
            "colour": self.colour,
            "occasion": self.occasion,
            "style": self.style,
            "gender": self.gender,
            "preferred_colours": list(self.preferred_colours),
            "include_categories": list(self.include_categories),
            "exclude_categories": list(self.exclude_categories),
            "descriptors": self.free_text,
            "source": self.source,
            "rejected": list(self.rejected),
        }


def resolve_categories(
    phrases: list[str],
    known_groups: set[str],
) -> tuple[tuple[str, ...], list[str]]:
    """Category words -> Phase 1 category groups. Returns (resolved, rejected)."""
    resolved: list[str] = []
    rejected: list[str] = []
    for raw in phrases:
        if not isinstance(raw, str):
            continue
        key = raw.strip().lower()
        if not key:
            continue
        if key in known_groups:                       # already a taxonomy value
            resolved.append(key)
            continue
        mapped = CATEGORY_PHRASES.get(key)
        if mapped is None:
            # try a contained phrase, longest first ("nail polish" before "nail")
            for phrase in sorted(CATEGORY_PHRASES, key=len, reverse=True):
                if phrase in key:
                    mapped = CATEGORY_PHRASES[phrase]
                    break
        if mapped is None:
            rejected.append(f"category '{raw}'")
            continue
        resolved.extend(g for g in mapped if g in known_groups)
    return tuple(dict.fromkeys(resolved)), rejected


def normalise(intent: ExtractedIntent, known_groups: set[str], source: str) -> NormalisedIntent:
    """Validate and map an extracted intent onto the engine's vocabulary.

    Anything the engine does not recognise is dropped and recorded, never
    coerced into a nearby value.
    """
    rejected: list[str] = []

    anchor_group, anchor_product_type = resolve_anchor_type(intent.anchor_type)
    if intent.anchor_type and anchor_group is None:
        rejected.append(f"garment '{intent.anchor_type}'")

    colour = resolve_colour(intent.colour)
    if intent.colour and colour is None:
        rejected.append(f"colour '{intent.colour}'")

    occasion = normalise_occasion(intent.occasion)
    if intent.occasion and occasion is None:
        rejected.append(f"occasion '{intent.occasion}'")

    style = normalise_style(intent.style)
    if intent.style and style is None:
        rejected.append(f"style '{intent.style}'")

    gender = (intent.gender or "").strip().lower() or None
    if gender and gender not in VALID_GENDERS:
        rejected.append(f"gender '{intent.gender}'")
        gender = None

    preferred: list[str] = []
    for raw in intent.preferred_colours:
        resolved = resolve_colour(raw) if isinstance(raw, str) else None
        if resolved:
            preferred.append(resolved)
        elif raw:
            rejected.append(f"preferred colour '{raw}'")

    include, include_rejected = resolve_categories(intent.include_categories, known_groups)
    exclude, exclude_rejected = resolve_categories(intent.exclude_categories, known_groups)
    rejected.extend(include_rejected + exclude_rejected)

    descriptors = " ".join(
        d.strip() for d in intent.descriptors
        if isinstance(d, str) and d.strip()) or None

    intent_type = (intent.intent_type or "").strip().lower()
    if intent_type not in {"product", "outfit"}:
        if intent.intent_type:
            rejected.append(f"intent type '{intent.intent_type}'")
        intent_type = "product"

    return NormalisedIntent(
        intent_type=intent_type,
        owns_anchor=bool(intent.owns_anchor),
        time_context=(intent.time_context or None),
        gender_explicit=gender is not None,
        anchor_type=intent.anchor_type if anchor_group else None,
        anchor_category_group=anchor_group,
        anchor_product_type=anchor_product_type,
        colour=colour,
        occasion=occasion,
        style=style,
        gender=gender,
        preferred_colours=tuple(dict.fromkeys(preferred)),
        include_categories=include,
        exclude_categories=exclude,
        free_text=descriptors,
        source=source,
        rejected=tuple(dict.fromkeys(rejected)),
    )
