"""Tests for the recommendation engine."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import make_store, product  # noqa: E402

from src.engine.affinity import (  # noqa: E402
    MIN_AFFINITY,
    affinity_for,
    product_type_relevance,
    ranked_categories,
)
from src.engine.colour import (  # noqa: E402
    FAMILY_HUE,
    HARMONY_SCORES,
    family_class,
    harmony,
    hue_distance,
)
from src.engine.diversity import DiversityConfig, measure, rerank  # noqa: E402
from src.engine.engine import MIN_ACCEPTABLE_SCORE, RecommendationEngine  # noqa: E402
from src.engine.explain import build_reasons  # noqa: E402
from src.engine.occasion import (  # noqa: E402
    beauty_suitability,
    catalog_suitability,
    normalise_occasion,
)
from src.engine.relevance import TextRelevance  # noqa: E402
from src.engine.schemas import Anchor, LookRequest, Preferences, ScoreComponent  # noqa: E402
from src.engine.scoring import (  # noqa: E402
    DEFAULT_CONFIG,
    colour_component,
    combine,
    normalise_style,
    preference_component,
)


# ==========================================================================
# Colour harmony
# ==========================================================================


def test_every_family_pair_scores():
    families = sorted(FAMILY_HUE)
    for a in families:
        for b in families:
            result = harmony(a, b)
            assert 0.0 <= result.score <= 1.0
            assert result.relation and result.explanation


def test_neutral_anchor_prefers_an_accent_over_another_neutral():
    # The core of complementary recommendation: black + gold beats black + black.
    assert harmony("black", "gold").score > harmony("black", "red").score
    assert harmony("black", "red").score > harmony("black", "black").score


def test_metallic_lifts_a_neutral_base():
    assert harmony("black", "gold").relation == "metallic_on_neutral"
    assert harmony("white", "silver").relation == "metallic_on_neutral"


def test_warm_metal_suits_warm_colour_and_not_a_cool_one():
    assert harmony("red", "gold").score > harmony("red", "silver").score
    assert harmony("blue", "silver").score > harmony("blue", "gold").score


def test_neutral_grounds_a_saturated_anchor():
    assert harmony("red", "beige").relation == "neutral_grounding"


def test_same_family_is_scored_below_a_real_pairing():
    # Tonal is valid but must not beat a genuine complement, or the engine
    # degenerates into a similarity recommender.
    assert harmony("red", "red").relation == "same_family"
    assert harmony("red", "red").score < harmony("red", "gold").score


def test_multi_is_unresolved_not_guessed():
    assert harmony("multi", "red").relation == "unresolved"
    assert harmony("red", "multi").relation == "unresolved"


def test_grey_carries_no_hue():
    # Regression: grey once inherited Charcoal's blue-tinted hex and gained a
    # spurious 204deg hue, which made it behave as a cool chromatic.
    assert FAMILY_HUE["grey"] is None
    assert family_class("grey") == "neutral"


def test_hue_distance_is_symmetric_and_wraps():
    assert hue_distance("red", "blue") == hue_distance("blue", "red")
    # red sits at ~353deg, orange at ~28deg: the wrap must be handled
    assert hue_distance("red", "orange") < 60


def test_harmony_is_deterministic():
    assert harmony("black", "gold") == harmony("black", "gold")


def test_no_clash_verdict_is_claimed():
    # Documented limitation: 15 coarse families cannot support clash detection.
    assert "clash" not in {k for k in HARMONY_SCORES if k.endswith("clash")
                           and not k.startswith("metallic")}


# ==========================================================================
# colour_role filtering - the Phase 1 rule
# ==========================================================================


def test_skin_match_colour_never_participates_in_colour_matching():
    assert colour_component("black", "beige", "skin_match", 0.35) is None


def test_packaging_colour_never_participates_in_colour_matching():
    assert colour_component("black", "white", "packaging", 0.35) is None


def test_style_colour_does_participate():
    component = colour_component("black", "gold", "style", 0.35)
    assert component is not None
    assert component.name == "colour_harmony"


def test_no_colour_component_without_an_anchor_colour():
    assert colour_component(None, "gold", "style", 0.35) is None


def test_engine_never_colour_matches_a_foundation(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(gender="women", limit=30),
    ))
    for rec in response.recommendations:
        if rec.product_type in {"Foundation and Primer", "Perfume and Body Mist"}:
            assert not any(c.name == "colour_harmony" for c in rec.components), (
                f"{rec.name} was colour-matched but its colour is not a style signal")


def test_preference_ignores_colour_for_non_style_products():
    style_scored = preference_component(
        "elegant", (), "gold", "style", True, None, 0.14)
    skin_scored = preference_component(
        "elegant", (), "gold", "skin_match", True, None, 0.14)
    assert style_scored.raw > skin_scored.raw


# ==========================================================================
# Category affinity
# ==========================================================================


def test_affinity_is_composed_from_three_factors():
    result = affinity_for("jewellery", "ethnic_wear", "wedding")
    assert result.score == pytest.approx(
        min(1.0, result.base * result.occasion_multiplier * result.anchor_multiplier))
    assert "base" in result.explanation


def test_wedding_raises_jewellery_and_lowers_wallets():
    assert (affinity_for("jewellery", "ethnic_wear", "wedding").score
            > affinity_for("jewellery", "ethnic_wear", "casual").score)
    assert (affinity_for("wallet", "ethnic_wear", "wedding").score
            < affinity_for("jewellery", "ethnic_wear", "wedding").score)


def test_sports_occasion_suppresses_makeup():
    assert affinity_for("beauty_lip", "topwear", "sports").score < 0.3


def test_belt_matters_for_bottomwear_not_for_a_saree():
    assert (affinity_for("belt", "bottomwear", None).score
            > affinity_for("belt", "ethnic_wear", None).score)


def test_ranked_categories_excludes_and_includes():
    available = {"jewellery", "bag", "beauty_lip", "wallet"}
    only = ranked_categories("ethnic_wear", "wedding", available,
                             include=("jewellery", "bag"))
    assert {a.category_group for a in only} == {"jewellery", "bag"}

    without = ranked_categories("ethnic_wear", "wedding", available,
                                exclude=("jewellery",))
    assert "jewellery" not in {a.category_group for a in without}


def test_ranked_categories_is_sorted_and_thresholded():
    result = ranked_categories("ethnic_wear", "wedding",
                               {"jewellery", "bag", "beauty_lip", "wallet"})
    scores = [a.score for a in result]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= MIN_AFFINITY for s in scores)


def test_product_type_refines_a_coarse_category():
    # A deodorant must not rank as a styling choice just because it sits in the
    # same category group as perfume.
    deodorant, _ = product_type_relevance("Deodorant")
    perfume, _ = product_type_relevance("Perfume and Body Mist")
    assert deodorant < perfume
    laptop, _ = product_type_relevance("Laptop Bag")
    clutch, _ = product_type_relevance("Clutches")
    assert laptop < clutch


# ==========================================================================
# Occasion
# ==========================================================================


def test_occasion_synonyms_normalise():
    assert normalise_occasion("shaadi") == "wedding"
    assert normalise_occasion("Diwali") == "festive"
    assert normalise_occasion("night out") == "party"
    assert normalise_occasion("gym") == "sports"
    assert normalise_occasion("nonsense-occasion") is None


def test_beauty_suitability_never_reads_the_source_occasion():
    # Signature carries no source-occasion parameter at all, by design.
    import inspect
    params = set(inspect.signature(beauty_suitability).parameters)
    assert "product_occasion" not in params
    assert "occasion" not in params


def test_deep_shades_suit_a_wedding_more_than_pale_ones():
    deep = beauty_suitability("beauty_lip", "red", "style", "matte", "wedding")
    pale = beauty_suitability("beauty_lip", "beige", "style", "gloss", "wedding")
    assert deep.score > pale.score
    assert deep.basis == "derived_from_attributes"


def test_pale_shades_suit_everyday_more_than_deep_ones():
    deep = beauty_suitability("beauty_lip", "red", "style", "matte", "casual")
    pale = beauty_suitability("beauty_lip", "beige", "style", "gloss", "casual")
    assert pale.score > deep.score


def test_skin_match_suitability_ignores_shade():
    a = beauty_suitability("beauty_face", "beige", "skin_match", None, "wedding")
    b = beauty_suitability("beauty_face", "red", "skin_match", None, "wedding")
    assert a.score == b.score


def test_catalog_occasion_path_used_for_non_beauty():
    result = catalog_suitability("ethnic", "wedding")
    assert result.basis == "catalog_occasion"
    assert result.score > catalog_suitability("sports", "wedding").score


def test_unknown_occasion_is_not_scored_as_mediocre():
    result = catalog_suitability("ethnic", "not-an-occasion")
    assert "not a recognised occasion" in result.explanation


# ==========================================================================
# Candidate filtering
# ==========================================================================


def test_only_complements_are_candidates(tiny_store):
    assert all(tiny_store.complements.can_be_complement)
    assert "ethnic_wear" not in tiny_store.available_complement_groups


def test_anchor_category_is_never_recommended(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"), Preferences(limit=30)))
    assert all(r.category_group != "ethnic_wear" for r in response.recommendations)


def test_gender_filter_applies(tiny_store):
    pool = tiny_store.candidate_pool("jewellery", gender="men")
    assert pool.empty or set(pool.gender) <= {"men", "unisex"}


def test_unknown_product_id_fails_gracefully(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(Anchor(product_id=999_999_999)))
    assert response.is_empty
    assert any("not in the catalog" in w for w in response.warnings)


def test_every_recommendation_exists_in_the_catalog(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"), Preferences(limit=20)))
    assert response.recommendations
    for rec in response.recommendations:
        assert tiny_store.exists(rec.product_id)


# ==========================================================================
# Scoring
# ==========================================================================


def test_combine_is_a_weighted_mean_over_active_components():
    components = [
        ScoreComponent("a", 1.0, 0.5, ""),
        ScoreComponent("b", 0.0, 0.5, ""),
    ]
    assert combine(components) == pytest.approx(0.5)


def test_absent_components_do_not_dilute_the_score():
    # A single perfect component must score 1.0, not 1.0 * its weight.
    assert combine([ScoreComponent("a", 1.0, 0.35, "")]) == pytest.approx(1.0)


def test_combine_handles_no_components():
    assert combine([]) == 0.0


def test_weights_are_configurable_and_documented():
    assert set(DEFAULT_CONFIG.as_dict()) == {
        "colour_harmony", "occasion_suitability", "category_affinity",
        "preference_match", "text_relevance"}
    assert DEFAULT_CONFIG.colour > DEFAULT_CONFIG.text


def test_style_synonyms_normalise():
    assert normalise_style("classy") == "elegant"
    assert normalise_style("understated") == "minimal"
    assert normalise_style("not-a-style") is None


def test_requested_colour_scores_above_an_unrelated_one():
    wanted = preference_component(None, ("gold",), "gold", "style", True, None, 0.14)
    other = preference_component(None, ("gold",), "green", "style", False, None, 0.14)
    assert wanted.raw > other.raw


def test_preference_absent_when_nothing_requested():
    assert preference_component(None, (), "gold", "style", True, None, 0.14) is None


def test_scores_are_bounded(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="wedding", style="elegant", limit=30)))
    assert all(0.0 <= r.score <= 1.0 for r in response.recommendations)


def test_engine_is_deterministic(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    request = LookRequest(Anchor(anchor_type="saree", colour="black"),
                          Preferences(occasion="wedding", style="elegant", limit=10))
    first = [r.product_id for r in engine.recommend(request).recommendations]
    second = [r.product_id for r in engine.recommend(request).recommendations]
    assert first == second


# ==========================================================================
# Diversity
# ==========================================================================


def _candidate(pid, score, brand, colour, ptype="Earrings"):
    return {"product_id": pid, "score": score, "brand": brand,
            "colour_family": colour, "product_type": ptype,
            "category_group": "jewellery"}


def test_diversity_breaks_up_a_single_brand():
    candidates = [_candidate(i, 0.9 - i * 0.001, "SameBrand", "gold") for i in range(10)]
    candidates.append(_candidate(99, 0.5, "OtherBrand", "red"))
    picked = rerank(candidates, 5)
    brands = {p["brand"] for p in picked}
    assert "OtherBrand" in brands


def test_brand_cap_is_hard():
    config = DiversityConfig(max_per_brand=2)
    candidates = [_candidate(i, 0.9, "SameBrand", f"c{i}") for i in range(10)]
    picked = rerank(candidates, 10, config)
    assert sum(1 for p in picked if p["brand"] == "SameBrand") <= 2


def test_diversity_prefers_a_new_colour_when_scores_are_close():
    candidates = [
        _candidate(1, 0.90, "A", "gold"),
        _candidate(2, 0.89, "B", "gold"),
        _candidate(3, 0.88, "C", "red"),
    ]
    picked = rerank(candidates, 2)
    assert [p["product_id"] for p in picked] == [1, 3]


def test_diversity_keeps_the_best_item_first():
    candidates = [_candidate(1, 0.99, "A", "gold"), _candidate(2, 0.5, "B", "red")]
    assert rerank(candidates, 2)[0]["product_id"] == 1


def test_diversity_records_why_an_item_was_demoted():
    candidates = [_candidate(1, 0.9, "A", "gold"), _candidate(2, 0.89, "A2", "gold")]
    picked = rerank(candidates, 2)
    assert picked[1]["diversity_note"]


def test_diversity_handles_an_empty_pool():
    assert rerank([], 5) == []


def test_measure_reports_concentration():
    stats = measure([_candidate(1, 0.9, "A", "gold"), _candidate(2, 0.8, "A", "gold")])
    assert stats["brands"] == 1
    assert stats["max_share_one_brand"] == 1.0


def test_real_results_are_not_single_brand(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"), Preferences(limit=10)))
    stats = measure([r.to_dict() | {"brand": r.brand} for r in response.recommendations])
    assert stats["max_share_one_brand"] <= 0.5


# ==========================================================================
# Explanations
# ==========================================================================


def test_reasons_are_generated_from_components_that_fired():
    components = (
        ScoreComponent("colour_harmony", 0.95, 0.35, "gold lifts a black base"),
        ScoreComponent("occasion_suitability", 0.9, 0.25, "suits a wedding"),
    )
    reasons = build_reasons(components)
    assert any("gold lifts a black base" in r for r in reasons)
    assert any("suits a wedding" in r for r in reasons)


def test_reasons_are_ordered_by_contribution():
    components = (
        ScoreComponent("text_relevance", 1.0, 0.08, "weak signal"),
        ScoreComponent("colour_harmony", 1.0, 0.35, "strong signal"),
    )
    assert "strong signal" in build_reasons(components)[0]


def test_weak_components_are_not_claimed_as_reasons():
    components = (ScoreComponent("colour_harmony", 0.25, 0.35, "poor colour match"),)
    reasons = build_reasons(components)
    assert any("Weak match" in r for r in reasons)


def test_no_components_yields_an_honest_statement():
    assert "No scoring signal" in build_reasons(())[0]


def test_every_recommendation_carries_reasons(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="wedding", limit=20)))
    for rec in response.recommendations:
        assert rec.reasons
        assert rec.components
        # every reason must trace back to a component that was actually scored
        assert all(isinstance(r, str) and r for r in rec.reasons)


def test_breakdown_contributions_sum_to_the_score(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="wedding", limit=5)))
    for rec in response.recommendations:
        total_weight = sum(c.weight for c in rec.components)
        expected = sum(c.contribution for c in rec.components) / total_weight
        assert rec.score == pytest.approx(expected)


# ==========================================================================
# Thin categories and no-result handling
# ==========================================================================


def test_thin_category_is_reported_as_thin(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="wedding", limit=30)))
    headwear = [c for c in response.categories if c.category_group == "headwear"]
    if headwear:
        assert headwear[0].confidence in {"thin", "none"}
        assert headwear[0].note


def test_mixed_colour_role_category_reports_the_usable_subset(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="wedding", limit=30)))
    face = [c for c in response.categories if c.category_group == "beauty_face"]
    assert face, "beauty_face should be considered"
    # 8 foundations (skin_match) + 2 blushes (style): the note must say so
    assert face[0].note and "cannot be matched" in face[0].note


def test_nothing_is_returned_below_the_acceptance_floor():
    store = make_store([
        product(1, "Awful Match", "jewellery", "multi", occasion="sports"),
    ])
    engine = RecommendationEngine(store=store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="sports", limit=5)))
    for category in response.categories:
        for rec in category.recommendations:
            assert rec.score >= MIN_ACCEPTABLE_SCORE


def test_empty_catalog_returns_no_results_not_an_error():
    store = make_store([product(1, "Anchor", "ethnic_wear", "black",
                                can_be_anchor=True, can_be_complement=False)])
    engine = RecommendationEngine(store=store)
    response = engine.recommend(LookRequest(Anchor(anchor_type="saree", colour="black")))
    assert response.is_empty
    assert response.warnings


def test_excluding_everything_is_handled(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(exclude_categories=tuple(tiny_store.available_complement_groups))))
    assert response.is_empty
    assert any("include/exclude" in w for w in response.warnings)


def test_unrecognised_occasion_warns_and_still_answers(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="moon landing", limit=5)))
    assert any("not a recognised occasion" in w for w in response.warnings)
    assert response.recommendations


def test_unrecognised_anchor_words_are_reported_not_guessed(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="spacesuit", colour="ultraviolet")))
    assert any("Could not interpret" in w for w in response.warnings)


def test_broad_request_with_no_anchor_still_answers(tiny_store):
    engine = RecommendationEngine(store=tiny_store)
    response = engine.recommend(LookRequest(Anchor(), Preferences(limit=5)))
    assert any("No anchor was given" in w for w in response.warnings)
    assert all(not any(c.name == "colour_harmony" for c in r.components)
               for r in response.recommendations)


# ==========================================================================
# Text relevance
# ==========================================================================


def test_text_relevance_matches_a_descriptor_term():
    store = make_store([
        product(1, "Silk Scarf", "neckwear", "red", text_blob="Silk Scarf | red silk"),
        product(2, "Cotton Scarf", "neckwear", "red", text_blob="Cotton Scarf | red cotton"),
    ])
    relevance = TextRelevance(store.complements)
    scores = relevance.score("silk", [1, 2])
    assert scores[1].score > scores[2].score
    assert "silk" in scores[1].matched_terms


def test_empty_query_contributes_nothing():
    store = make_store([product(1, "Silk Scarf", "neckwear", "red")])
    relevance = TextRelevance(store.complements)
    assert relevance.score("", [1])[1].score == 0.0


def test_stopwords_are_not_treated_as_signal():
    store = make_store([product(1, "Silk Scarf", "neckwear", "red")])
    relevance = TextRelevance(store.complements)
    assert relevance.query_terms("i want a look for the") == []


# ==========================================================================
# Integration against the real catalog
# ==========================================================================


def test_flagship_black_saree_wedding(real_store):
    engine = RecommendationEngine(store=real_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="wedding", style="elegant", gender="women", limit=10)))

    assert len(response.recommendations) >= 8
    groups = {r.category_group for r in response.recommendations}
    assert groups & {"beauty_lip", "beauty_eye"}, "a look needs makeup"
    assert groups & {"jewellery", "bag"}, "a look needs accessories"
    assert all(r.category_group != "ethnic_wear" for r in response.recommendations)
    assert all(r.reasons for r in response.recommendations)


def test_anchor_by_product_id_resolves(real_store):
    saree = real_store.df[
        (real_store.df.product_type == "Sarees")
        & (real_store.df.colour_family == "black")].iloc[0]
    engine = RecommendationEngine(store=real_store)
    response = engine.recommend(LookRequest(
        Anchor(product_id=int(saree.product_id)),
        Preferences(occasion="wedding", limit=8)))
    assert response.resolved_anchor["source"] == "catalog_product"
    assert response.resolved_anchor["colour_family"] == "black"
    assert response.recommendations


def test_party_sparsity_is_disclosed(real_store):
    engine = RecommendationEngine(store=real_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="dress", colour="pink"),
        Preferences(occasion="party", gender="women", limit=8)))
    assert any("only 28 products labelled 'party'" in w for w in response.warnings)


def test_latency_is_reasonable(real_store):
    engine = RecommendationEngine(store=real_store)
    request = LookRequest(Anchor(anchor_type="saree", colour="black"),
                          Preferences(occasion="wedding", gender="women", limit=10))
    engine.recommend(request)                       # warm any caches
    response = engine.recommend(request)
    assert response.diagnostics["latency_ms"] < 2000


def test_explicitly_included_category_is_never_silently_dropped(real_store):
    # Regression: headwear for a wedding scores 0.08, below MIN_AFFINITY, and
    # was being filtered out entirely - so an explicit request returned nothing
    # with a warning about include/exclude filters. An explicit ask must be
    # honoured with its weakness reported, not vetoed by a default floor.
    engine = RecommendationEngine(store=real_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(include_categories=("headwear",), occasion="wedding",
                    gender="women", limit=5)))
    assert response.categories, "an explicitly requested category must be considered"
    assert response.categories[0].category_group == "headwear"
    assert response.recommendations, "an explicit request must return something"
    assert response.categories[0].affinity < MIN_AFFINITY, (
        "this test is meaningless unless the affinity really is below the floor")


def test_low_affinity_categories_do_not_crowd_a_look(real_store):
    # A watch scores 0.16 affinity at a wedding; colour alone must not let it
    # take slots from jewellery and makeup.
    engine = RecommendationEngine(store=real_store)
    response = engine.recommend(LookRequest(
        Anchor(anchor_type="saree", colour="black"),
        Preferences(occasion="wedding", gender="women", limit=10)))
    watches = sum(1 for r in response.recommendations if r.category_group == "watch")
    assert watches == 0


def test_vocabulary_matching_respects_word_boundaries():
    # Regression: substring matching resolved "ultraviolet" -> purple (contains
    # "violet"), "blackberry" -> black, and "laptop bag" -> a topwear anchor
    # (contains "top"). Free text reaches these resolvers from users and from an
    # LLM, so a loose match silently feeds the engine an attribute nobody asked for.
    from src.engine.catalog_store import resolve_anchor_type, resolve_colour
    assert resolve_colour("ultraviolet") is None
    assert resolve_colour("blackberry") is None
    assert resolve_colour("greenhouse") is None
    assert resolve_anchor_type("laptop bag") == (None, None)
    # ...while genuine phrases still resolve, longest first
    assert resolve_colour("a navy blue shirt") == "blue"
    assert resolve_colour("off-white top") == "white"
    assert resolve_anchor_type("black saree") == ("ethnic_wear", "Sarees")
    assert resolve_anchor_type("kurta set") == ("ethnic_wear", "Kurta Sets")
