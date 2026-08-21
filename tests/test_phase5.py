"""Tests for the Phase 5 additions: provider abstraction, vocabulary, browse.

The Phase 1-4 suites are untouched and must keep passing alongside these.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app, services  # noqa: E402
from src.engine.catalog_store import DEFAULT_CATALOG  # noqa: E402
from src.engine.occasion import normalise_occasion  # noqa: E402
from src.intent import fallback  # noqa: E402
from src.intent.llm import IntentLLM  # noqa: E402
from src.intent.providers import (  # noqa: E402
    PROVIDERS,
    SYSTEM_PROMPT,
    AnthropicProvider,
    GeminiProvider,
    ProviderError,
    build_provider,
    detect_provider_name,
)

pytestmark = pytest.mark.skipif(
    not os.path.exists(DEFAULT_CATALOG),
    reason="catalog not built - run scripts/ingest_catalog.py",
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                 "LLM_PROVIDER", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# ==========================================================================
# Provider abstraction
# ==========================================================================


def test_anthropic_is_the_default_provider(clean_env):
    assert detect_provider_name() == "anthropic"


def test_google_key_selects_gemini(clean_env):
    clean_env.setenv("GEMINI_API_KEY", "test-key")
    assert detect_provider_name() == "gemini"


def test_google_api_key_also_selects_gemini(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "test-key")
    assert detect_provider_name() == "gemini"


def test_anthropic_wins_when_both_keys_are_set(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "a")
    clean_env.setenv("GEMINI_API_KEY", "b")
    assert detect_provider_name() == "anthropic"


def test_provider_can_be_forced(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "a")
    clean_env.setenv("LLM_PROVIDER", "gemini")
    assert detect_provider_name() == "gemini"


def test_llm_can_be_disabled_entirely(clean_env):
    clean_env.setenv("LLM_PROVIDER", "none")
    assert detect_provider_name() is None
    with pytest.raises(ProviderError):
        build_provider()


def test_unknown_provider_is_rejected(clean_env):
    clean_env.setenv("LLM_PROVIDER", "some-other-llm")
    with pytest.raises(ProviderError) as excinfo:
        build_provider()
    assert "unknown LLM_PROVIDER" in str(excinfo.value)


def test_every_provider_shares_the_same_contract():
    for factory in PROVIDERS.values():
        assert hasattr(factory, "name") and hasattr(factory, "default_model")
        assert callable(getattr(factory, "extract"))


def test_missing_credentials_degrade_rather_than_raise(clean_env):
    llm = IntentLLM()
    assert llm.available is False
    status = llm.status
    assert status["reason"]
    # The model a provider *would* use is still reported, so the UI can name it.
    assert status["model"]
    assert status["provider"] in PROVIDERS


def test_gemini_without_a_key_reports_clearly(clean_env):
    clean_env.setenv("LLM_PROVIDER", "gemini")
    llm = IntentLLM()
    assert llm.available is False
    assert "GEMINI_API_KEY" in llm.status["reason"] or "google-genai" in llm.status["reason"]


def test_system_prompt_forbids_product_invention():
    lowered = SYSTEM_PROMPT.lower()
    assert "never output a product" in lowered
    assert "you do not recommend" in lowered
    # The prompt must constrain occasion to the engine's own vocabulary.
    for occasion in ("wedding", "festive", "party", "formal", "office", "casual", "sports"):
        assert occasion in lowered


def test_providers_are_not_referenced_by_the_engine():
    """The engine must not import the LLM layer - swapping provider cannot
    change what gets recommended."""
    import pathlib

    engine_dir = pathlib.Path(__file__).parent.parent / "src" / "engine"
    for path in engine_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "intent" not in source.replace("intent extraction", ""), path.name


# ==========================================================================
# Vocabulary additions
# ==========================================================================


def test_dinner_maps_to_an_existing_occasion():
    # The catalog has no "dinner" occasion; it maps onto the nearest supported
    # equivalent rather than inventing one.
    assert normalise_occasion("dinner") == "party"
    assert normalise_occasion("date night") == "party"


def test_sporty_and_active_map_to_sports():
    assert normalise_occasion("sporty") == "sports"
    assert normalise_occasion("active") == "sports"


def test_new_synonyms_do_not_disturb_existing_ones():
    assert normalise_occasion("wedding") == "wedding"
    assert normalise_occasion("diwali") == "festive"
    assert normalise_occasion("gym") == "sports"
    assert normalise_occasion("brunch") == "casual"


def test_unmapped_occasion_is_still_reported_not_forced():
    assert normalise_occasion("moon landing") is None


def test_blue_shirt_for_dinner_parses_end_to_end():
    intent = fallback.parse("Blue shirt for dinner.")
    assert intent.anchor_type == "shirt"
    assert intent.colour == "blue"
    assert normalise_occasion(intent.occasion) == "party"


def test_sporty_query_parses_to_sports():
    intent = fallback.parse("Something sporty for an active day")
    assert normalise_occasion(intent.occasion) == "sports"


# ==========================================================================
# Browse endpoint
# ==========================================================================


def test_browse_returns_real_catalog_products(client):
    body = client.get("/catalog/browse", params={"limit": 5}).json()
    assert body["total"] > 0
    assert len(body["products"]) == 5
    for product in body["products"]:
        assert services.store.exists(product["product_id"])
        row = services.store.get(product["product_id"])
        assert product["name"] == row["name"]
        assert product["colour"] == row.base_colour


def test_browse_never_invents_commerce_fields(client):
    body = client.get("/catalog/browse", params={"limit": 8}).json()
    for product in body["products"]:
        for forbidden in ("price", "mrp", "rating", "reviews", "popularity", "stock"):
            assert forbidden not in product


def test_browse_carries_no_score(client):
    # Browse performs no scoring; a score here would imply a ranking that does
    # not exist.
    body = client.get("/catalog/browse", params={"limit": 5}).json()
    assert all("score" not in p for p in body["products"])


def test_browse_filters_by_domain(client):
    body = client.get("/catalog/browse", params={"domain": "beauty", "limit": 10}).json()
    for product in body["products"]:
        assert services.store.get(product["product_id"]).domain == "beauty"


def test_browse_filters_by_colour(client):
    body = client.get("/catalog/browse", params={"colour": "red", "limit": 10}).json()
    assert body["products"]
    for product in body["products"]:
        assert product["colour_family"] == "red"


def test_browse_anchors_only_returns_anchor_garments(client):
    body = client.get("/catalog/browse", params={"anchors_only": "true", "limit": 10}).json()
    for product in body["products"]:
        assert product["can_be_anchor"] is True


def test_browse_rejects_an_unknown_domain(client):
    assert client.get("/catalog/browse", params={"domain": "spacecraft"}).status_code == 422


def test_browse_paging_is_stable(client):
    first = client.get("/catalog/browse", params={"limit": 6, "offset": 0}).json()["products"]
    again = client.get("/catalog/browse", params={"limit": 6, "offset": 0}).json()["products"]
    later = client.get("/catalog/browse", params={"limit": 6, "offset": 6}).json()["products"]
    assert [p["product_id"] for p in first] == [p["product_id"] for p in again]
    assert not ({p["product_id"] for p in first} & {p["product_id"] for p in later})


def test_browse_products_carry_image_references(client):
    body = client.get("/catalog/browse", params={"limit": 8}).json()
    for product in body["products"]:
        assert product["image"] is not None
        assert product["image"]["resolution"] in {"large", "thumb"}


def test_browse_prefers_high_resolution_first(client):
    body = client.get("/catalog/browse", params={"limit": 24}).json()
    resolutions = [p["image"]["resolution"] for p in body["products"]]
    # Once a thumbnail appears, no large image may follow it.
    if "large" in resolutions and "thumb" in resolutions:
        assert resolutions.index("thumb") > max(
            i for i, r in enumerate(resolutions) if r == "large")


# ==========================================================================
# Anchoring a look on a browsed product
# ==========================================================================


def test_a_browsed_anchor_can_drive_a_recommendation(client):
    anchor = client.get(
        "/catalog/browse", params={"anchors_only": "true", "colour": "black", "limit": 1}
    ).json()["products"][0]

    response = client.post("/recommend", json={
        "product_id": anchor["product_id"], "occasion": "wedding", "limit": 8})
    assert response.status_code == 200
    body = response.json()
    assert body["anchor"]["product_id"] == anchor["product_id"]
    assert body["anchor"]["source"] == "catalog_product"
    assert body["recommendations"]
    # never recommend the anchor's own category back to it
    assert all(r["category"] != body["anchor"]["category"] for r in body["recommendations"])


def test_health_reports_the_provider(client):
    llm = client.get("/health").json()["llm"]
    assert "provider" in llm
    assert "model" in llm
    assert isinstance(llm["available"], bool)


def test_health_reports_high_resolution_count(client):
    body = client.get("/health").json()
    assert body["images_high_resolution"] >= 0
    assert body["images_high_resolution"] <= body["images_available"]
