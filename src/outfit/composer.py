"""Assemble a coherent outfit from the existing recommendation engine.

This layer sits **above** the Phase 2 engine and does not reimplement any of
it. It decides *which categories* to ask for; the engine still does retrieval,
colour compatibility, occasion fit, category affinity, scoring, ranking,
diversity and explanations, and every product still comes from the real catalog.

Two mechanics are worth understanding:

1. **Clothing is an anchor in the Phase 1 taxonomy**, so the engine will never
   return a kurta or a pair of trousers as a *complement*. To rank clothing with
   the same scorer rather than writing a second one, the composer builds a
   second `CatalogStore` over a view of the catalog in which the wanted clothing
   groups are marked complementable, and runs the ordinary engine against it.
   No engine code changes; the scoring, colour model and diversity are identical.

2. **One engine call per section.** A `CategoryResult` carries its full ranked
   list, so asking for one category at a time gives the section as many products
   as it needs without touching the engine's slot allocation.

Gender is applied as a hard filter by the engine itself (`candidate_pool`
intersects on gender), and the composer additionally verifies it - a men's look
containing a women's product is a bug worth catching loudly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache

import pandas as pd

from ..engine.catalog_store import CatalogStore
from ..engine.diversity import rerank
from ..engine.scoring import request_match
from ..engine.engine import RecommendationEngine
from ..engine.schemas import Anchor, LookRequest, Preferences, Recommendation
from .policy import Section, infer_gender_from_garment, sections_for, title_for

# A section with fewer than this many qualifying products is reported as thin
# rather than presented as a real choice.
THIN_SECTION = 3

# How close a product type must be to the strongest type in a section to be
# offered alongside it.
TYPE_FLOOR = 0.75


@dataclass
class ComposedSection:
    key: str
    title: str
    groups: tuple[str, ...]
    products: list[Recommendation] = field(default_factory=list)
    confidence: str = "none"
    note: str | None = None
    essential: bool = False

    def to_dict(self, shape) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "categories": list(self.groups),
            "confidence": self.confidence,
            "note": self.note,
            "essential": self.essential,
            "products": [shape(p) for p in self.products],
        }


@dataclass
class ComposedOutfit:
    sections: list[ComposedSection]
    anchor: dict
    warnings: list[str]
    diagnostics: dict

    @property
    def all_products(self) -> list[Recommendation]:
        return [p for section in self.sections for p in section.products]


class OutfitComposer:
    def __init__(self, engine: RecommendationEngine):
        self.engine = engine
        self.store = engine.store

    # ------------------------------------------------------------------
    # Product requests that name a garment
    # ------------------------------------------------------------------

    def primary_garment(
        self,
        product_type: str | None,
        category_group: str | None,
        colour: str | None,
        gender: str | None,
        occasion: str | None,
        style: str | None = None,
        free_text: str | None = None,
        limit: int = 6,
    ) -> tuple[list[Recommendation], str | None]:
        """The product the shopper actually asked for.

        "red kurta for men" is a request to see kurtas, not a request for things
        that go with one - and "perfume" is a request to see perfumes. This
        returns that product, ranked on how well it matches the request, plus a
        note when the catalog cannot honour the colour.
        """
        if not category_group:
            return [], None

        types = (product_type,) if product_type else ()
        note = None
        wanted_colour = colour
        if wanted_colour and not self._clothing_pool_size(
                (category_group,), types, wanted_colour, gender):
            note = (f"The catalog has no {wanted_colour} "
                    f"{(product_type or category_group).lower()} for this request, "
                    f"so the closest compatible colours are shown instead.")
            wanted_colour = None

        engine = self._clothing_engine((category_group,), types, wanted_colour)
        if len(engine.store.complements) == 0:
            return [], note

        response = engine.recommend(LookRequest(
            anchor=Anchor(),
            preferences=Preferences(
                occasion=occasion, style=style, gender=gender,
                free_text=free_text,
                include_categories=(category_group,),
                max_per_category=limit, limit=limit),
        ))
        ranked = [r for result in response.categories
                  for r in result.recommendations]

        # Re-score against the request itself. The engine scored these as if
        # they were complements to an empty anchor, which answers "does this go
        # with something?" - the wrong question for the item that was asked for,
        # and the reason a matching heel could out-score the requested shirt.
        rescored = []
        for recommendation in ranked:
            row = self.store.get(recommendation.product_id)
            score, components = request_match(
                requested_type=product_type,
                requested_group=category_group,
                requested_colour=colour,
                requested_occasion=occasion,
                requested_style=style,
                product_type=row["product_type"],
                category_group=row["category_group"],
                product_occasion=row["occasion"],
                colour_family=row["colour_family"],
                colour_role=row["colour_role"],
                is_metallic=bool(row["is_metallic"]),
                finish=row["finish"],
            )
            rescored.append(replace(
                recommendation, score=score, components=components,
                reasons=tuple(c.detail for c in components)))
        rescored.sort(key=lambda r: r.score, reverse=True)

        candidates = [
            {"recommendation": r, "score": r.score, "brand": r.brand,
             "colour_family": r.colour_family, "product_type": r.product_type,
             "category_group": r.category_group}
            for r in rescored
        ]
        return [c["recommendation"] for c in rerank(candidates, limit)], note

    def gender_for_garment(self, product_type: str | None) -> str | None:
        return infer_gender_from_garment(self.store.df, product_type)

    # ------------------------------------------------------------------
    # Clothing view
    # ------------------------------------------------------------------

    @lru_cache(maxsize=64)
    def _clothing_engine(
        self,
        groups: tuple[str, ...],
        product_types: tuple[str, ...] = (),
        colour: str | None = None,
        anchor_id: int | None = None,
    ) -> RecommendationEngine:
        """An engine over a catalog view where the wanted clothing is complementable.

        This is the whole trick that lets clothing be ranked by the existing
        scorer: the catalog frame is copied and re-flagged, nothing in the
        engine is modified, and the returned engine behaves identically in
        every other respect.

        `product_types` narrows within a group - `ethnic_wear` holds both kurtas
        and churidars, and a churidar does not belong in "Main look".
        `colour` restricts the pool when the shopper asked for a garment in a
        specific colour: they said red kurta, so a gold one is a wrong answer,
        not a lower-scoring one.
        """
        frame = self.store.df
        wanted = frame.category_group.isin(groups)
        if product_types:
            wanted &= frame.product_type.isin(product_types)
        if colour:
            wanted &= frame.colour_family == colour

        # The view holds ONLY the wanted rows. Two reasons: the engine can then
        # return nothing but what this section asked for, and the frame stays
        # small enough that one view per product type is cheap - which is what
        # makes type-level querying viable below.
        view = frame[wanted].copy()
        view["can_be_complement"] = True
        view["can_be_anchor"] = False

        # The engine resolves an anchor by id through its own store, so the
        # anchor row has to be present in the view or the lookup raises and the
        # whole section comes back empty. It is marked non-complementable, so it
        # can anchor the section without being recommended back.
        if anchor_id is not None and anchor_id not in set(view.product_id):
            anchor_row = frame[frame.product_id == anchor_id].copy()
            anchor_row["can_be_complement"] = False
            anchor_row["can_be_anchor"] = True
            view = pd.concat([view, anchor_row], ignore_index=True)
        return RecommendationEngine(store=CatalogStore(frame=view))

    def _clothing_pool_size(self, groups, product_types, colour, gender) -> int:
        frame = self.store.df
        mask = frame.category_group.isin(groups) & (frame.age_group == "adult")
        if product_types:
            mask &= frame.product_type.isin(product_types)
        if colour:
            mask &= frame.colour_family == colour
        if gender:
            mask &= frame.gender.isin([gender, "unisex"])
        return int(mask.sum())

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(
        self,
        gender: str | None,
        occasion: str | None,
        anchor_group: str | None,
        anchor_colour: str | None,
        style: str | None = None,
        free_text: str | None = None,
        exclude_categories: tuple[str, ...] = (),
    ) -> ComposedOutfit:
        warnings: list[str] = []
        shape = sections_for(gender, occasion, anchor_group)

        # ---- 1. the main garment ------------------------------------
        # Everything else is coordinated against it, so it is resolved first.
        main_section = next(s for s in shape if s.key == "main")
        # The colour the shopper named applies to the garment itself. If the
        # catalog has none in that colour, say so rather than silently serving a
        # different colour as though it were the request.
        wanted_colour = anchor_colour
        if wanted_colour and not self._clothing_pool_size(
                main_section.groups, main_section.product_types, wanted_colour, gender):
            warnings.append(
                f"The catalog has no {wanted_colour} {main_section.title.lower()} "
                f"for this request, so the closest compatible colours are shown "
                f"instead.")
            wanted_colour = None
        main = self._section(main_section, gender, occasion, anchor_colour,
                             style, free_text, anchor_product=None,
                             restrict_colour=wanted_colour)

        anchor_product = main.products[0] if main.products else None
        anchor_info = {
            "source": "composed",
            "product_id": anchor_product.product_id if anchor_product else None,
            "name": anchor_product.name if anchor_product else None,
            "category_group": anchor_product.category_group if anchor_product else anchor_group,
            "colour_family": (anchor_product.colour_family if anchor_product
                              else anchor_colour),
            "base_colour": anchor_product.base_colour if anchor_product else None,
            "gender": gender,
        }

        if anchor_product is None:
            warnings.append(
                "No main garment in the catalog matched this request, so the rest "
                "of the look could not be coordinated against one.")

        # ---- 2. everything else, coordinated against it --------------
        sections = [main]
        for section in shape:
            if section.key == "main":
                continue
            if set(section.groups) <= set(exclude_categories):
                continue
            sections.append(self._section(
                section, gender, occasion,
                anchor_colour or (anchor_product.colour_family if anchor_product else None),
                style, free_text, anchor_product=anchor_product,
                exclude_categories=exclude_categories))

        # ---- 3. report thin sections -----------------------------------
        thin = [s.title for s in sections if s.confidence == "thin"]
        empty = [s.title for s in sections if not s.products and s.essential]
        if thin:
            warnings.append("Limited choice in: " + ", ".join(thin) + ".")
        if empty:
            warnings.append(
                "Nothing suitable in: " + ", ".join(empty)
                + ". These were left out rather than filled with a poor match.")

        kept = [s for s in sections if s.products]
        return ComposedOutfit(
            sections=kept,
            anchor=anchor_info,
            warnings=warnings,
            diagnostics={
                "sections_planned": len(shape),
                "sections_returned": len(kept),
                "gender": gender,
                "occasion": occasion,
                "composed_around": anchor_info["product_id"],
            },
        )

    # ------------------------------------------------------------------

    def _section(
        self,
        section: Section,
        gender: str | None,
        occasion: str | None,
        colour: str | None,
        style: str | None,
        free_text: str | None,
        anchor_product: Recommendation | None,
        exclude_categories: tuple[str, ...] = (),
        restrict_colour: str | None = None,
    ) -> ComposedSection:
        """Fill one section by asking the engine for exactly its categories."""
        groups = tuple(g for g in section.groups if g not in exclude_categories)
        if not groups:
            return ComposedSection(section.key, section.title, section.groups,
                                   essential=section.essential)

        # A filtered view is needed whenever the section narrows below its
        # category group - clothing always does, and footwear does too (the
        # catalog's 644 men's flip flops sit in the same group as its sandals).
        needs_view = section.clothing or bool(section.product_types) or bool(restrict_colour)
        anchor_id = (anchor_product.product_id
                     if anchor_product is not None and not section.clothing else None)
        engine = (self._clothing_engine(groups, section.product_types,
                                        restrict_colour, anchor_id)
                  if needs_view else self.engine)

        # The main garment anchors everything after it. For the main garment
        # itself there is no product yet, so the described colour anchors it.
        if restrict_colour:
            # The pool is already exactly that colour; comparing it against
            # itself would only reward tonal sameness.
            anchor = Anchor()
        elif anchor_product is not None and not section.clothing:
            anchor = Anchor(product_id=anchor_product.product_id)
        elif anchor_product is not None:
            anchor = Anchor(anchor_type=None, colour=anchor_product.colour_family)
        else:
            anchor = Anchor(anchor_type=None, colour=colour)

        def ask(view_engine) -> list[list[Recommendation]]:
            response = view_engine.recommend(LookRequest(
                anchor=anchor,
                preferences=Preferences(
                    occasion=occasion,
                    style=style,
                    gender=gender,
                    include_categories=groups,
                    exclude_categories=exclude_categories,
                    free_text=free_text,
                    max_per_category=section.limit,
                    limit=section.limit,
                ),
            ))
            return [list(result.recommendations) for result in response.categories
                    if result.category_group in groups]

        # One query per product type. Querying the whole group at once returns a
        # shortlist saturated by whichever type is most numerous - a women's
        # wedding "Main look" came back as 25 kurtas and zero sarees, because
        # kurtas outnumber sarees 4:1 and the shortlist truncates before a saree
        # is ever reached.
        per_group: list[list[Recommendation]] = []
        if section.product_types and needs_view:
            for product_type in section.product_types:
                sub = self._clothing_engine(groups, (product_type,),
                                            restrict_colour, anchor_id)
                if len(sub.store.complements) == 0:
                    continue
                per_group.extend(g for g in ask(sub) if g)
        else:
            per_group = [g for g in ask(engine) if g]
        # Round-robin by *product type*, not just by category group. Without
        # this, "Main look" for a women's wedding returns four kurtas because
        # kurtas outnumber sarees 4:1 - the shopper should see a saree and a
        # lehenga too, since those are what the section is offering.
        ranked = _interleave(per_group)
        by_type: dict[str, list[Recommendation]] = {}
        for item in ranked:
            by_type.setdefault(item.product_type, []).append(item)

        # Round-robin gives every product type an equal slot, which is right for
        # kurtas against sarees but wrong for T-shirts against shirts in a
        # formal look. A type has to be within reach of the best type on offer
        # to earn its slot.
        if by_type:
            best = max(group[0].score for group in by_type.values())
            by_type = {name: group for name, group in by_type.items()
                       if group[0].score >= best * TYPE_FLOOR}
        ordered = _interleave(list(by_type.values()))

        # A CategoryResult holds the pre-diversity ranked list, so without this
        # a section can show the same product name three times over - 38.9% of
        # the catalog shares a display name. Reuse the engine's own MMR rather
        # than writing a second one.
        candidates = [
            {"recommendation": r, "score": r.score, "brand": r.brand,
             "colour_family": r.colour_family, "product_type": r.product_type,
             "category_group": r.category_group}
            for r in ordered
        ]
        products = [c["recommendation"] for c in rerank(candidates, section.limit)]

        qualifying = sum(len(g) for g in per_group)
        if not products:
            confidence = "none"
        elif qualifying < THIN_SECTION:
            confidence = "thin"
        elif qualifying < 10:
            confidence = "moderate"
        else:
            confidence = "strong"

        note = section.note
        if confidence == "thin":
            note = (f"Only {qualifying} product{'' if qualifying == 1 else 's'} "
                    f"in the catalog fit here." + (f" {note}" if note else ""))

        return ComposedSection(
            key=section.key,
            title=title_for(section.key, occasion, section.title),
            groups=groups,
            products=products,
            confidence=confidence,
            note=note,
            essential=section.essential,
        )


def _interleave(groups: list[list]) -> list:
    """Round-robin across groups so one category cannot fill a whole section."""
    out: list = []
    for index in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if index < len(group):
                out.append(group[index])
    return out
