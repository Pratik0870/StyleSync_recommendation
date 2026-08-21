"""Unit tests for catalog normalisation.

These run without the dataset - every function under test is a pure mapping.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.catalog.normalize import (
    build_brand_lexicon,
    build_text_blob,
    clean_name,
    classify_colour_role,
    colour_is_meaningful,
    extract_brand,
    name_key,
    normalise_audience,
    normalise_category_group,
    normalise_colour,
    normalise_domain,
    normalise_occasion,
    parse_finish,
    product_roles,
)
from src.catalog.taxonomy import (
    CATEGORY_GROUP_MAP,
    COLOUR_MAP,
    DOMAIN_MAP,
    GENDER_MAP,
    OCCASION_MAP,
)


# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------


def test_every_source_colour_maps_to_a_family():
    for raw in COLOUR_MAP:
        result = normalise_colour(raw)
        assert result["colour_family"]
        assert isinstance(result["is_neutral"], bool)
        assert isinstance(result["is_metallic"], bool)


def test_multi_has_no_representative_hex():
    assert normalise_colour("Multi")["colour_hex"] is None


def test_every_non_multi_colour_has_a_hex():
    for raw in COLOUR_MAP:
        if raw != "Multi":
            assert normalise_colour(raw)["colour_hex"].startswith("#")


@pytest.mark.parametrize("raw", ["Gold", "Silver", "Bronze", "Copper", "Metallic"])
def test_metallics_are_flagged(raw):
    assert normalise_colour(raw)["is_metallic"] is True


@pytest.mark.parametrize("raw", ["Black", "White", "Grey", "Beige", "Nude", "Skin"])
def test_neutrals_are_flagged(raw):
    assert normalise_colour(raw)["is_neutral"] is True


def test_saturated_colours_are_not_neutral():
    for raw in ["Red", "Pink", "Blue", "Green", "Purple", "Yellow", "Orange"]:
        assert normalise_colour(raw)["is_neutral"] is False


# --------------------------------------------------------------------------
# Category / domain
# --------------------------------------------------------------------------


def test_personal_care_maps_to_beauty():
    assert normalise_domain("Personal Care") == "beauty"


def test_every_article_type_maps_to_a_group():
    for raw in CATEGORY_GROUP_MAP:
        assert normalise_category_group(raw)


def test_colour_cosmetics_grouping():
    assert normalise_category_group("Lipstick") == "beauty_lip"
    assert normalise_category_group("Eyeshadow") == "beauty_eye"
    assert normalise_category_group("Highlighter and Blush") == "beauty_face"
    assert normalise_category_group("Nail Polish") == "beauty_nails"


def test_saree_is_an_anchor_not_a_complement():
    can_anchor, can_complement = product_roles(normalise_category_group("Sarees"))
    assert can_anchor is True
    assert can_complement is False


def test_lipstick_is_a_complement_not_an_anchor():
    can_anchor, can_complement = product_roles(normalise_category_group("Lipstick"))
    assert can_anchor is False
    assert can_complement is True


def _role(article_type):
    return classify_colour_role(article_type, normalise_category_group(article_type))


def test_style_colours_are_style():
    for article_type in ["Lipstick", "Nail Polish", "Eyeshadow", "Sarees", "Handbags"]:
        assert _role(article_type) == "style"


def test_foundation_colour_matches_skin_not_outfit():
    for article_type in ["Foundation and Primer", "Compact", "Concealer"]:
        assert _role(article_type) == "skin_match"


def test_container_colours_are_packaging():
    # "White" on a face wash or a perfume describes the bottle, not a look.
    for article_type in ["Face Wash and Cleanser", "Perfume and Body Mist", "Deodorant"]:
        assert _role(article_type) == "packaging"


def test_colour_is_meaningful_only_for_style():
    assert colour_is_meaningful("Lipstick", "beauty_lip") is True
    assert colour_is_meaningful("Foundation and Primer", "beauty_face") is False
    assert colour_is_meaningful("Face Wash and Cleanser", "beauty_skincare") is False


# --------------------------------------------------------------------------
# Occasion
# --------------------------------------------------------------------------


def test_occasion_reliability_depends_on_domain():
    _, reliable = normalise_occasion("Ethnic", "apparel")
    assert reliable is True
    # the source labels virtually all personal care "Casual"
    _, reliable = normalise_occasion("Casual", "beauty")
    assert reliable is False


def test_every_usage_value_maps():
    for raw in OCCASION_MAP:
        occasion, _ = normalise_occasion(raw, "apparel")
        assert occasion


# --------------------------------------------------------------------------
# Audience
# --------------------------------------------------------------------------


def test_kids_are_split_out_of_gender():
    assert normalise_audience("Girls") == ("women", "kids")
    assert normalise_audience("Women") == ("women", "adult")


def test_every_gender_value_maps():
    for raw in GENDER_MAP:
        gender, age = normalise_audience(raw)
        assert gender and age


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   ", "nan", "NULL", "-"])
def test_unusable_names_become_none(raw):
    assert clean_name(raw) is None


def test_whitespace_is_collapsed():
    assert clean_name("  Lakme   Absolute  Lipstick ") == "Lakme Absolute Lipstick"


def test_name_key_groups_identical_listings():
    a = name_key("Catwalk Women Black Heels", "Heels", "Black", "Women")
    b = name_key("catwalk women black heels", "Heels", "Black", "Women")
    assert a == b


# --------------------------------------------------------------------------
# Brand extraction
# --------------------------------------------------------------------------


def _lexicon(names):
    return build_brand_lexicon(names, min_support=2, multiword_ratio=0.6)


def test_brand_does_not_absorb_audience_token():
    names = ["Catwalk Women Black Heels"] * 5 + ["Catwalk Women Red Heels"] * 5
    assert extract_brand(names[0], _lexicon(names)) == "Catwalk"


def test_multiword_brand_is_kept_whole():
    names = ["Lino Perros Women Beige Handbag"] * 5 + ["Lino Perros Women Red Clutch"] * 5
    assert extract_brand(names[0], _lexicon(names)) == "Lino Perros"


def test_brand_matching_is_case_insensitive():
    names = ["United Colors of Benetton Men Blue Shirt"] * 6
    lex = _lexicon(names)
    assert extract_brand("United Colors Of Benetton Women Yellow Muffler", lex) == \
        "United Colors of Benetton"


def test_brand_starting_with_a_colour_word_survives():
    names = ["Red Tape Men Brown Formal Shoes"] * 5 + ["Red Tape Men Black Shoes"] * 5
    assert extract_brand(names[0], _lexicon(names)) == "Red Tape"


def test_unknown_brand_returns_none():
    lex = _lexicon(["Puma Men Grey Tshirt"] * 5)
    assert extract_brand("Obscure Label Women Blue Top", lex) is None


# --------------------------------------------------------------------------
# Finish
# --------------------------------------------------------------------------


def test_finish_parsed_only_for_beauty():
    assert parse_finish("Lakme Absolute Matte Merlot Lipstick", "beauty_lip") == "matte"
    assert parse_finish("Some Matte Finish Shirt", "topwear") is None


def test_finish_absent_when_not_stated():
    assert parse_finish("Revlon Lipstick 304", "beauty_lip") is None


# --------------------------------------------------------------------------
# Text blob
# --------------------------------------------------------------------------


def test_text_blob_includes_key_attributes():
    blob = build_text_blob(
        "Lakme Absolute Matte Merlot Lipstick 45", "Lakme", "Lipstick",
        "Maroon", "red", "casual", "women", "matte",
    )
    for fragment in ["Lakme", "Lipstick", "Maroon", "red colour", "matte finish"]:
        assert fragment in blob


def test_text_blob_skips_empty_parts():
    blob = build_text_blob("Puma Tshirt", None, "Tshirts", "Black", "black",
                           "casual", "men", None)
    assert "||" not in blob
    assert "finish" not in blob


# --------------------------------------------------------------------------
# Taxonomy integrity
# --------------------------------------------------------------------------


def test_domain_map_covers_all_master_categories():
    assert set(DOMAIN_MAP) == {
        "Apparel", "Accessories", "Footwear", "Personal Care",
        "Free Items", "Sporting Goods", "Home",
    }


def test_no_category_group_is_both_anchor_and_complement():
    from src.catalog.taxonomy import ANCHOR_GROUPS, COMPLEMENT_GROUPS
    assert not (ANCHOR_GROUPS & COMPLEMENT_GROUPS)
