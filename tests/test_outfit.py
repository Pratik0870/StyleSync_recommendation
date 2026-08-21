"""Outfit intent, gender as a hard constraint, and outfit composition.

The failure these guard against is concrete: "I am going for wedding tomorrow
with red kurta man" used to return sandals, a tie, a bracelet, a laptop bag and
a lunch bag — no kurta, no bottoms.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app, services  # noqa: E402
from src.engine.catalog_store import DEFAULT_CATALOG  # noqa: E402
from src.intent import fallback  # noqa: E402
from src.intent.schema import ExtractedIntent, normalise  # noqa: E402
from src.outfit.policy import requires_gender, sections_for  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.path.exists(DEFAULT_CATALOG),
    reason="catalog not built - run scripts/ingest_catalog.py",
)

PROBLEM_QUERY = "I am going for wedding tomorrow with red kurta man"

WOMENS_ONLY_TYPES = {"Sarees", "Kurtis", "Lehenga Choli", "Patiala", "Heels",
                     "Lipstick", "Nail Polish", "Clutches"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def genders_of(products):
    return {services.store.get(p["product_id"]).gender for p in products}


# ==========================================================================
# Outfit vs product intent
# ==========================================================================


@pytest.mark.parametrize("query", [
    "I need an outfit for a wedding",
    "I am going to a wedding tomorrow",
    "Help me dress for a wedding",
    "I need a complete look for a wedding",
    "Suggest an outfit for Diwali",
    "what should I wear to a wedding",
    PROBLEM_QUERY,
])
def test_outfit_requests_are_detected(query):
    assert fallback.parse(query).intent_type == "outfit"


@pytest.mark.parametrize("query", [
    "red kurta for wedding",
    "blue shirt for office",
    "black heels for party",
    "red lipstick for wedding",
    "navy blue shirt for the office, men",
    "red shirt for party",
])
def test_product_requests_are_not_promoted_to_outfits(query):
    assert fallback.parse(query).intent_type == "product"


def test_owning_the_garment_means_complements_not_a_new_outfit():
    # The product's core promise: you have the saree, you want what goes with it.
    for query in ["I'm wearing a black saree to a wedding. I want an elegant look.",
                  "I have a pink dress for a party. Suggest makeup and accessories."]:
        assert fallback.parse(query).intent_type == "product"


def test_time_context_is_captured_but_carries_no_promise():
    assert fallback.parse(PROBLEM_QUERY).time_context == "tomorrow"
    assert fallback.parse("I need an outfit tonight").time_context == "tonight"


def test_unknown_intent_type_from_a_model_falls_back_to_product():
    known = services.store.available_complement_groups
    intent = normalise(ExtractedIntent(intent_type="shopping_spree"), known, "llm")
    assert intent.intent_type == "product"
    assert any("intent type" in item for item in intent.rejected)


# ==========================================================================
# Gender extraction and hard constraint
# ==========================================================================


@pytest.mark.parametrize("query,expected", [
    ("I am going for wedding tomorrow with red kurta man", "men"),
    ("I need a men's outfit for a wedding", "men"),
    ("outfit for him", "men"),
    ("I'm a man, what should I wear", "men"),
    ("mens wedding outfit", "men"),
    ("I need a women's outfit for a wedding", "women"),
    ("outfit for her", "women"),
    ("ladies outfit for a wedding", "women"),
    ("female wedding outfit", "women"),
])
def test_gender_is_extracted_wherever_it_appears(query, expected):
    assert fallback.parse(query).gender == expected


def test_gender_absent_is_reported_not_guessed():
    assert fallback.parse("I need an outfit for a wedding").gender is None


def test_normalised_intent_records_whether_gender_was_stated():
    known = services.store.available_complement_groups
    stated = normalise(ExtractedIntent(gender="men"), known, "llm")
    unstated = normalise(ExtractedIntent(), known, "llm")
    assert stated.gender_explicit is True
    assert unstated.gender_explicit is False


def test_mens_outfit_contains_no_womens_products(client):
    body = client.post("/recommend", json={
        "query": "I need a men's outfit for a wedding", "limit": 30}).json()
    assert body["recommendations"], "a men's wedding outfit should be buildable"
    assert genders_of(body["recommendations"]) <= {"men", "unisex"}


def test_womens_outfit_contains_no_mens_products(client):
    body = client.post("/recommend", json={
        "query": "I need a women's outfit for a wedding", "limit": 30}).json()
    assert body["recommendations"]
    assert genders_of(body["recommendations"]) <= {"women", "unisex"}


def test_the_original_failing_query_is_mens_only(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    assert body["recommendations"]
    assert genders_of(body["recommendations"]) <= {"men", "unisex"}
    names = " ".join(p["name"].lower() for p in body["recommendations"])
    for leak in ("women", "girls", "lipstick", "heels", "saree", "kurti"):
        assert leak not in names, f"'{leak}' leaked into a men's outfit"


def test_gender_is_hard_on_product_requests_too(client):
    body = client.post("/recommend", json={
        "query": "navy blue shirt for the office, men", "limit": 20}).json()
    assert genders_of(body["recommendations"]) <= {"men", "unisex"}


def test_explicit_gender_overrides_a_query_without_one(client):
    body = client.post("/recommend", json={
        "query": "I need an outfit for a wedding", "gender": "men", "limit": 20}).json()
    assert body["needs_gender"] is False
    assert genders_of(body["recommendations"]) <= {"men", "unisex"}


# ==========================================================================
# Unspecified gender on an outfit
# ==========================================================================


def test_outfit_without_gender_asks_rather_than_mixing(client):
    body = client.post("/recommend", json={
        "query": "I need an outfit for a wedding tomorrow", "limit": 20}).json()
    assert body["needs_gender"] is True
    assert body["recommendations"] == []
    assert body["outfit"] is None
    assert any("men's or women's" in note for note in body["notes"])


def test_policy_knows_when_gender_is_required():
    assert requires_gender(None) is True
    assert requires_gender("unisex") is True
    assert requires_gender("men") is False
    assert requires_gender("women") is False


def test_a_product_request_without_gender_still_answers(client):
    body = client.post("/recommend", json={"query": "red kurta for a wedding"}).json()
    assert body["needs_gender"] is False
    assert body["recommendations"]


# ==========================================================================
# Outfit composition
# ==========================================================================


def test_mens_wedding_outfit_has_a_coherent_shape(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    outfit = body["outfit"]
    assert outfit, "an outfit request must return outfit sections"

    keys = [section["key"] for section in outfit]
    assert keys[0] == "main", "the main garment comes first"
    assert "footwear" in keys

    main = outfit[0]
    assert main["products"], "a look needs a main garment"
    types = {p["product_type"] for p in main["products"]}
    assert types <= {"Kurtas", "Nehru Jackets", "Kurta Sets"}, types


def test_accessories_do_not_dominate_an_outfit(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    products = body["recommendations"]
    accessory_like = {"watch", "jewellery", "neckwear", "belt", "eyewear", "bag",
                      "wallet", "accessory_other"}
    share = sum(1 for p in products if p["category"] in accessory_like) / len(products)
    assert share < 0.5, f"accessories were {share:.0%} of the look"


def test_the_original_failure_products_are_gone(client):
    """A laptop bag and a lunch bag were being recommended for a wedding."""
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    names = " ".join(p["name"].lower() for p in body["recommendations"])
    for wrong in ("laptop", "lunch bag", "backpack", "trolley"):
        assert wrong not in names


def test_requested_colour_applies_to_the_main_garment(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    main = body["outfit"][0]
    # red kurta was asked for; the red family covers red/maroon/burgundy
    assert all(p["colour_family"] == "red" for p in main["products"]), \
        [p["colour"] for p in main["products"]]


def test_womens_wedding_outfit_includes_its_own_categories(client):
    body = client.post("/recommend", json={
        "query": "I need a women's outfit for a wedding", "limit": 30}).json()
    keys = {section["key"] for section in body["outfit"]}
    assert "main" in keys and "footwear" in keys
    assert keys & {"jewellery", "beauty"}, "a women's look should reach beauty or jewellery"


def test_outfit_sections_only_appear_when_they_have_products(client):
    body = client.post("/recommend", json={
        "query": "I need a men's outfit for a wedding", "limit": 30}).json()
    assert all(section["products"] for section in body["outfit"])


def test_outfit_products_are_real_catalog_items(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    for product in body["recommendations"]:
        assert services.store.exists(product["product_id"])
        row = services.store.get(product["product_id"])
        assert product["name"] == row["name"]


def test_outfit_products_invent_no_commerce_fields(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    for product in body["recommendations"]:
        for forbidden in ("price", "mrp", "rating", "reviews", "popularity", "stock"):
            assert forbidden not in product


def test_outfit_products_carry_reasons_and_images(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    for product in body["recommendations"]:
        assert product["reasons"]
        assert product["image"] is not None


def test_thin_sections_are_disclosed_not_padded(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 30}).json()
    for section in body["outfit"]:
        if section["confidence"] == "thin":
            assert section["note"], "a thin section must say so"


def test_time_context_makes_no_availability_claim(client):
    body = client.post("/recommend", json={"query": PROBLEM_QUERY, "limit": 20}).json()
    notes = " ".join(body["notes"]).lower()
    assert "tomorrow" in notes
    assert "no stock or delivery" in notes
    for promise in ("in stock", "delivered", "arrives", "available tomorrow"):
        assert promise not in notes


def test_policy_only_names_categories_that_exist():
    available = set(services.store.df.category_group.unique())
    for gender in ("men", "women"):
        for anchor in ("ethnic_wear", None):
            for section in sections_for(gender, "wedding", anchor):
                assert set(section.groups) <= available, section.groups


def test_product_requests_still_use_the_complement_path(client):
    body = client.post("/recommend", json={
        "query": "red kurta for a wedding", "limit": 12}).json()
    assert body["outfit"] is None
    assert body["categories"], "a product request keeps the category view"


# ==========================================================================
# Search relevance: the requested item comes first
# ==========================================================================

ACCESSORY_CATEGORIES = {"watch", "jewellery", "neckwear", "belt", "eyewear", "bag",
                        "wallet", "accessory_other", "fragrance", "beauty_lip",
                        "beauty_face", "beauty_eye", "beauty_nail", "socks"}


@pytest.mark.parametrize("query,gender,product_type", [
    ("red shirt for men for office", "men", "Shirts"),
    ("red shirt for women for office", "women", "Shirts"),
    ("black trousers for men", "men", "Trousers"),
])
def test_the_requested_garment_leads_the_results(client, query, gender, product_type):
    """A tie, a perfume or a handbag must never come before the shirt."""
    body = client.post("/recommend", json={"query": query, "limit": 18}).json()
    products = body["recommendations"]
    assert products, query
    assert products[0]["product_type"] == product_type, products[0]["name"]
    lead = [p for p in products if p["product_type"] == product_type]
    first_accessory = next((i for i, p in enumerate(products)
                            if p["category"] in ACCESSORY_CATEGORIES), len(products))
    assert first_accessory >= len(lead), "an accessory outranked the requested garment"
    assert genders_of(products) <= {gender, "unisex"}


def test_the_requested_garment_outscores_the_accessories(client):
    body = client.post("/recommend", json={
        "query": "red shirt for men for office", "limit": 18}).json()
    products = body["recommendations"]
    best_shirt = max(p["score"] for p in products if p["product_type"] == "Shirts")
    for product in products:
        if product["category"] in ACCESSORY_CATEGORIES:
            assert product["score"] <= best_shirt, product["name"]


def test_an_exact_colour_match_beats_a_near_one(client):
    body = client.post("/recommend", json={
        "query": "red shirt for men for office", "limit": 18}).json()
    shirts = [p for p in body["recommendations"] if p["product_type"] == "Shirts"]
    exact = [p["score"] for p in shirts if p["colour_family"] == "red"]
    other = [p["score"] for p in shirts if p["colour_family"] != "red"]
    if exact and other:
        assert min(exact) >= max(other)


def test_a_request_naming_no_garment_builds_a_look(client):
    """"office wear for women" used to answer with heels, a bag and a lipstick."""
    body = client.post("/recommend", json={
        "query": "office wear for women", "gender": "women", "limit": 18}).json()
    assert body["outfit"], "a request with no named item should build a look"
    assert body["outfit"][0]["key"] == "main"
    assert body["outfit"][0]["products"], "a look needs a main garment"


def test_naming_a_product_still_uses_the_product_path(client):
    """The routing rule must not swallow real product requests."""
    body = client.post("/recommend", json={
        "query": "red lipstick for a wedding", "limit": 12}).json()
    assert body["outfit"] is None
    assert body["recommendations"]


def test_a_formal_look_offers_no_tshirts_or_jeans(client):
    """The catalog labels a novelty T-shirt "formal"; the look must not."""
    body = client.post("/recommend", json={
        "query": "formal outfit for men", "gender": "men", "limit": 20}).json()
    types = {p["product_type"] for section in body["outfit"]
             for p in section["products"]}
    assert not types & {"Tshirts", "Sweatshirts", "Shorts", "Jeans"}, types


def test_a_casual_look_still_offers_casual_garments(client):
    """The dressy rule must not leak into casual requests."""
    body = client.post("/recommend", json={
        "query": "something casual for the weekend", "gender": "men",
        "limit": 20}).json()
    types = {p["product_type"] for section in body["outfit"]
             for p in section["products"]}
    assert types & {"Tshirts", "Jeans", "Casual Shoes", "Sweatshirts", "Shorts"}, types
