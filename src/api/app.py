"""FastAPI backend for AI Beauty & Fashion Match.

A thin layer over the Phase 2 engine. It resolves intent, calls the engine, and
shapes the result for a frontend. It does not rank, filter, score or select
anything itself - the engine remains the single source of truth for which
products come back, and the catalog remains the single source of truth for what
those products are.

    uvicorn src.api.app:app --reload --port 8000
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import replace

from dotenv import load_dotenv
from fastapi import FastAPI, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..engine.catalog_store import CatalogStore, UnknownProduct
from ..engine.engine import RecommendationEngine
from ..engine.schemas import Anchor, LookRequest, Preferences
from ..intent.extractor import IntentExtractor, intent_to_engine_request
from ..intent.llm import STATUS_LABELS
from ..intent.schema import NormalisedIntent, resolve_categories
from ..outfit.composer import OutfitComposer
from ..outfit.policy import requires_gender
from .explanations import explain
from .images import MEDIA_TYPE, ImageStore
from .models import (
    AiStatus,
    AnchorOut,
    CategoryOut,
    ErrorResponse,
    HealthResponse,
    ImageRef,
    IntentOut,
    RecommendationOut,
    RecommendRequest,
    OutfitSectionOut,
    RecommendResponse,
    ScoreComponentOut,
)

logger = logging.getLogger(__name__)

# Backend-only secrets. Loaded here so the LLM provider can be detected before
# any request arrives. Nothing from this file ever reaches the browser.
load_dotenv(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

VERSION = "0.5.0"
CACHE_SECONDS = 60 * 60 * 24 * 7
# How long an image request may wait for a first-time fetch. Long enough for the
# two mirror round-trips, short enough that a card never hangs; anything slower
# falls back to the thumbnail and is picked up by the background queue.
IMAGE_RESOLVE_SECONDS = 14.0


# --------------------------------------------------------------------------
# Composition root
# --------------------------------------------------------------------------


class Services:
    """Loaded once at import; the catalog and image store are read-only."""

    def __init__(self) -> None:
        self.error: str | None = None
        self.store: CatalogStore | None = None
        self.engine: RecommendationEngine | None = None
        self.images = ImageStore()
        self.extractor: IntentExtractor | None = None
        self.composer: OutfitComposer | None = None

        try:
            self.store = CatalogStore()
            self.engine = RecommendationEngine(store=self.store)
            self.composer = OutfitComposer(self.engine)
            self.extractor = IntentExtractor(
                known_groups=self.store.available_complement_groups,
                use_llm=os.environ.get("DISABLE_LLM", "").lower() not in {"1", "true", "yes"},
            )
        except Exception as exc:                        # catalog missing / unreadable
            self.error = (
                f"catalog could not be loaded ({exc}). "
                f"Run `python scripts/ingest_catalog.py` to build it.")
            logger.error(self.error)

    @property
    def ready(self) -> bool:
        return self.engine is not None


services = Services()

app = FastAPI(
    title="AI Beauty & Fashion Match",
    description=(
        "Describe a look you already have; get complementary real products from "
        "across fashion, accessories and beauty, each with the reasoning shown."
    ),
    version=VERSION,
)

# The React frontend is a later phase; allow it to develop against this locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173",
                   "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Errors - surfaced, never swallowed
# --------------------------------------------------------------------------


def _error(status: int, code: str, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(error=error, detail=detail, code=code).model_dump(),
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError):
    problems = []
    for item in exc.errors():
        location = ".".join(str(p) for p in item.get("loc", ()) if p != "body")
        problems.append(f"{location or 'request'}: {item.get('msg')}")
    return _error(
        422, "invalid_request", "The request could not be understood.",
        " ".join(problems) or "The request body did not match the expected shape.",
    )


@app.exception_handler(Exception)
def handle_unexpected(request: Request, exc: Exception):
    logger.exception("unhandled error on %s", request.url.path)
    return _error(
        500, "internal_error", "Something went wrong while building your look.",
        f"{type(exc).__name__}: {exc}",
    )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


def _ai_status(used_fallback: bool | None = None) -> AiStatus:
    """The language model's state, with the provider's own wording removed.

    `llm_status` carries a `reason` written by the provider. It is logged at
    startup and on every failure, and is deliberately not returned here.
    """
    raw = services.extractor.llm_status if services.extractor else {}
    state = raw.get("state", "unavailable")
    available = bool(raw.get("available"))
    # Never report "available" for a request that actually used the parser -
    # that would claim the model understood something it never saw.
    if used_fallback and state == "available":
        state = raw.get("last_failure") or "unavailable"
        available = False
    if state != "available":
        available = False
    return AiStatus(
        available=available,
        state=state if state in AiStatus.model_fields["state"].annotation.__args__
        else "unavailable",
        label=STATUS_LABELS.get(state, "AI Search Temporarily Unavailable"),
        using_fallback=(not available) if used_fallback is None else used_fallback,
        provider=raw.get("provider"),
        model=raw.get("model"),
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness plus what the service can actually do right now."""
    return HealthResponse(
        status="ok" if services.ready and services.images.available else "degraded",
        catalog_products=len(services.store) if services.store else 0,
        images_available=len(services.images),
        images_high_resolution=services.images.large_count,
        engine_ready=services.ready,
        llm=_ai_status(),
        version=VERSION,
    )


