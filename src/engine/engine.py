"""The recommendation engine.

Given something the user already has, recommend complementary products from
other categories. Deterministic end to end: no LLM, no randomness, no network.

    filter -> score -> per-category selection -> diversity -> explain

Nothing is fabricated. Every returned product is a row resolved through
`CatalogStore`, and every reason is generated from a score component that
actually fired.
"""

from __future__ import annotations

import time
from functools import cached_property

from .affinity import ranked_categories
from .catalog_store import CatalogStore, UnknownProduct
from .diversity import DEFAULT_DIVERSITY, DiversityConfig, rerank
from .explain import build_reasons, explain_category
from .occasion import (
    SPARSE_CATALOG_OCCASIONS,
    CANONICAL_OCCASIONS,
    normalise_occasion,
)
from .relevance import TextRelevance
from .schemas import (
    CategoryResult,
    LookRequest,
    LookResponse,
    Recommendation,
    ScoreComponent,
)
from .scoring import (
    DEFAULT_CONFIG,
    ScoreConfig,
    affinity_component,
    colour_component,
    combine,
    normalise_style,
    occasion_component,
    preference_component,
    text_component,
)

# A category needs this many qualifying products before we call the choice real.
STRONG_POOL = 25
MODERATE_POOL = 8

# Below this score we would rather return nothing than pad the result.
MIN_ACCEPTABLE_SCORE = 0.45

# How many products to consider per category before diversity re-ranking.
PER_CATEGORY_SHORTLIST = 25


