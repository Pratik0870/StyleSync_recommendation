"""Shared fixtures.

Unit tests run against a small synthetic catalog so they are fast, deterministic
and independent of the data build. Integration tests that need the real 43,165
-product catalog are marked and skip cleanly if it has not been built.
"""

import os
import sys

import pandas as pd
import pytest

# The test suite exercises the engine and the API contract, not a live language
# model. Forcing the deterministic parser keeps every run offline, fast and
# repeatable - a network call would make results depend on a provider's mood.
# Tests that specifically cover the LLM layer construct a provider explicitly.
os.environ["DISABLE_LLM"] = "1"

# The image resolver fetches real photography from a public mirror on demand.
# Tests must never depend on that being reachable, so the resolver is switched
# off here and its behaviour is covered with an explicit fake instead.
os.environ["DISABLE_IMAGE_FETCH"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.catalog_store import DEFAULT_CATALOG, CatalogStore  # noqa: E402

_COLUMNS = [
    "product_id", "name", "brand", "domain", "category_group", "product_type",
    "base_colour", "colour_family", "colour_role", "occasion", "finish",
    "is_metallic", "gender", "age_group", "can_be_anchor", "can_be_complement",
    "text_blob",
]


def product(
    product_id,
    name,
    category_group,
    colour_family="red",
    *,
    domain="accessory",
    product_type=None,
    colour_role="style",
    occasion="ethnic",
    finish=None,
    brand="TestBrand",
    gender="women",
    is_metallic=False,
    can_be_anchor=False,
    can_be_complement=True,
    text_blob=None,
):
    return {
        "product_id": product_id,
        "name": name,
        "brand": brand,
        "domain": domain,
        "category_group": category_group,
        "product_type": product_type or category_group,
        "base_colour": colour_family.capitalize(),
        "colour_family": colour_family,
        "colour_role": colour_role,
        "occasion": occasion,
        "finish": finish,
        "is_metallic": is_metallic,
        "gender": gender,
        "age_group": "adult",
        "can_be_anchor": can_be_anchor,
        "can_be_complement": can_be_complement,
        "text_blob": text_blob or f"{name} | {colour_family} colour | {occasion} occasion",
    }


def make_store(rows) -> CatalogStore:
    frame = pd.DataFrame(rows, columns=_COLUMNS)
    return CatalogStore(frame=frame)


@pytest.fixture
def tiny_store():
    """A catalog with enough breadth to exercise the whole pipeline."""
    rows = []
    pid = 1000
    # jewellery: a spread of colours, several brands
    for colour, metallic in [("gold", True), ("silver", True), ("red", False),
                             ("green", False), ("pink", False), ("blue", False),
                             ("white", False), ("black", False), ("purple", False),
                             ("brown", False)]:
        for n in range(3):
            rows.append(product(pid, f"Brand{n} {colour} Earrings", "jewellery",
                                colour, product_type="Earrings",
                                brand=f"Brand{n}", is_metallic=metallic))
            pid += 1
    # lip products, including one shimmer and one matte
    for colour, finish in [("red", "matte"), ("brown", "satin"), ("pink", "gloss"),
                           ("purple", "shimmer"), ("beige", None), ("gold", "shimmer"),
                           ("orange", None), ("black", None), ("green", None),
                           ("blue", None)]:
        rows.append(product(pid, f"Lakme {colour} Lipstick", "beauty_lip", colour,
                            domain="beauty", product_type="Lipstick",
                            occasion="casual", finish=finish, brand="Lakme"))
        pid += 1
    # a mixed beauty_face category: mostly skin-match, a little blush
    for n in range(8):
        rows.append(product(pid, f"Foundation {n}", "beauty_face", "beige",
                            domain="beauty", product_type="Foundation and Primer",
                            colour_role="skin_match", occasion="casual"))
        pid += 1
    for colour in ("pink", "red"):
        rows.append(product(pid, f"Blush {colour}", "beauty_face", colour,
                            domain="beauty", product_type="Highlighter and Blush",
                            occasion="casual"))
        pid += 1
    # fragrance: colour is packaging throughout
    for n, colour in enumerate(("white", "black", "gold")):
        rows.append(product(pid, f"Perfume {n}", "fragrance", colour,
                            domain="beauty", product_type="Perfume and Body Mist",
                            colour_role="packaging", occasion="casual"))
        pid += 1
    # a deliberately thin category
    rows.append(product(pid, "Only Headband", "headwear", "red",
                        product_type="Headband"))
    pid += 1
    # anchors
    rows.append(product(pid, "Black Saree", "ethnic_wear", "black", domain="apparel",
                        product_type="Sarees", can_be_anchor=True,
                        can_be_complement=False))
    return make_store(rows)


@pytest.fixture
def real_store():
    if not os.path.exists(DEFAULT_CATALOG):
        pytest.skip("catalog not built - run scripts/ingest_catalog.py")
    return CatalogStore()
