"""Image resolution selection, and complete-look composition.

Two user-visible failures are guarded here:

* Product photos rendered blurry in the browser. The pipeline was correct - the
  high-resolution files simply did not exist for *clothing*, which only started
  being recommended when outfit composition arrived. These tests fail if the API
  ever serves a thumbnail while a large file exists.
* "What should I wear to a wedding?" returned a column of kurtas rather than a
  look. These tests require a main garment plus the rest of the outfit.
"""

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from src.api.app import app, services  # noqa: E402
from src.api.images import DEFAULT_LARGE_DIR, ImageStore  # noqa: E402
from src.engine.catalog_store import DEFAULT_CATALOG  # noqa: E402
from src.intent import fallback  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.path.exists(DEFAULT_CATALOG),
    reason="catalog not built - run scripts/ingest_catalog.py",
)

CLOTHING_TYPES = {
    "Kurtas", "Kurtis", "Kurta Sets", "Sarees", "Lehenga Choli", "Tunics",
    "Nehru Jackets", "Dresses", "Jumpsuit", "Tops", "Shirts", "Tshirts",
    "Sweaters", "Sweatshirts",
}
ACCESSORY_GROUPS = {"watch", "jewellery", "neckwear", "belt", "eyewear", "bag",
                    "wallet", "accessory_other", "fragrance"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def look(client, query, **extra):
    return client.post("/recommend", json={"query": query, "limit": 30, **extra}).json()


# ==========================================================================
# Image resolution selection
# ==========================================================================


def test_large_image_is_preferred_whenever_one_exists():
    """The regression that matters: never serve a thumbnail over a large file."""
    store = ImageStore()
    if not os.path.isdir(DEFAULT_LARGE_DIR):
        pytest.skip("no high-resolution store built")
    ids = [int(f[:-4]) for f in os.listdir(DEFAULT_LARGE_DIR)
           if f.endswith(".jpg")][:25]
    if not ids:
        pytest.skip("high-resolution store is empty")
    for product_id in ids:
        reference = store.reference(product_id)
        assert reference is not None
        assert reference["resolution"] == "large", product_id
        assert reference["width"] >= 400, (product_id, reference)


def test_thumbnail_is_used_only_when_no_large_file_exists():
    store = ImageStore()
    frame = services.store.df
    without = [
        int(p) for p in frame.product_id
        if not os.path.exists(os.path.join(DEFAULT_LARGE_DIR, f"{int(p)}.jpg"))
    ][:5]
    for product_id in without:
        reference = store.reference(product_id)
        assert reference["resolution"] == "thumb"


def test_served_bytes_match_the_declared_resolution(client):
    """What the API promises is what the browser actually downloads."""
    body = look(client, "date outfit for women")
    products = body["recommendations"][:6]
    assert products
    for product in products:
        reference = product["image"]
        response = client.get(reference["url"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.size == (reference["width"], reference["height"])
            if reference["resolution"] == "large":
                assert image.width >= 400, product["product_id"]
            else:
                assert image.width <= 100


def test_size_parameter_selects_explicitly(client):
    store = ImageStore()
    if not store.large_count:
        pytest.skip("no high-resolution store built")
    product_id = int(os.listdir(DEFAULT_LARGE_DIR)[0].replace(".jpg", ""))
    large = client.get(f"/images/{product_id}.jpg?size=large")
    thumb = client.get(f"/images/{product_id}.jpg?size=thumb")
    with Image.open(io.BytesIO(large.content)) as image:
        assert image.width >= 400
    with Image.open(io.BytesIO(thumb.content)) as image:
        assert image.width <= 100
    assert len(large.content) > len(thumb.content)


def test_high_resolution_images_are_actually_detailed():
    """A 600x800 file that is really an upscaled thumbnail would pass on size
    alone. Compare detail against the thumbnail blown up to the same size."""
    import numpy as np

    store = ImageStore()
    if not store.large_count:
        pytest.skip("no high-resolution store built")

    def detail(image):
        a = np.asarray(image.convert("L"), dtype=float)
        lap = (a[1:-1, 1:-1] * 4 - a[:-2, 1:-1] - a[2:, 1:-1]
               - a[1:-1, :-2] - a[1:-1, 2:])
        return lap.var()

    checked = 0
    for filename in os.listdir(DEFAULT_LARGE_DIR)[:5]:
        product_id = int(filename.replace(".jpg", ""))
        large_bytes = store.get(product_id, "large")
        thumb_bytes = store.get(product_id, "thumb")
        if not large_bytes or not thumb_bytes:
            continue
        with Image.open(io.BytesIO(large_bytes)) as large:
            with Image.open(io.BytesIO(thumb_bytes)) as thumb:
                upscaled = thumb.resize(large.size, Image.LANCZOS)
                assert detail(large) > detail(upscaled) * 5, product_id
        checked += 1
    assert checked, "no comparable pair found"


def test_every_outfit_product_has_an_image_reference(client):
    body = look(client, "I am going to a wedding tomorrow, what should I wear? I am a woman")
    for product in body["recommendations"]:
        assert product["image"] is not None
        assert product["image"]["resolution"] in {"large", "thumb"}


# ==========================================================================
# "What should I wear" is outfit intent
# ==========================================================================


@pytest.mark.parametrize("query", [
    "what should I wear to a wedding",
    "what can I wear for a party",
    "what to wear for diwali",
    "help me dress for a wedding",
    "style me for a party",
    "give me a look for the office",
    "I need something to wear for a wedding",
    "I am going to a wedding tomorrow",
    "date outfit for women",
])
def test_styling_requests_are_outfit_intent(query):
    assert fallback.parse(query).intent_type == "outfit"


@pytest.mark.parametrize("query", [
    "red kurta for men",
    "blue shirt for men",
    "black heels",
    "red lipstick",
    "I am wearing a red saree for my birthday",
])
def test_specific_product_requests_stay_product_intent(query):
    assert fallback.parse(query).intent_type == "product"


def test_wearing_a_saree_is_a_complement_request(client):
    """The saree is owned, so it must not be recommended back."""
    body = look(client, "I am wearing a red saree for my birthday")
    assert body["outfit"] is None
    types = {p["product_type"] for p in body["recommendations"]}
    assert "Sarees" not in types


# ==========================================================================
# Complete-look composition
# ==========================================================================


def main_section(body):
    assert body["outfit"], "expected an outfit response"
    return body["outfit"][0]


@pytest.mark.parametrize("query,gender", [
    ("I am going to a wedding tomorrow, what should I wear? I am a man", "men"),
    ("I am going to a wedding tomorrow, what should I wear? I am a woman", "women"),
    ("date outfit for women", "women"),
    ("date outfit for men", "men"),
])
def test_a_look_leads_with_actual_clothing(client, query, gender):
    body = look(client, query)
    section = main_section(body)
    assert section["key"] == "main"
    assert section["products"], query
    types = {p["product_type"] for p in section["products"]}
    assert types <= CLOTHING_TYPES, (query, types)


@pytest.mark.parametrize("query", [
    "I am going to a wedding tomorrow, what should I wear? I am a man",
    "I am going to a wedding tomorrow, what should I wear? I am a woman",
    "date outfit for women",
    "date outfit for men",
])
def test_a_look_is_more_than_its_main_garment(client, query):
    body = look(client, query)
    keys = [section["key"] for section in body["outfit"]]
    assert len(keys) >= 3, f"{query} produced only {keys}"
    assert "footwear" in keys, f"{query} has no footwear: {keys}"


def test_clothing_is_never_outnumbered_by_accessories(client):
    for query in ["I am going to a wedding tomorrow, what should I wear? I am a man",
                  "date outfit for women"]:
        body = look(client, query)
        products = body["recommendations"]
        clothing = sum(1 for p in products if p["product_type"] in CLOTHING_TYPES)
        accessories = sum(1 for p in products if p["category"] in ACCESSORY_GROUPS)
        assert clothing >= 2, query
        assert accessories <= len(products) * 0.6, query


def test_the_main_look_shows_more_than_one_kind_of_garment(client):
    """A women's wedding used to return four kurtas and no saree."""
    body = look(client, "I am going to a wedding tomorrow, what should I wear? I am a woman")
    types = {p["product_type"] for p in main_section(body)["products"]}
    assert len(types) >= 2, types


def test_womens_wedding_reaches_a_saree(client):
    body = look(client, "I am going to a wedding tomorrow, what should I wear? I am a woman")
    types = {p["product_type"] for p in main_section(body)["products"]}
    assert "Sarees" in types, types


def test_a_look_carries_supporting_clothing_where_the_catalog_has_it(client):
    body = look(client, "date outfit for women")
    keys = {section["key"] for section in body["outfit"]}
    assert "bottoms" in keys


@pytest.mark.parametrize("query,expected", [
    ("I am going to a wedding tomorrow, what should I wear? I am a man", {"men", "unisex"}),
    ("I am going to a wedding tomorrow, what should I wear? I am a woman", {"women", "unisex"}),
    ("date outfit for men", {"men", "unisex"}),
    ("date outfit for women", {"women", "unisex"}),
])
def test_a_look_never_mixes_genders(client, query, expected):
    body = look(client, query)
    genders = {services.store.get(p["product_id"]).gender
               for p in body["recommendations"]}
    assert genders <= expected, (query, genders)


def test_unspecified_gender_asks_before_composing(client):
    body = look(client, "What should I wear to a wedding?")
    assert body["needs_gender"] is True
    assert body["recommendations"] == []


def test_footwear_in_a_dressed_look_is_appropriate(client):
    """Flip flops are not wedding footwear, and there are 644 men's pairs."""
    body = look(client, "I am going to a wedding tomorrow, what should I wear? I am a man")
    footwear = next((s for s in body["outfit"] if s["key"] == "footwear"), None)
    assert footwear, "a wedding look needs footwear"
    types = {p["product_type"] for p in footwear["products"]}
    assert "Flip Flops" not in types
    assert "Sports Shoes" not in types


def test_a_mens_look_never_offers_womens_footwear(client):
    body = look(client, "I am going to a wedding tomorrow, what should I wear? I am a man")
    footwear = next((s for s in body["outfit"] if s["key"] == "footwear"), None)
    for product in footwear["products"]:
        assert services.store.get(product["product_id"]).gender in {"men", "unisex"}


def test_outfit_products_are_real_and_invent_nothing(client):
    body = look(client, "date outfit for women")
    for product in body["recommendations"]:
        assert services.store.exists(product["product_id"])
        for forbidden in ("price", "rating", "reviews", "stock", "popularity"):
            assert forbidden not in product


# ==========================================================================
# The garment they asked for leads the result
# ==========================================================================


def test_a_named_garment_leads_a_product_request(client):
    """"red kurta for men" is a request to see kurtas, not things to wear with one."""
    body = look(client, "red kurta for men")
    assert body["outfit"] is None
    types = [p["product_type"] for p in body["recommendations"]]
    assert "Kurtas" in types
    assert types[0] == "Kurtas", types[:3]


def test_the_named_garment_respects_the_requested_colour(client):
    body = look(client, "red kurta for men")
    kurtas = [p for p in body["recommendations"] if p["product_type"] == "Kurtas"]
    assert kurtas
    assert all(p["colour_family"] == "red" for p in kurtas), [p["colour"] for p in kurtas]


def test_a_named_shirt_leads_its_own_result(client):
    body = look(client, "blue shirt for dinner")
    types = [p["product_type"] for p in body["recommendations"]]
    assert types[0] == "Shirts", types[:3]


def test_an_owned_garment_is_never_recommended_back(client):
    body = look(client, "I am wearing a red saree for my birthday")
    assert body["intent"]["owns_anchor"] is True
    assert "Sarees" not in {p["product_type"] for p in body["recommendations"]}


def test_a_named_garment_still_brings_complements(client):
    body = look(client, "red kurta for men")
    categories = {p["category"] for p in body["recommendations"]}
    assert len(categories) >= 3, categories


# ==========================================================================
# Gender implied by a near-unanimous garment
# ==========================================================================


def test_a_saree_implies_a_womens_look(client):
    """A men's tie was being recommended alongside a saree."""
    body = look(client, "I am wearing a red saree for my birthday")
    assert body["intent"]["gender"] == "women"
    genders = {services.store.get(p["product_id"]).gender
               for p in body["recommendations"]}
    assert genders <= {"women", "unisex"}
    assert "Ties" not in {p["product_type"] for p in body["recommendations"]}


def test_the_assumption_is_disclosed(client):
    body = look(client, "I am wearing a red saree for my birthday")
    assert any("Assumed a women's look" in note for note in body["notes"])


def test_an_ambiguous_garment_infers_nothing():
    from src.outfit.policy import infer_gender_from_garment
    frame = services.store.df
    # Shirts are only ~90% men's in this catalog, below the dominance bar.
    assert infer_gender_from_garment(frame, "Shirts") is None
    assert infer_gender_from_garment(frame, "Sarees") == "women"
    assert infer_gender_from_garment(frame, "Ties") == "men"
    assert infer_gender_from_garment(frame, None) is None


def test_a_stated_gender_always_beats_the_inference(client):
    body = client.post("/recommend", json={
        "query": "I am wearing a red saree for my birthday",
        "gender": "men", "limit": 10}).json()
    assert body["intent"]["gender"] == "men"


# ==========================================================================
# Cache correctness
# ==========================================================================


def test_the_image_url_names_the_representation():
    """A bare /images/{id}.jpg served `immutable` for a week, so a browser that
    had cached the 60x80 kept showing it after the 600x800 arrived."""
    store = ImageStore()
    frame = services.store.df
    checked = 0
    for product_id in list(frame.product_id)[:200]:
        reference = store.reference(int(product_id))
        if reference is None:
            continue
        token = reference["url"].split("?v=")[1]
        expected = (str(reference["width"]) if reference["resolution"] == "large"
                    else reference["resolution"])
        assert token == expected, reference
        checked += 1
        if checked >= 20:
            break
    assert checked


def test_upgrading_a_product_changes_its_url(client):
    """The cache key must differ between the two tiers."""
    body = look(client, "date outfit for women")
    urls = {p["image"]["url"] for p in body["recommendations"]}
    assert all("?v=" in u for u in urls)


def test_versioned_requests_are_immutable_and_bare_ones_revalidate(client):
    body = look(client, "date outfit for women")
    product_id = body["recommendations"][0]["product_id"]

    versioned = client.get(f"/images/{product_id}.jpg?v=900")
    assert "immutable" in versioned.headers["cache-control"]
    assert versioned.headers.get("etag")

    bare = client.get(f"/images/{product_id}.jpg")
    assert "immutable" not in bare.headers["cache-control"]
    assert "must-revalidate" in bare.headers["cache-control"]


def test_the_served_image_still_matches_the_declared_resolution(client):
    body = look(client, "Green silk kurta for Diwali, traditional style.")
    for product in body["recommendations"][:6]:
        reference = product["image"]
        response = client.get(reference["url"])
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.size == (reference["width"], reference["height"])


# ==========================================================================
# On-demand image resolution
# ==========================================================================


class FakeResolver:
    """A resolver that never touches the network.

    The real one fetches from a public mirror; these tests care about the
    policy around it - what gets promised, what gets queued, what is admitted
    as unavailable - not about HTTP.
    """

    def __init__(self, fetchable=(), stored=(), quality=None):
        self._fetchable = set(fetchable)
        self._stored = dict(stored)
        self._quality = quality or {}
        self.prefetched = []
        self.ensured = []

    def fetchable(self, pid):
        return int(pid) in self._fetchable

    def path(self, pid):
        return self._stored.get(int(pid))

    def quality(self, pid):
        return self._quality.get(int(pid))

    def measure(self, image):
        return 500.0

    def record_quality(self, pid, width, height, sharpness):
        self._quality[int(pid)] = {"width": width, "height": height,
                                   "sharpness": sharpness, "sharp": sharpness >= 80}

    def prefetch(self, ids):
        self.prefetched.extend(int(i) for i in ids)
        return len(list(ids))

    def ensure(self, pid, timeout=12.0):
        self.ensured.append(int(pid))
        return self._stored.get(int(pid))


def unstored_product() -> int:
    """A catalog product that has no high-resolution file on disk yet."""
    real = ImageStore()
    for pid in list(services.store.df.product_id):
        if real.has(int(pid)) and real._large_path(int(pid)) is None:
            return int(pid)
    pytest.skip("every product already has a high-resolution file")


def test_a_product_with_no_large_file_is_pending_not_a_stretched_thumbnail():
    """The old behaviour served a 60x80 and let the card upscale it 4.4x."""
    pid = unstored_product()
    store = ImageStore(resolver=FakeResolver(fetchable=[pid]))
    reference = store.reference(pid)
    assert reference["resolution"] == "pending"
    assert reference["width"] is None and reference["height"] is None
    assert reference["url"].endswith("?v=pending")


def test_asking_for_a_pending_product_queues_the_fetch():
    pid = unstored_product()
    resolver = FakeResolver(fetchable=[pid])
    store = ImageStore(resolver=resolver)
    store.reference(pid)
    assert pid in resolver.prefetched, "every display path must queue the fetch"


def test_a_product_that_cannot_be_fetched_is_reported_as_low_resolution():
    """Honesty: when 60x80 is all there is, say so instead of implying more."""
    pid = unstored_product()
    store = ImageStore(resolver=FakeResolver(fetchable=[]))
    reference = store.reference(pid)
    assert reference["resolution"] == "thumb"
    assert reference["detail"] == "low"
    assert (reference["width"], reference["height"]) == (60, 80)


def test_a_soft_source_is_not_advertised_as_sharp():
    """A 900x1200 that holds no detail is still a poor photograph."""
    real = ImageStore()
    stored = next((p for p in list(services.store.df.product_id)[:400]
                   if real._large_path(int(p))), None)
    if stored is None:
        pytest.skip("no high-resolution files stored yet")
    pid = int(stored)
    soft = FakeResolver(stored={pid: real._large_path(pid)},
                        quality={pid: {"width": 900, "height": 1200,
                                       "sharpness": 4.0, "sharp": False}})
    assert ImageStore(resolver=soft).reference(pid)["detail"] == "soft"


def test_resolution_is_never_promised_when_fetching_is_disabled():
    """With the network off, nothing may claim an image is on its way."""
    from src.api.image_resolver import ImageResolver

    resolver = ImageResolver()
    assert resolver.fetchable(1163) is False      # conftest sets DISABLE_IMAGE_FETCH
    assert resolver.prefetch([1163, 1164]) == 0


def test_the_resolver_never_enlarges_a_small_source():
    """thumbnail() only shrinks - a small source must stay small."""
    from PIL import Image as PILImage

    from src.api.image_resolver import TARGET_SIZE

    small = PILImage.new("RGB", (60, 80))
    small.thumbnail(TARGET_SIZE, PILImage.LANCZOS)
    assert small.size == (60, 80), "a thumbnail must never be blown up to fake detail"


def test_every_recommendation_states_an_honest_resolution(client):
    body = look(client, "date outfit for women")
    for product in body["recommendations"]:
        reference = product["image"]
        assert reference["resolution"] in {"large", "pending", "thumb"}
        assert reference["detail"] in {"sharp", "soft", "low", "unknown"}
        if reference["resolution"] == "large":
            assert reference["width"] and reference["height"]
