"""Public API request and response models.

These are the frontend's contract. They deliberately expose product data,
scores, reasons and category context - and deliberately do not expose engine
internals such as raw component weights, candidate pool internals or module
structure. `include_score_breakdown` opts into the full decomposition for
debugging without making it the default payload.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_QUERY_CHARS = 2000


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


class RecommendRequest(BaseModel):
    """Natural language, structured fields, or both.

    Structured fields win over anything extracted from `query`, so a UI can let
    a user refine an extracted intent without re-parsing prose.
    """

    query: str | None = Field(
        None, max_length=MAX_QUERY_CHARS,
        description="Natural language request, e.g. \"I'm wearing a black saree "
                    "to a wedding. I want an elegant look.\"")
    product_id: int | None = Field(
        None, description="Anchor an existing catalog product instead of describing one.")
    anchor_type: str | None = Field(None, description="Garment the user already has.")
    colour: str | None = Field(None, description="Colour of that garment.")
    occasion: str | None = None
    style: str | None = None
    gender: Literal["women", "men", "unisex"] | None = None
    preferred_colours: list[str] = Field(default_factory=list)
    include_categories: list[str] = Field(default_factory=list)
    exclude_categories: list[str] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=50)
    max_per_category: int = Field(2, ge=1, le=10)
    include_score_breakdown: bool = Field(
        False, description="Return the full per-component score decomposition.")
    use_llm: bool = Field(
        True, description="Set false to force the deterministic parser.")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _needs_something_to_work_with(self):
        if self.query and self.query.strip():
            return self
        if any([self.product_id, self.anchor_type, self.colour, self.occasion,
                self.style, self.preferred_colours, self.include_categories]):
            return self
        raise ValueError(
            "Provide a `query`, or at least one structured field "
            "(product_id, anchor_type, colour, occasion, style, "
            "preferred_colours, include_categories).")


# --------------------------------------------------------------------------
# Response
# --------------------------------------------------------------------------


class ImageRef(BaseModel):
    """What the client is actually being given, stated honestly.

    `width`/`height` are None while `resolution` is "pending": the file has not
    been fetched yet, and inventing dimensions for it would be a guess.
    """

    url: str
    width: int | None = None
    height: int | None = None
    media_type: str
    resolution: Literal["large", "pending", "thumb"] = "thumb"
    detail: Literal["sharp", "soft", "low", "unknown"] = "unknown"


class ScoreComponentOut(BaseModel):
    component: str
    raw: float
    weight: float
    contribution: float
    detail: str


class RecommendationOut(BaseModel):
    product_id: int
    name: str
    brand: str | None
    category: str
    product_type: str
    colour: str
    colour_family: str
    score: float
    image: ImageRef | None
    reasons: list[str]
    score_breakdown: list[ScoreComponentOut] | None = None


class CategoryOut(BaseModel):
    """One group of results.

    `role` separates the item that was asked for from the things that go with
    it. Their scores answer different questions - "does this match your
    request?" against "does this go with it?" - so a client must not compare
    the two numbers or interleave the groups.
    """

    category: str
    role: Literal["primary", "complement"] = "complement"
    affinity: float
    why_considered: str
    confidence: Literal["strong", "moderate", "thin", "none"]
    qualifying_candidates: int
    note: str | None = None


class OutfitSectionOut(BaseModel):
    key: str
    title: str
    categories: list[str]
    confidence: Literal["strong", "moderate", "thin", "none"]
    essential: bool
    note: str | None = None
    products: list[RecommendationOut]


class IntentOut(BaseModel):
    intent_type: Literal["product", "outfit"] = "product"
    owns_anchor: bool = False
    time_context: str | None = None
    gender_explicit: bool = False
    anchor_type: str | None
    anchor_category: str | None
    anchor_product_type: str | None = None
    colour: str | None
    occasion: str | None
    style: str | None
    gender: str | None
    preferred_colours: list[str]
    include_categories: list[str]
    exclude_categories: list[str]
    descriptors: str | None
    source: Literal["llm", "fallback", "structured"]
    rejected: list[str]


class AnchorOut(BaseModel):
    source: str
    product_id: int | None = None
    name: str | None = None
    category: str | None = None
    product_type: str | None = None
    colour: str | None = None
    colour_family: str | None = None
    image: ImageRef | None = None


class AiStatus(BaseModel):
    """What the language model can do right now, safe to show anywhere.

    There is deliberately no field for the provider's own error text: quota
    tables, request URLs and stack traces belong in the server log, not in a
    browser. `state` is enough for a client to react to.
    """

    available: bool = False
    state: Literal["available", "quota", "auth", "network", "timeout",
                   "unavailable", "not_configured"] = "unavailable"
    label: str = "AI Search Temporarily Unavailable"
    using_fallback: bool = True
    provider: str | None = None
    model: str | None = None


class RecommendResponse(BaseModel):
    query: str | None
    intent: IntentOut
    anchor: AnchorOut
    recommendations: list[RecommendationOut]
    categories: list[CategoryOut]
    outfit: list[OutfitSectionOut] | None = Field(
        None, description="Present only for an outfit request: the look, in the "
                          "order it is assembled. `recommendations` holds the "
                          "same products flattened.")
    ai_status: AiStatus = Field(
        default_factory=AiStatus,
        description="Whether the language model handled this query or the "
                    "deterministic parser did.")
    needs_gender: bool = Field(
        False, description="An outfit was asked for without a gender. The client "
                           "should ask before showing a look, since a mixed "
                           "men's/women's outfit is never correct.")
    notes: list[str] = Field(
        default_factory=list,
        description="Things the user should know: fallbacks used, values ignored, "
                    "categories that were too thin to answer well.")
    meta: dict


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    catalog_products: int
    images_available: int
    images_high_resolution: int = 0
    engine_ready: bool
    llm: AiStatus
    version: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    code: str