@app.post("/recommend", response_model=RecommendResponse,
          responses={422: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                     503: {"model": ErrorResponse}},
          tags=["recommendations"])
def recommend(request: RecommendRequest):
    """Natural language or structured input -> real catalog products."""
    if not services.ready:
        return _error(503, "engine_unavailable",
                      "The recommendation engine is not available.",
                      services.error or "The catalog has not been built.")

    started = time.perf_counter()
    notes: list[str] = []

    # ---- intent --------------------------------------------------------
    intent, intent_notes = _resolve_intent(request)
    notes.extend(intent_notes)

    # ---- a strongly gendered garment settles the gender ---------------
    # Sarees are 100% women's in this catalog, so pairing one with a men's tie
    # is a defect, not an open question. Only near-unanimous garments count, and
    # anything the user actually stated always wins.
    if intent.gender is None and intent.anchor_product_type:
        inferred = services.composer.gender_for_garment(intent.anchor_product_type)
        if inferred:
            intent = replace(intent, gender=inferred)
            notes.append(
                f"Assumed a {inferred}'s look because the catalog lists "
                f"{intent.anchor_product_type.lower()} as {inferred}'s wear. "
                f"Say otherwise and that will be used instead.")


    # ---- engine --------------------------------------------------------
    if request.product_id is not None:
        if not services.store.exists(request.product_id):
            return _error(
                404, "unknown_product",
                f"Product {request.product_id} is not in the catalog.",
                "Anchor products must be real catalog items. "
                "Describe the garment instead, or use a valid product id.")
        look = LookRequest(
            anchor=Anchor(product_id=request.product_id),
            preferences=Preferences(
                occasion=intent.occasion, style=intent.style, gender=intent.gender,
                preferred_colours=intent.preferred_colours,
                include_categories=intent.include_categories,
                exclude_categories=intent.exclude_categories,
                free_text=intent.free_text,
                max_per_category=request.max_per_category, limit=request.limit,
            ),
        )
    else:
        look = intent_to_engine_request(intent, request.limit, request.max_per_category)

    # ---- "what should I wear" is an outfit request ---------------------
    # "office wear for women" names no garment and no category, so there is
    # nothing to complement. Build a full look instead. A query that does name a
    # target ("red lipstick", "red shirt") keeps the product path.
    if (not intent.is_outfit and request.product_id is None
            and not intent.owns_anchor
            and not intent.anchor_category_group
            and not intent.include_categories
            and (intent.occasion or intent.style)):
        intent = replace(intent, intent_type="outfit")
        notes.append("No specific item was named, so a complete look was built "
                     "instead of accessories on their own.")

    # ---- outfit requests take the composition path -------------------
    if intent.is_outfit and request.product_id is None:
        return _compose_outfit(request, intent, notes, started)

    try:
        result = services.engine.recommend(look)
    except UnknownProduct as exc:
        return _error(404, "unknown_product", "That product is not in the catalog.", str(exc))

    # ---- the garment they asked for comes first -----------------------
    # "red kurta for men" is a request to see kurtas. Only when they already
    # own it ("I'm wearing a red saree") is it purely a complement request.
    primary: list = []
    primary_note = None
    # The user asked to see either a garment ("red kurta") or a category
    # ("perfume"). Either way it is the answer, not a complement, so it is
    # scored against the request and placed first.
    primary_group = intent.anchor_category_group
    if not primary_group and len(intent.include_categories) == 1:
        primary_group = intent.include_categories[0]

    if primary_group and not intent.owns_anchor and request.product_id is None:
        primary, primary_note = services.composer.primary_garment(
            product_type=intent.anchor_product_type,
            category_group=primary_group,
            colour=intent.colour,
            gender=intent.gender,
            occasion=intent.occasion,
            style=intent.style,
            free_text=request.query,
        )
        if primary_note:
            notes.append(primary_note)

    # The engine may also return the requested category as a complement. Showing
    # it twice would duplicate products and leave one section labelled "goes
    # with" when it is the answer, so the primary group is taken out of the
    # complement side.
    complement_categories = list(result.categories)
    complement_recommendations = list(result.recommendations)
    if primary:
        primary_group_name = primary[0].category_group
        already = {rec.product_id for rec in primary}
        complement_categories = [c for c in complement_categories
                                 if c.category_group != primary_group_name]
        complement_recommendations = [r for r in complement_recommendations
                                      if r.category_group != primary_group_name
                                      and r.product_id not in already]

    notes.extend(result.warnings)
    if not complement_recommendations and not primary:
        notes.append(
            "No products matched this request well enough to recommend. "
            "Nothing was returned rather than filling the list with poor matches.")

    return RecommendResponse(
        ai_status=_ai_status(intent.source != "llm"),
        query=request.query,
        intent=IntentOut(**intent.to_dict()),
        anchor=_anchor_out(result.resolved_anchor),
        recommendations=[
            _recommendation_out(
                rec, request.include_score_breakdown,
                role="primary" if rec in primary else "complement",
                occasion=intent.occasion, requested_colour=intent.colour)
            for rec in (*primary, *complement_recommendations)
        ],
        categories=([
            CategoryOut(
                category=primary[0].category_group,
                role="primary",
                affinity=1.0,
                why_considered=(
                    f"You asked for "
                    f"{(intent.anchor_type or primary[0].category_group.replace('_', ' '))}, "
                    f"so these come first."),
                confidence="strong" if len(primary) >= 3 else "thin",
                qualifying_candidates=len(primary),
                note=primary_note,
            )
        ] if primary else []) + [
            CategoryOut(
                category=category.category_group,
                affinity=round(category.affinity, 3),
                why_considered=category.why_considered,
                confidence=category.confidence,
                qualifying_candidates=category.candidates_after_filter,
                note=category.note,
            )
            for category in complement_categories
        ],
        notes=list(dict.fromkeys(notes)),
        meta={
            "catalog_products": len(services.store),
            "categories_considered": len(result.categories),
            "engine_latency_ms": result.diagnostics.get("latency_ms"),
            "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "intent_source": intent.source,
            "version": VERSION,
        },
    )


