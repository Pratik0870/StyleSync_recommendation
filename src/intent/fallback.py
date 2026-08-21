"""Deterministic intent parser - the no-LLM path.

The application must be fully usable without an API key, so this is not a
degraded stub: it parses the same query shapes the LLM handles, using the same
vocabularies the engine already ships (garment hints, colour lookup, occasion
and style synonyms, category phrases). Its output goes through exactly the same
`normalise()` step, so both paths are bound by the identical contract.

What it cannot do that the LLM can: unusual phrasing, implicit occasion
("my cousin's big day"), negation in unexpected forms, or vocabulary outside
the lexicons. Those are reported as unparsed rather than guessed.
"""

from __future__ import annotations

import re

from ..engine.catalog_store import ANCHOR_TYPE_HINTS, COLOUR_LOOKUP
from ..engine.occasion import _OCCASION_SYNONYMS
from ..engine.scoring import _STYLE_SYNONYMS
from .schema import CATEGORY_PHRASES, ExtractedIntent

# Material / pattern / cut words. Only these reach text relevance - the Phase 2
# benchmark showed text is worth its weight for exactly this vocabulary.
DESCRIPTOR_WORDS = {
    "silk", "cotton", "leather", "denim", "satin", "velvet", "chiffon",
    "georgette", "linen", "wool", "lace", "net", "crepe",
    "printed", "solid", "striped", "checked", "embroidered", "embellished",
    "sequin", "sequined", "zari", "woven", "textured", "floral", "polka",
    "matte", "glossy", "shimmer", "metallic", "beaded", "studded",
    "classic", "vintage", "handcrafted", "oxidised", "antique",
}

# Phrases that flip the following category words into an exclusion.
_NEGATION = re.compile(
    r"\b(no|not|without|avoid|skip|don'?t\s+want|do\s+not\s+want|except)\b", re.I)

_GENDER_WORDS = {
    "women": "women", "woman": "women", "female": "women", "womens": "women",
    "her": "women", "she": "women", "girl": "women", "ladies": "women",
    "men": "men", "man": "men", "male": "men", "mens": "men",
    "him": "men", "he": "men", "boy": "men", "gents": "men",
    "unisex": "unisex",
}

_TOKEN_RE = re.compile(r"[a-z0-9'-]+")

# Phrases that mean "assemble a whole look", not "find me one item".
# Asking to be styled, in the ways people actually phrase it. The literal word
# "outfit" is only one of them.
_OUTFIT_PHRASES = (
    "outfit", "complete look", "full look", "whole look", "entire look",
    "head to toe", "complete the look",
    # "what should/can/do I wear …"
    "what should i wear", "what can i wear", "what do i wear", "what to wear",
    "what shall i wear", "what should i put on",
    # asking to be dressed or styled
    "help me dress", "dress me", "help me get ready", "getting ready",
    "style me", "styling for", "style for",
    # "give me / need / want a look"
    "give me a look", "need a look", "want a look", "suggest a look",
    "show me a look", "build me a look", "put together a look",
    # "I need something to wear"
    "something to wear", "anything to wear", "nothing to wear",
    # attending something
    "going to a", "going to the", "going for", "i am going", "i'm going",
    "im going", "attending a", "attending my", "invited to",
)

# Saying you already own the garment is the opposite signal: you want things
# that go WITH it, not a wardrobe rebuilt around it. "I'm wearing a black saree
# to a wedding" must keep returning complements - that is the product's whole
# promise - while "I am going to a wedding" asks to be dressed.
_OWNERSHIP_PHRASES = ("i am wearing", "i'm wearing", "im wearing", "i have a",
                      "i have my", "i've got", "i already have", "i own")

_TIME_PHRASES = ("tomorrow", "tonight", "today", "this weekend", "next week",
                 "this evening", "tonite", "day after tomorrow")


