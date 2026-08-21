"""Turn score components into a sentence a shopper would actually read.

The engine explains itself in its own terms - "catalogued as casual wear, which
suits a casual (1.00)". That is the right level of detail for a score breakdown
and the wrong level for a product card, so this module restates the same signals
in plain language.

Nothing is invented here. Every sentence is built from a component the scorer
actually produced, so an explanation cannot claim a reason the product did not
earn. Raw numbers, weights, model names and parser state stay out - they are
implementation detail, and a shopper reading "0.92" learns nothing.
"""

from __future__ import annotations

# How each occasion sounds in a sentence.
OCCASION_PHRASES = {
    "office": "an office look",
    "formal": "a formal outfit",
    "casual": "a casual look",
    "sports": "a sporty outfit",
    "party": "a party",
    "wedding": "a wedding outfit",
    "festive": "a festive outfit",
}

# Plural catalog product types read badly in a sentence ("a Shirts").
SINGULAR = {
    "Shirts": "shirt", "Tshirts": "T-shirt", "Jeans": "jeans", "Trousers": "trousers",
    "Shorts": "shorts", "Track Pants": "track pants", "Kurtas": "kurta",
    "Kurtis": "kurti", "Sarees": "saree", "Dresses": "dress", "Tops": "top",
    "Heels": "heels", "Flats": "flats", "Sandals": "sandals", "Watches": "watch",
    "Sunglasses": "sunglasses", "Handbags": "handbag", "Clutches": "clutch",
    "Belts": "belt", "Socks": "socks", "Caps": "cap", "Backpacks": "backpack",
    "Sports Shoes": "running shoes", "Formal Shoes": "formal shoes",
    "Casual Shoes": "casual shoes", "Sweaters": "sweater",
    "Sweatshirts": "sweatshirt", "Tracksuits": "tracksuit",
    "Perfume and Body Mist": "fragrance", "Deodorant": "deodorant",
    "Lipstick": "lipstick", "Nail Polish": "nail polish", "Earrings": "earrings",
    "Jackets": "jacket", "Skirts": "skirt", "Leggings": "leggings",
    "Nehru Jackets": "Nehru jacket", "Churidar": "churidar", "Dupatta": "dupatta",
}

NEUTRALS = {"black", "white", "grey", "beige", "brown"}

# Nouns that are already plural: "a blue jeans" reads badly, "blue jeans" does not.
PLURAL = {"jeans", "trousers", "shorts", "track pants", "leggings", "heels",
          "flats", "sandals", "sunglasses", "socks", "earrings", "formal shoes",
          "casual shoes", "running shoes", "shoes"}


def _phrase_with_article(colour: str, noun: str) -> str:
    """"a black shirt" / "black jeans" - whichever is grammatical."""
    piece = f"{colour} {noun}".strip() if colour else noun
    if noun in PLURAL:
        return piece
    article = "an" if piece[:1].lower() in "aeiou" else "a"
    return f"{article} {piece}"


def _noun(product_type: str) -> str:
    return SINGULAR.get(product_type, (product_type or "piece").lower())


def _occasion(occasion: str | None) -> str | None:
    return OCCASION_PHRASES.get(occasion) if occasion else None


def _raw(components, name: str) -> float | None:
    for component in components:
        if component.name == name:
            return component.raw
    return None


def explain(recommendation, *, role: str, occasion: str | None,
            requested_colour: str | None) -> list[str]:
    """Two short sentences at most: why it fits, and why it goes with the look."""
    components = recommendation.components or ()
    noun = _noun(recommendation.product_type)
    colour = (recommendation.colour_family or "").lower()
    phrase = _occasion(occasion)
    lines: list[str] = []

    if role == "primary":
        colour_match = _raw(components, "colour_match")
        category_match = _raw(components, "category_match")

        # The main piece of a look nobody specified ("casual wear") was not
        # searched for by name, so it cannot be "what you searched for".
        if colour_match is None and category_match is None:
            # Naming the colour keeps four shirts in a row from reading
            # identically.
            piece = _phrase_with_article(colour, noun)
            opening = (f"{piece} that works well for {phrase}." if phrase
                       else f"{piece} to start the outfit with.")
            return ["A simple " + opening[2:] if opening.startswith("a ")
                    else opening[0].upper() + opening[1:]]

        if colour_match is not None and colour_match >= 1.0:
            opening = f"{_phrase_with_article(colour, noun)}, which is what you searched for."
        elif colour_match is not None and colour_match >= 0.6:
            opening = (f"{_phrase_with_article(colour, noun)}, the closest shade "
                       f"to {requested_colour} in the catalog.")
        elif category_match is not None and category_match >= 1.0:
            opening = f"This is the {noun} you searched for."
        else:
            opening = f"{_phrase_with_article('', noun)} close to what you searched for."
        lines.append(opening[0].upper() + opening[1:])

        fit = _raw(components, "occasion_suitability")
        if phrase and fit is not None:
            if fit >= 0.85:
                lines.append(f"Good for {phrase}.")
            elif fit >= 0.5:
                lines.append(f"Can work for {phrase}.")
        return lines

    # A complement: it is here because it goes with the look, so say that first.
    harmony = _raw(components, "colour_harmony")
    if harmony is not None and harmony >= 0.75:
        lines.append(
            f"This {colour} works well with the rest of the outfit."
            if colour in NEUTRALS else
            f"The {colour} stands out nicely against the main piece.")
    elif harmony is not None and harmony >= 0.5:
        lines.append(f"A {colour} that does not clash with the main piece.")

    fit = _raw(components, "occasion_suitability")
    if phrase and fit is not None and fit >= 0.7:
        lines.append(f"Suits {phrase}.")
    elif not lines:
        rounds = f"{_phrase_with_article('', noun)} to finish the outfit."
        lines.append(rounds[0].upper() + rounds[1:])

    return lines[:2]