@app.get("/images/{product_id}.jpg", tags=["images"],
         responses={200: {"content": {MEDIA_TYPE: {}}}, 404: {"model": ErrorResponse}})
def product_image(
    product_id: int = Path(..., ge=0),
    size: str = Query("auto", pattern="^(auto|large|thumb)$"),
    v: str | None = Query(None, pattern="^(pending|thumb|[0-9]{2,5})$",
                          description="Cache key naming the served resolution."),
):
    """The catalog photograph for a product.

    `size=auto` (the default) serves the high-resolution file when one has been
    fetched for this product and the Phase 1 thumbnail otherwise.
    """
    if not services.images.available:
        return _error(503, "images_unavailable", "Product images are not available.",
                      services.images.reason or "The image store was not loaded.")
    # Resolve on demand: a product recommended before its photograph was
    # fetched still paints a real one, because the browser waits on this
    # request rather than on the recommendation.
    data = services.images.get(product_id, size, resolve=(v != "thumb"),
                               timeout=IMAGE_RESOLVE_SECONDS)
    if data is None:
        return _error(404, "image_not_found",
                      f"No image is stored for product {product_id}.",
                      "Only products in the built catalog have images.")
    # `immutable` is safe because `?v=` names the stored resolution: when a
    # product gains a larger file its URL changes, so a cached smaller version
    # cannot mask it. The ETag lets a client on the bare URL revalidate.
    etag = hashlib.md5(data).hexdigest()[:16]
    # A pending URL has no fixed content yet, so it must not be immutable.
    cache = (f"public, max-age={CACHE_SECONDS}, immutable"
             if v and v not in {"pending"}
             else "public, max-age=3600, must-revalidate")
    return Response(
        content=data, media_type=MEDIA_TYPE,
        headers={"Cache-Control": cache, "ETag": f'"{etag}"'},
    )


