"""Tests for the Phase 3 API and intent layer.

The Phase 1 and Phase 2 suites are untouched and must keep passing alongside
these.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app, services  # noqa: E402
from src.engine.catalog_store import DEFAULT_CATALOG  # noqa: E402
from src.intent import fallback  # noqa: E402
from src.intent.extractor import IntentExtractor  # noqa: E402
from src.intent.llm import IntentLLM, IntentLLMError  # noqa: E402
from src.intent.schema import ExtractedIntent, normalise, resolve_categories  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.path.exists(DEFAULT_CATALOG),
    reason="catalog not built - run scripts/ingest_catalog.py",
)

FLAGSHIP = "I'm wearing a black saree to a wedding. I want an elegant look."


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def known_groups():
    return services.store.available_complement_groups


# ==========================================================================
# 1. Health endpoint
# ==========================================================================


def test_health_reports_ready(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["engine_ready"] is True
    assert body["catalog_products"] == 43165
    assert body["images_available"] > 0
    assert "available" in body["llm"]


def test_health_discloses_llm_state(client):
    llm = client.get("/health").json()["llm"]
    # Whether or not credentials exist, the state must be stated, not implied.
    assert isinstance(llm["available"], bool)
    assert llm["state"] in {"available", "quota", "auth", "network", "timeout",
                            "unavailable", "not_configured"}
    assert llm["label"].startswith("AI Search")


def test_health_never_returns_the_providers_own_error_text(client):
    """`reason` can carry quota tables and request URLs - it stays server-side."""
    llm = client.get("/health").json()["llm"]
    assert "reason" not in llm
    assert not any("429" in str(v) or "RESOURCE_EXHAUSTED" in str(v)
                   for v in llm.values())


# ==========================================================================
# 2. Normal recommendation request
# ==========================================================================


def test_natural_language_request(client):
    response = client.post("/recommend", json={"query": FLAGSHIP, "limit": 10})
    assert response.status_code == 200
    body = response.json()

    assert body["query"] == FLAGSHIP
    assert body["intent"]["anchor_category"] == "ethnic_wear"
    assert body["intent"]["colour"] == "black"
    assert body["intent"]["occasion"] == "wedding"
    assert body["intent"]["style"] == "elegant"
    assert len(body["recommendations"]) >= 8


def test_recommendations_cross_categories(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 10}).json()
    categories = {r["category"] for r in body["recommendations"]}
    assert len(categories) >= 3
    assert categories & {"beauty_lip", "beauty_eye", "beauty_nails", "beauty_face"}
    assert categories & {"jewellery", "bag"}
    # never the anchor's own category
    assert "ethnic_wear" not in categories


def test_response_carries_category_context(client):
    body = client.post("/recommend", json={"query": FLAGSHIP}).json()
    assert body["categories"]
    for category in body["categories"]:
        assert category["why_considered"]
        assert category["confidence"] in {"strong", "moderate", "thin", "none"}


def test_score_breakdown_is_opt_in(client):
    plain = client.post("/recommend", json={"query": FLAGSHIP}).json()
    assert plain["recommendations"][0]["score_breakdown"] is None

    detailed = client.post(
        "/recommend", json={"query": FLAGSHIP, "include_score_breakdown": True}).json()
    breakdown = detailed["recommendations"][0]["score_breakdown"]
    assert breakdown and all(item["detail"] for item in breakdown)


# ==========================================================================
# 3. Structured request
# ==========================================================================


def test_structured_request_without_a_query(client):
    response = client.post("/recommend", json={
        "anchor_type": "saree", "colour": "black", "occasion": "wedding",
        "style": "elegant", "gender": "women", "limit": 8,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["query"] is None
    assert body["intent"]["source"] == "structured"
    assert body["recommendations"]


def test_structured_fields_override_the_parsed_query(client):
    body = client.post("/recommend", json={
        "query": "I'm wearing a black saree to a wedding",
        "colour": "red",                     # user corrected the colour in the UI
    }).json()
    assert body["intent"]["colour"] == "red"


def test_anchor_by_product_id(client):
    saree = services.store.df[
        (services.store.df.product_type == "Sarees")
        & (services.store.df.colour_family == "black")].iloc[0]
    response = client.post("/recommend", json={
        "product_id": int(saree.product_id), "occasion": "wedding", "limit": 6})
    assert response.status_code == 200
    body = response.json()
    assert body["anchor"]["source"] == "catalog_product"
    assert body["anchor"]["product_id"] == int(saree.product_id)
    assert body["anchor"]["colour_family"] == "black"
    assert body["anchor"]["image"] is not None


def test_excluded_categories_are_respected(client):
    body = client.post("/recommend", json={
        "query": FLAGSHIP, "exclude_categories": ["jewellery"], "limit": 10}).json()
    assert all(r["category"] != "jewellery" for r in body["recommendations"])


# ==========================================================================
# 4. Empty and invalid requests
# ==========================================================================


def test_empty_body_is_rejected_with_guidance(client):
    response = client.post("/recommend", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_request"
    assert "query" in body["detail"]


def test_blank_query_is_rejected(client):
    response = client.post("/recommend", json={"query": "   "})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_unknown_field_is_rejected(client):
    response = client.post("/recommend", json={"query": FLAGSHIP, "budget": 5000})
    assert response.status_code == 422


def test_out_of_range_limit_is_rejected(client):
    assert client.post("/recommend", json={"query": FLAGSHIP, "limit": 0}).status_code == 422
    assert client.post("/recommend", json={"query": FLAGSHIP, "limit": 500}).status_code == 422


def test_unintelligible_query_is_reported_not_guessed(client):
    response = client.post("/recommend", json={"query": "zzzz qqqq wubble"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["anchor_type"] is None
    assert any("Nothing usable" in note for note in body["notes"])


# ==========================================================================
# 5. LLM unavailable fallback
# ==========================================================================


def test_use_llm_false_forces_the_deterministic_parser(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "use_llm": False}).json()
    assert body["intent"]["source"] == "fallback"
    assert body["meta"]["intent_source"] == "fallback"
    assert body["recommendations"]


def test_fallback_produces_the_same_intent_as_the_flagship_expectation():
    intent = fallback.parse(FLAGSHIP)
    assert intent.anchor_type == "saree"
    assert intent.colour == "black"
    assert intent.occasion == "wedding"
    assert intent.style == "elegant"


def test_extractor_falls_back_when_the_llm_raises(known_groups):
    class Broken(IntentLLM):
        def __init__(self):
            self._client = object()
            self._open_until = 0.0
            self._consecutive_failures = 0
            self.model = "test"

        def extract(self, query):
            raise IntentLLMError("provider exploded")

    extractor = IntentExtractor(known_groups=known_groups, llm=Broken())
    intent, notes = extractor.extract(FLAGSHIP)
    assert intent.source == "fallback"
    assert intent.colour == "black"
    # The provider's own wording must never reach a note - it can carry quota
    # tables, request URLs and stack traces.
    assert not any("provider exploded" in note for note in notes)
    assert any("AI search" in note for note in notes)


def test_missing_credentials_do_not_break_the_service():
    llm = IntentLLM(api_key=None)
    status = llm.status
    assert isinstance(status["available"], bool)
    if not status["available"]:
        assert status["reason"]


def test_circuit_breaker_opens_after_repeated_failures():
    llm = IntentLLM.__new__(IntentLLM)
    llm._client = object()
    llm._consecutive_failures = 0
    llm._open_until = 0.0
    llm.model = "test"
    for _ in range(3):
        llm._record_failure()
    assert llm.available is False
    assert "circuit breaker" in llm.status["reason"]


# ==========================================================================
# 6. Invalid LLM response
# ==========================================================================


def test_llm_output_with_unknown_values_is_rejected_not_passed_through(known_groups):
    # A model that returns plausible-but-unsupported vocabulary must not be able
    # to smuggle it into the engine.
    hallucinated = ExtractedIntent(
        anchor_type="space suit",
        colour="ultraviolet",
        occasion="moon landing",
        style="interstellar",
        gender="robot",
        preferred_colours=["chartreuse-plaid"],
        include_categories=["teleporters"],
    )
    intent = normalise(hallucinated, known_groups, source="llm")
    assert intent.anchor_type is None
    assert intent.colour is None
    assert intent.occasion is None
    assert intent.style is None
    assert intent.gender is None
    assert intent.preferred_colours == ()
    assert intent.include_categories == ()
    assert len(intent.rejected) >= 6


def test_intent_schema_has_no_channel_for_a_product():
    # The structural guarantee: a hallucinated product has nowhere to go.
    fields = set(ExtractedIntent.model_fields)
    for forbidden in ("product_id", "product", "products", "name", "brand",
                      "price", "rating", "score", "image", "recommendations"):
        assert forbidden not in fields


def test_llm_cannot_add_extra_fields():
    with pytest.raises(Exception):
        ExtractedIntent(anchor_type="saree", product_id=12345)


def test_partially_valid_llm_output_keeps_the_good_parts(known_groups):
    intent = normalise(
        ExtractedIntent(anchor_type="saree", colour="black",
                        occasion="moon landing", include_categories=["makeup"]),
        known_groups, source="llm")
    assert intent.colour == "black"
    assert intent.anchor_category_group == "ethnic_wear"
    assert intent.occasion is None
    assert "beauty_lip" in intent.include_categories
    assert any("moon landing" in item for item in intent.rejected)


def test_category_phrases_resolve_to_taxonomy_groups(known_groups):
    resolved, rejected = resolve_categories(["makeup", "jewellery"], known_groups)
    assert "beauty_lip" in resolved and "jewellery" in resolved
    assert not rejected

    resolved, rejected = resolve_categories(["teleporters"], known_groups)
    assert resolved == ()
    assert rejected


# ==========================================================================
# 7. No-result requests
# ==========================================================================


def test_excluding_everything_returns_no_results_with_an_explanation(client):
    everything = sorted(services.store.available_complement_groups)
    response = client.post("/recommend", json={
        "query": FLAGSHIP, "exclude_categories": everything})
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"] == []
    assert body["notes"]


def test_unknown_product_id_returns_404_with_guidance(client):
    response = client.post("/recommend", json={"product_id": 999_999_999})
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "unknown_product"
    assert "not in the catalog" in body["error"]


def test_thin_category_is_disclosed(client):
    body = client.post("/recommend", json={
        "query": FLAGSHIP, "include_categories": ["headwear"], "limit": 5}).json()
    assert body["categories"]
    assert body["categories"][0]["category"] == "headwear"


# ==========================================================================
# 8. Real product ids
# ==========================================================================


def test_every_returned_product_exists_in_the_catalog(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 12}).json()
    assert body["recommendations"]
    for rec in body["recommendations"]:
        assert services.store.exists(rec["product_id"])


def test_returned_fields_match_the_catalog_row(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 6}).json()
    for rec in body["recommendations"]:
        row = services.store.get(rec["product_id"])
        assert rec["name"] == row["name"]
        assert rec["category"] == row.category_group
        assert rec["colour"] == row.base_colour
        assert rec["colour_family"] == row.colour_family
        assert rec["product_type"] == row.product_type


def test_no_price_or_rating_is_invented(client):
    body = client.post("/recommend", json={"query": FLAGSHIP}).json()
    for rec in body["recommendations"]:
        for forbidden in ("price", "mrp", "discount", "rating", "reviews", "popularity"):
            assert forbidden not in rec


def test_product_endpoint_returns_a_real_row(client):
    product_id = int(services.store.df.iloc[0].product_id)
    body = client.get(f"/products/{product_id}").json()
    assert body["product_id"] == product_id
    assert body["name"]


def test_product_endpoint_404s_on_an_unknown_id(client):
    response = client.get("/products/999999999")
    assert response.status_code == 404
    assert response.json()["code"] == "unknown_product"


# ==========================================================================
# 9. Image references
# ==========================================================================


def test_every_recommendation_carries_an_image_reference(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 10}).json()
    for rec in body["recommendations"]:
        image = rec["image"]
        assert image is not None
        # The URL carries the representation, so upgrading a product from a
        # thumbnail to a high-resolution file changes its cache key.
        assert image["url"].startswith(f"/images/{rec['product_id']}.jpg?v=")
        # The token names the resolution actually stored, so an upgrade from
        # 600x800 to 900x1200 changes the cache key.
        token = image["url"].split("?v=")[1]
        if image["resolution"] == "large":
            assert token == str(image["width"])
        else:
            assert token in {"pending", "thumb"}
        assert image["width"] > 0 and image["height"] > 0
        assert image["media_type"] == "image/jpeg"


def test_image_endpoint_serves_real_jpeg_bytes(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 3}).json()
    url = body["recommendations"][0]["image"]["url"]
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"          # JPEG SOI marker
    assert len(response.content) > 200


def test_image_endpoint_is_cacheable(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 3}).json()
    response = client.get(body["recommendations"][0]["image"]["url"])
    assert "max-age" in response.headers.get("cache-control", "")


def test_image_endpoint_404s_for_an_unknown_product(client):
    response = client.get("/images/999999999.jpg")
    assert response.status_code == 404
    assert response.json()["code"] == "image_not_found"


# ==========================================================================
# 10. Explanations
# ==========================================================================


def test_every_recommendation_has_reasons(client):
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 10}).json()
    for rec in body["recommendations"]:
        assert rec["reasons"]
        assert all(isinstance(reason, str) and reason for reason in rec["reasons"])


def test_reasons_read_as_sentences_not_scores(client):
    """A card explains itself in words; the numbers stay in the breakdown."""
    body = client.post("/recommend", json={"query": FLAGSHIP, "limit": 10}).json()
    for rec in body["recommendations"]:
        for reason in rec["reasons"]:
            assert reason[0].isupper(), reason
            assert reason.endswith("."), reason
            # no weights, raw scores, component names or parser internals
            for leak in ("0.", "1.0", "=", "(base", "Colour:", "Occasion:",
                         "Category:", "colour_harmony", "occasion_suitability"):
                assert leak not in reason, f"{leak!r} leaked into {reason!r}"


def test_reasons_still_come_from_real_signals(client):
    """Explanations are built from scored components, never invented."""
    body = client.post("/recommend", json={
        "query": FLAGSHIP, "include_score_breakdown": True, "limit": 10}).json()
    for rec in body["recommendations"]:
        assert rec["reasons"], rec["name"]
        assert rec["score_breakdown"], "a reason must have a component behind it"


def test_breakdown_contributions_reproduce_the_score(client):
    body = client.post("/recommend", json={
        "query": FLAGSHIP, "include_score_breakdown": True, "limit": 5}).json()
    for rec in body["recommendations"]:
        breakdown = rec["score_breakdown"]
        total_weight = sum(item["weight"] for item in breakdown)
        expected = sum(item["contribution"] for item in breakdown) / total_weight
        assert abs(expected - rec["score"]) < 0.01


# ==========================================================================
# Misc: determinism, categories endpoint, docs
# ==========================================================================


def test_identical_requests_return_identical_products(client):
    payload = {"query": FLAGSHIP, "limit": 10, "use_llm": False}
    first = [r["product_id"] for r in client.post("/recommend", json=payload).json()["recommendations"]]
    second = [r["product_id"] for r in client.post("/recommend", json=payload).json()["recommendations"]]
    assert first == second


def test_categories_endpoint_explains_affinity(client):
    body = client.get("/categories", params={
        "anchor_category": "ethnic_wear", "occasion": "wedding"}).json()
    assert body["occasion"] == "wedding"
    assert body["categories"]
    assert all(item["why"] for item in body["categories"])
    scores = [item["affinity"] for item in body["categories"]]
    assert scores == sorted(scores, reverse=True)


def test_openapi_schema_is_served(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/recommend" in response.json()["paths"]


# ==========================================================================
# Provider failures are classified, never leaked
# ==========================================================================


@pytest.mark.parametrize("error,expected", [
    ("ClientError: 429 RESOURCE_EXHAUSTED. You exceeded your current quota", "quota"),
    ("rate limit reached for this model", "quota"),
    ("401 Unauthorized: invalid API key provided", "auth"),
    ("PermissionDenied: the caller does not have permission", "auth"),
    ("Read timed out after 30s", "timeout"),
    ("Connection refused to generativelanguage.googleapis.com", "network"),
    ("no Anthropic credentials found - set ANTHROPIC_API_KEY", "not_configured"),
    ("something nobody predicted", "unavailable"),
])
def test_provider_errors_are_classified(error, expected):
    from src.intent.llm import classify_failure

    assert classify_failure(error) == expected


def test_a_quota_failure_never_reaches_the_user(known_groups):
    """The exact string the user saw on the results page."""
    from src.intent.llm import IntentLLMError

    raw = ("ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, "
           "'message': 'You exceeded your current quota', "
           "'status': 'RESOURCE_EXHAUSTED'}}")

    class OutOfQuota:
        available = True
        status = {"state": "quota", "reason": raw}
        model = "test"

        def extract(self, query):
            raise IntentLLMError(raw, "quota")

    _, notes = IntentExtractor(known_groups=known_groups, llm=OutOfQuota()).extract(
        "red shirt for men for office")
    joined = " ".join(notes)
    for leak in ("429", "RESOURCE_EXHAUSTED", "quota", "ClientError", "googleapis"):
        assert leak not in joined, f"{leak!r} leaked into a user-facing note"
    assert "AI search is temporarily unavailable" in joined


def test_the_status_label_reflects_the_real_state():
    from src.intent.llm import STATUS_LABELS

    assert STATUS_LABELS["available"] == "AI Search Available"
    assert STATUS_LABELS["quota"] == "AI Search Temporarily Unavailable"
    assert STATUS_LABELS["auth"] == "AI Search Configuration Error"