class RecommendationEngine:
    def __init__(
        self,
        store: CatalogStore | None = None,
        config: ScoreConfig = DEFAULT_CONFIG,
        diversity: DiversityConfig = DEFAULT_DIVERSITY,
    ):
        self.store = store or CatalogStore()
        self.config = config
        self.diversity = diversity

    @cached_property
    def relevance(self) -> TextRelevance:
        """Built lazily - a request with no free text never pays for it."""
        return TextRelevance(self.store.complements)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, request: LookRequest) -> LookResponse:
        started = time.perf_counter()
        warnings: list[str] = []
        prefs = request.preferences

        # ---- resolve the anchor --------------------------------------
        try:
            anchor = self.store.resolve_anchor(
                request.anchor.product_id,
                request.anchor.anchor_type,
                request.anchor.colour,
                prefs.gender,
            )
        except UnknownProduct as exc:
            return self._empty(
                {"source": "unknown", "product_id": request.anchor.product_id},
                (f"{exc}. No recommendations can be made without a valid anchor.",),
                started,
            )

        if request.anchor.is_empty():
            warnings.append(
                "No anchor was given, so recommendations are ranked on occasion, "
                "style and preferences only - there is no colour to coordinate with.")
        for item in anchor.unresolved:
            warnings.append(
                f"Could not interpret {item}; it was ignored rather than guessed.")
        if anchor.colour_family is None and not request.anchor.is_empty():
            warnings.append(
                "No anchor colour was resolved, so colour harmony did not "
                "contribute to ranking.")

        # ---- occasion and style --------------------------------------
        occasion = normalise_occasion(prefs.occasion)
        if prefs.occasion and occasion is None:
            warnings.append(
                f"'{prefs.occasion}' is not a recognised occasion "
                f"({', '.join(CANONICAL_OCCASIONS)}); occasion was not used to rank.")
        if occasion:
            warnings.extend(self._occasion_coverage_warnings(occasion))

        style = normalise_style(prefs.style)
        if prefs.style and style is None:
            warnings.append(
                f"'{prefs.style}' is not a recognised style; style was not used to rank.")

        preferred_colours = tuple(
            f for f in (self._resolve_colour(c) for c in prefs.preferred_colours) if f)

        # ---- which categories to consider ----------------------------
        affinities = ranked_categories(
            anchor.category_group,
            occasion,
            self.store.available_complement_groups,
            include=prefs.include_categories,
            exclude=prefs.exclude_categories,
        )
        if not affinities:
            return self._empty(
                anchor.to_dict(),
                tuple(warnings) + (
                    "No complementary category remained after applying the "
                    "include/exclude filters.",),
                started,
            )

        # ---- score each category -------------------------------------
        # Only free text drives text relevance. `style` is handled structurally
        # by preference_component; feeding it here too would double-count it and
        # would build the TF-IDF index for every request.
        query_text = prefs.free_text or ""

        category_results: list[CategoryResult] = []
        for affinity in affinities:
            category_results.append(
                self._score_category(
                    affinity, anchor, occasion, style, preferred_colours, query_text))

        # ---- assemble, with an affinity-scaled per-category cap -------
        # Affinity's job is to decide which categories belong in the answer, so
        # it governs how many slots a category may occupy. Without this a watch
        # (affinity 0.16 at a wedding) can still take two of ten slots purely on
        # colour score, which contradicts the affinity the engine just reported.
        pool: list[dict] = []
        explicit = set(prefs.include_categories)
        for result in category_results:
            slots = self._slots_for(result.affinity, prefs.max_per_category)
            if result.category_group in explicit:
                # The user named this category; give it a place even if its
                # affinity is low, and let the reported confidence carry the
                # caveat rather than dropping it silently.
                slots = max(slots, 1)
            for rank, rec in enumerate(result.recommendations[:slots]):
                pool.append({
                    "recommendation": rec,
                    "score": rec.score,
                    "brand": rec.brand,
                    "colour_family": rec.colour_family,
                    "product_type": rec.product_type,
                    "category_group": rec.category_group,
                    "category_rank": rank,
                })

        selected = rerank(pool, prefs.limit, self.diversity)

        final: list[Recommendation] = []
        for entry in selected:
            rec = entry["recommendation"]
            if entry.get("diversity_note"):
                rec = Recommendation(
                    **{**rec.__dict__,
                       "reasons": build_reasons(rec.components, entry["diversity_note"])})
            final.append(rec)

        warnings.extend(self._coverage_warnings(category_results))

        elapsed_ms = (time.perf_counter() - started) * 1000
        return LookResponse(
            resolved_anchor=anchor.to_dict(),
            categories=tuple(category_results),
            recommendations=tuple(final),
            warnings=tuple(dict.fromkeys(warnings)),
            diagnostics={
                "catalog_size": len(self.store),
                "categories_considered": len(affinities),
                "categories_with_results": sum(
                    1 for c in category_results if c.recommendations),
                "resolved_occasion": occasion,
                "resolved_style": style,
                "weights": self.config.as_dict(),
                "latency_ms": round(elapsed_ms, 2),
            },
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_colour(self, text: str) -> str | None:
        from .catalog_store import resolve_colour
        return resolve_colour(text)

    def _score_category(
        self,
        affinity,
        anchor,
        occasion: str | None,
        style: str | None,
        preferred_colours: tuple[str, ...],
        query_text: str,
    ) -> CategoryResult:
        group = affinity.category_group
        full_pool = self.store.candidate_pool(group)
        pool = self.store.candidate_pool(group, gender=anchor.gender)

        if pool.empty:
            return CategoryResult(
                group, affinity.score,
                explain_category(group, affinity.explanation, len(full_pool), 0, "none"),
                len(full_pool), 0, "none", (),
                note="No products in this category match the requested audience.",
            )

        # Components depend only on a handful of attributes, so memoising on
        # those makes scoring the whole pool cheap without any approximation.
        cache: dict[tuple, tuple[list[ScoreComponent], float]] = {}

        text_scores = (
            self.relevance.score(query_text, pool.product_id.tolist())
            if query_text.strip() else {}
        )

        scored: list[tuple[float, list[ScoreComponent], object]] = []
        for row in pool.itertuples(index=False):
            key = (row.colour_family, row.colour_role, row.finish,
                   row.occasion, row.domain, row.is_metallic, row.product_type)
            cached = cache.get(key)
            if cached is None:
                components = [
                    colour_component(anchor.colour_family, row.colour_family,
                                     row.colour_role, self.config.colour),
                    occasion_component(row.domain, occasion, row.occasion, group,
                                       row.colour_family, row.colour_role,
                                       row.finish, self.config.occasion),
                    affinity_component(affinity.score, affinity.explanation,
                                       self.config.affinity, row.product_type),
                    preference_component(style, preferred_colours, row.colour_family,
                                         row.colour_role, bool(row.is_metallic),
                                         row.finish, self.config.preference),
                ]
                components = [c for c in components if c is not None]
                cached = (components, combine(components))
                cache[key] = cached

            components, base_score = cached
            relevance = text_scores.get(int(row.product_id))
            if relevance is not None:
                text_c = text_component(relevance, self.config.text)
                if text_c is not None:
                    components = components + [text_c]
                    base_score = combine(components)

            scored.append((base_score, components, row))

        scored.sort(key=lambda item: (-item[0], item[2].product_id))
        qualifying = [s for s in scored if s[0] >= MIN_ACCEPTABLE_SCORE]

        # Confidence must reflect the choice that actually exists for *this*
        # request. beauty_face holds 155 products, but 118 of them are
        # foundation/concealer/compact whose colour matches skin rather than an
        # outfit - so when the user has an anchor colour, the real choice is the
        # 37 blush/highlighter items, and reporting "strong" would be false.
        # Only meaningful where the category is *mixed*. Fragrance is uniformly
        # packaging-coloured, so colour was never applicable there and judging it
        # on colour-matchable stock would wrongly report it as empty.
        style_candidates = [s for s in qualifying if s[2].colour_role == "style"]
        colour_matters = (
            anchor.colour_family is not None
            and 0 < len(style_candidates) < len(qualifying)
        )
        effective = style_candidates if colour_matters else qualifying
        confidence = self._confidence(len(effective),
                                      effective[0][0] if effective else 0.0)

        note = None
        if colour_matters and len(effective) < len(qualifying):
            note = (f"{len(qualifying) - len(effective)} of {len(qualifying)} "
                    f"products here have a colour that cannot be matched to an "
                    f"outfit (skin tone or packaging); {len(effective)} can.")
        if not qualifying:
            best = scored[0][0] if scored else 0.0
            note = (f"No product in this category scored above "
                    f"{MIN_ACCEPTABLE_SCORE:.2f} (best was {best:.2f}), so nothing "
                    f"is recommended here rather than filling the slot.")
        elif confidence == "thin":
            note = (f"Only {len(effective)} products in this category are a good "
                    f"match, so the selection is limited."
                    + (f" {note}" if note else ""))

        recommendations = tuple(
            Recommendation(
                product_id=int(row.product_id),
                name=row.name,
                brand=row.brand if isinstance(row.brand, str) else None,
                category_group=row.category_group,
                product_type=row.product_type,
                colour_family=row.colour_family,
                base_colour=row.base_colour,
                score=score,
                components=tuple(components),
                reasons=build_reasons(tuple(components)),
            )
            for score, components, row in qualifying[:PER_CATEGORY_SHORTLIST]
        )

        return CategoryResult(
            category_group=group,
            affinity=affinity.score,
            why_considered=explain_category(
                group, affinity.explanation, len(full_pool), len(qualifying), confidence),
            candidates_before_filter=len(full_pool),
            candidates_after_filter=len(qualifying),
            confidence=confidence,
            recommendations=recommendations,
            note=note,
        )

    # Affinity tiers governing how many final slots a category may take.
    CORE_AFFINITY = 0.60          # full allowance
    SUPPORTING_AFFINITY = 0.35    # one item only

    @classmethod
    def _slots_for(cls, affinity: float, max_per_category: int) -> int:
        if affinity >= cls.CORE_AFFINITY:
            return max_per_category
        if affinity >= cls.SUPPORTING_AFFINITY:
            return 1
        return 0                  # reported in `categories`, absent from the look

    @staticmethod
    def _confidence(qualifying: int, best_score: float) -> str:
        if qualifying == 0:
            return "none"
        if qualifying >= STRONG_POOL and best_score >= 0.60:
            return "strong"
        if qualifying >= MODERATE_POOL:
            return "moderate"
        return "thin"

    @staticmethod
    def _occasion_coverage_warnings(occasion: str) -> list[str]:
        """Be explicit when the catalog cannot support an occasion literally."""
        if occasion == "party":
            return ["The catalog holds only 28 products labelled 'party', so party "
                    "requests are served from ethnic, formal and smart-casual items "
                    "rather than by filtering on the label."]
        if occasion in {"wedding", "festive"}:
            return []
        return []

    @staticmethod
    def _coverage_warnings(results: list[CategoryResult]) -> list[str]:
        thin = [r.category_group for r in results if r.confidence == "thin"]
        empty = [r.category_group for r in results if r.confidence == "none"]
        out = []
        if thin:
            out.append("Limited choice in: " + ", ".join(sorted(thin)) + ".")
        if empty:
            out.append("Nothing suitable found in: " + ", ".join(sorted(empty))
                       + ". These were left out rather than filled with a poor match.")
        return out

    def _empty(self, anchor: dict, warnings: tuple[str, ...], started: float) -> LookResponse:
        return LookResponse(
            resolved_anchor=anchor,
            categories=(),
            recommendations=(),
            warnings=warnings,
            diagnostics={
                "catalog_size": len(self.store),
                "categories_considered": 0,
                "categories_with_results": 0,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