@app.get("/products/{product_id}", tags=["catalog"],
         responses={404: {"model": ErrorResponse}})
def product(product_id: int = Path(..., ge=0)):
    """A single catalog product, for resolving an anchor in the UI."""
    if not services.ready:
        return _error(503, "engine_unavailable", "The catalog is not available.",
                      services.error or "")
    try:
        row = services.store.get(product_id)
    except UnknownProduct as exc:
        return _error(404, "unknown_product",
                      f"Product {product_id} is not in the catalog.", str(exc))
    return {
        "product_id": int(row.product_id),
        "name": row["name"],
        "brand": row.brand if isinstance(row.brand, str) else None,
        "category": row.category_group,
        "product_type": row.product_type,
        "colour": row.base_colour,
        "colour_family": row.colour_family,
        "gender": row.gender,
        "occasion": row.occasion if bool(row.occasion_reliable) else None,
        "can_be_anchor": bool(row.can_be_anchor),
        "image": services.images.reference(product_id),
    }


@app.get("/categories", tags=["catalog"])
def categories(anchor_category: str | None = Query(None), occasion: str | None = Query(None)):
    """Complement categories the engine can recommend, with their affinity."""
    if not services.ready:
        return _error(503, "engine_unavailable", "The catalog is not available.",
                      services.error or "")
    from ..engine.affinity import ranked_categories
    from ..engine.occasion import normalise_occasion

    ranked = ranked_categories(
        anchor_category, normalise_occasion(occasion),
        services.store.available_complement_groups)
    return {
        "anchor_category": anchor_category,
        "occasion": normalise_occasion(occasion),
        "categories": [
            {"category": item.category_group, "affinity": round(item.score, 3),
             "why": item.explanation}
            for item in ranked
        ],
    }


@app.get("/catalog/browse", tags=["catalog"])
def browse(
    category: str | None = Query(None, description="A category_group from /categories"),
    domain: str | None = Query(None, pattern="^(apparel|accessory|footwear|beauty)$"),
    colour: str | None = Query(None, description="Colour family"),
    gender: str | None = Query(None, pattern="^(women|men|unisex)$"),
    anchors_only: bool = Query(False, description="Only garments that can anchor a look"),
    limit: int = Query(24, ge=1, le=60),
    offset: int = Query(0, ge=0),
):
    """Browse the catalog.

    Read-only and deliberately unscored: this lists products so a user can pick
    one to build a look around. It performs no ranking, no colour matching and
    no recommendation - that all stays in the engine, reached through
    /recommend with the chosen `product_id`.
    """
    if not services.ready:
        return _error(503, "engine_unavailable", "The catalog is not available.",
                      services.error or "")

    frame = services.store.df
    if anchors_only:
        frame = frame[frame.can_be_anchor]
    if category:
        frame = frame[frame.category_group == category]
    if domain:
        frame = frame[frame.domain == domain]
    if colour:
        frame = frame[frame.colour_family == colour]
    if gender:
        frame = frame[frame.gender.isin([gender, "unisex"])]
    frame = frame[frame.age_group == "adult"]

    total = len(frame)
    # Products with a high-resolution image first, then by id so paging is
    # stable. This is presentation order for a browse grid, not a ranking.
    ids = frame.product_id.tolist()
    has_large = services.images.has_large
    ordered = sorted(ids, key=lambda pid: (not has_large(pid), pid))
    page = ordered[offset:offset + limit]

    products = []
    for product_id in page:
        row = services.store.get(product_id)
        products.append({
            "product_id": int(row.product_id),
            "name": row["name"],
            "brand": row.brand if isinstance(row.brand, str) else None,
            "category": row.category_group,
            "product_type": row.product_type,
            "colour": row.base_colour,
            "colour_family": row.colour_family,
            "can_be_anchor": bool(row.can_be_anchor),
            "image": services.images.reference(product_id),
        })

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "filters": {"category": category, "domain": domain, "colour": colour,
                    "gender": gender, "anchors_only": anchors_only},
        "products": products,
    }