def _find_phrases(text: str, vocabulary) -> list[tuple[int, str]]:
    """Locate vocabulary phrases in `text`, longest first, without overlap."""
    found: list[tuple[int, str]] = []
    consumed: list[tuple[int, int]] = []
    for phrase in sorted(vocabulary, key=len, reverse=True):
        start = 0
        while True:
            index = text.find(phrase, start)
            if index == -1:
                break
            end = index + len(phrase)
            before_ok = index == 0 or not text[index - 1].isalnum()
            after_ok = end >= len(text) or not text[end].isalnum()
            if before_ok and after_ok and not any(s < end and index < e for s, e in consumed):
                found.append((index, phrase))
                consumed.append((index, end))
            start = end
    return sorted(found)


def parse(query: str) -> ExtractedIntent:
    """Free text -> ExtractedIntent, deterministically."""
    text = (query or "").lower().strip()
    if not text:
        return ExtractedIntent()

    # ---- garment -----------------------------------------------------
    garments = _find_phrases(text, ANCHOR_TYPE_HINTS)
    anchor_type = garments[0][1] if garments else None
    anchor_position = garments[0][0] if garments else None

    # ---- colours -----------------------------------------------------
    # The colour that sits closest *before* the garment describes the garment;
    # any others are treated as preferences for the recommendations.
    colours = _find_phrases(text, COLOUR_LOOKUP)
    anchor_colour = None
    preferred: list[str] = []
    if colours:
        if anchor_position is not None:
            before = [(pos, name) for pos, name in colours if pos < anchor_position]
            if before:
                anchor_colour = before[-1][1]
            else:
                anchor_colour = colours[0][1]
        else:
            anchor_colour = colours[0][1]
        preferred = [name for pos, name in colours if name != anchor_colour]

    # ---- occasion and style ------------------------------------------
    occasions = _find_phrases(text, _OCCASION_SYNONYMS)
    occasion = occasions[0][1] if occasions else None

    styles = _find_phrases(text, _STYLE_SYNONYMS)
    # "party" is both an occasion and a style synonym; if it was already read as
    # the occasion, do not also report it as the style.
    style = None
    for _, phrase in styles:
        if occasion and phrase == occasions[0][1]:
            continue
        style = phrase
        break

    # ---- gender ------------------------------------------------------
    # Scanned across the whole sentence, so a trailing "man" is caught as
    # readily as a leading "men's".
    gender = None
    for token in _TOKEN_RE.findall(text):
        # "women's" tokenises with its apostrophe; strip possessives so the
        # lookup matches the same word however it was written.
        key = token.replace("'", "").rstrip("s") if token.endswith("'s") else token
        for candidate in (token, token.replace("'", ""), key):
            if candidate in _GENDER_WORDS:
                gender = _GENDER_WORDS[candidate]
                break
        if gender:
            break

    # ---- outfit vs product ------------------------------------------
    owns_garment = any(phrase in text for phrase in _OWNERSHIP_PHRASES)
    outfit = any(phrase in text for phrase in _OUTFIT_PHRASES) and not owns_garment

    time_context = next((p for p in _TIME_PHRASES if p in text), None)

    # ---- categories, with negation -----------------------------------
    include: list[str] = []
    exclude: list[str] = []
    negations = [m.end() for m in _NEGATION.finditer(text)]
    for position, phrase in _find_phrases(text, CATEGORY_PHRASES):
        # a negation counts if it appears within ~24 characters before the word
        negated = any(0 <= position - end <= 24 for end in negations)
        (exclude if negated else include).append(phrase)

    # ---- descriptors --------------------------------------------------
    descriptors = [word for word in _TOKEN_RE.findall(text) if word in DESCRIPTOR_WORDS]

    return ExtractedIntent(
        intent_type="outfit" if outfit else "product",
        owns_anchor=owns_garment and anchor_type is not None,
        time_context=time_context,
        anchor_type=anchor_type,
        colour=anchor_colour,
        occasion=occasion,
        style=style,
        gender=gender,
        preferred_colours=list(dict.fromkeys(preferred)),
        include_categories=list(dict.fromkeys(include)),
        exclude_categories=list(dict.fromkeys(exclude)),
        descriptors=list(dict.fromkeys(descriptors)),
    )