def _compose_outfit(request: RecommendRequest, intent: NormalisedIntent,
                    notes: list[str], started: float) -> RecommendResponse:
    """Build a whole look rather than a list of complements.

    Gender is required: a look that mixes men's and women's clothing is never
    the right answer, so when it was not stated the client is told to ask
    instead of being handed a guess.
    """
    needs_gender = requires_gender(intent.gender)
    if needs_gender:
        notes.append(
            "This looks like a request for a whole outfit, but you have not said "
            "who it is for. Choose men's or women's and the look will be built "
            "for that - mixing the two is never right.")
        return RecommendResponse(
            query=request.query,
            intent=IntentOut(**intent.to_dict()),
            anchor=AnchorOut(source="pending_gender",
                             category=intent.anchor_category_group,
                             colour_family=intent.colour),
            recommendations=[], categories=[], outfit=None, needs_gender=True,
            notes=list(dict.fromkeys(notes)),
            meta={"catalog_products": len(services.store),
                  "intent_source": intent.source,
                  "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                  "version": VERSION},
        )

    outfit = services.composer.compose(
        gender=intent.gender,
        occasion=intent.occasion,
        anchor_group=intent.anchor_category_group,
        anchor_colour=intent.colour,
        style=intent.style,
        free_text=intent.free_text,
        exclude_categories=intent.exclude_categories,
    )
    notes.extend(outfit.warnings)
    if intent.time_context:
        notes.append(
            f"Noted '{intent.time_context}' as context. This catalog carries no "
            f"stock or delivery information, so nothing here reflects availability.")

    main_ids = {p.product_id for section in outfit.sections
                if section.key == "main" for p in section.products}
    flat = [_recommendation_out(
                p, request.include_score_breakdown,
                role="primary" if p.product_id in main_ids else "complement",
                occasion=intent.occasion, requested_colour=intent.colour)
            for p in outfit.all_products]
    if not flat:
        notes.append(
            "No coherent look could be assembled from the catalog for this "
            "request. Nothing was returned rather than filling the page.")

    return RecommendResponse(
        ai_status=_ai_status(intent.source != "llm"),
        query=request.query,
        intent=IntentOut(**intent.to_dict()),
        anchor=AnchorOut(
            source=outfit.anchor["source"],
            product_id=outfit.anchor["product_id"],
            name=outfit.anchor["name"],
            category=outfit.anchor["category_group"],
            colour=outfit.anchor["base_colour"],
            colour_family=outfit.anchor["colour_family"],
            image=_image_ref(outfit.anchor["product_id"])
            if outfit.anchor["product_id"] is not None else None,
        ),
        recommendations=flat,
        categories=[],
        outfit=[
            OutfitSectionOut(
                key=section.key, title=section.title,
                categories=list(section.groups), confidence=section.confidence,
                essential=section.essential, note=section.note,
                products=[_recommendation_out(
                              p, request.include_score_breakdown,
                              role="primary" if section.key == "main" else "complement",
                              occasion=intent.occasion,
                              requested_colour=intent.colour)
                          for p in section.products],
            )
            for section in outfit.sections
        ],
        needs_gender=False,
        notes=list(dict.fromkeys(notes)),
        meta={
            "catalog_products": len(services.store),
            "intent_source": intent.source,
            "outfit_sections": len(outfit.sections),
            "composed_around": outfit.diagnostics.get("composed_around"),
            "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "version": VERSION,
        },
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _resolve_intent(request: RecommendRequest) -> tuple[NormalisedIntent, list[str]]:
    """Combine extracted and explicitly structured intent.

    Structured fields always win: a UI that lets the user correct an extracted
    value must not have that correction overwritten by the parser.
    """
    notes: list[str] = []
    known = services.store.available_complement_groups

    if request.query and request.query.strip():
        extractor = services.extractor
        if not request.use_llm:
            extractor = IntentExtractor(known_groups=known, use_llm=False)
            notes.append("Language model bypassed at the caller's request.")
        intent, extraction_notes = extractor.extract(request.query)
        notes.extend(extraction_notes)
    else:
        intent = NormalisedIntent(source="structured")

    overrides: dict = {}
    rejected = list(intent.rejected)

    if request.anchor_type:
        from ..engine.catalog_store import resolve_anchor_type
        group, _ = resolve_anchor_type(request.anchor_type)
        if group:
            overrides["anchor_type"] = request.anchor_type
            overrides["anchor_category_group"] = group
        else:
            rejected.append(f"garment '{request.anchor_type}'")

    if request.colour:
        from ..engine.catalog_store import resolve_colour
        colour = resolve_colour(request.colour)
        if colour:
            overrides["colour"] = colour
        else:
            rejected.append(f"colour '{request.colour}'")

    if request.occasion:
        from ..engine.occasion import normalise_occasion
        occasion = normalise_occasion(request.occasion)
        if occasion:
            overrides["occasion"] = occasion
        else:
            rejected.append(f"occasion '{request.occasion}'")

    if request.style:
        from ..engine.scoring import normalise_style
        style = normalise_style(request.style)
        if style:
            overrides["style"] = style
        else:
            rejected.append(f"style '{request.style}'")

    if request.gender:
        overrides["gender"] = request.gender

    if request.preferred_colours:
        from ..engine.catalog_store import resolve_colour
        resolved = []
        for raw in request.preferred_colours:
            value = resolve_colour(raw)
            if value:
                resolved.append(value)
            else:
                rejected.append(f"preferred colour '{raw}'")
        if resolved:
            overrides["preferred_colours"] = tuple(dict.fromkeys(resolved))

    for field, values in (("include_categories", request.include_categories),
                          ("exclude_categories", request.exclude_categories)):
        if values:
            resolved, bad = resolve_categories(values, known)
            rejected.extend(bad)
            if resolved:
                overrides[field] = resolved

    if request.query is None or not request.query.strip():
        overrides["source"] = "structured"

    already_noted = set(intent.rejected)
    if overrides or set(rejected) != already_noted:
        from dataclasses import replace
        intent = replace(intent, **overrides, rejected=tuple(dict.fromkeys(rejected)))

    # The extractor already reported anything it rejected; only mention values
    # the structured fields added on top, so the note is not duplicated.
    newly_rejected = [r for r in intent.rejected if r not in already_noted]
    if newly_rejected:
        notes.append("Ignored values the catalog does not recognise: "
                     + ", ".join(newly_rejected) + ".")

    return intent, notes


def _anchor_out(resolved: dict) -> AnchorOut:
    product_id = resolved.get("product_id")
    return AnchorOut(
        source=resolved.get("source", "unknown"),
        product_id=product_id,
        name=resolved.get("name"),
        category=resolved.get("category_group"),
        product_type=resolved.get("product_type"),
        colour=resolved.get("base_colour"),
        colour_family=resolved.get("colour_family"),
        image=_image_ref(product_id) if product_id is not None else None,
    )


def _image_ref(product_id: int) -> ImageRef | None:
    reference = services.images.reference(product_id)
    return ImageRef(**reference) if reference else None


def _recommendation_out(rec, include_breakdown: bool, *, role: str = "complement",
                        occasion: str | None = None,
                        requested_colour: str | None = None) -> RecommendationOut:
    return RecommendationOut(
        product_id=rec.product_id,
        name=rec.name,
        brand=rec.brand,
        category=rec.category_group,
        product_type=rec.product_type,
        colour=rec.base_colour,
        colour_family=rec.colour_family,
        score=round(rec.score, 4),
        image=_image_ref(rec.product_id),
        reasons=explain(rec, role=role, occasion=occasion,
                        requested_colour=requested_colour),
        score_breakdown=[
            ScoreComponentOut(
                component=component.name,
                raw=round(component.raw, 4),
                weight=component.weight,
                contribution=round(component.contribution, 4),
                detail=component.detail,
            )
            for component in rec.components
        ] if include_breakdown else None,
    )
