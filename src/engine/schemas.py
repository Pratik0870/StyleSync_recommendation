"""Contracts for the recommendation engine.

Plain dataclasses, no framework. These are the deterministic interface that a
Phase 3 LLM will populate - the LLM will fill a `LookRequest` and nothing else.

Note what `LookRequest` cannot express: there is no field that can hold a
product id, name, or any catalog content for a *recommended* item. An anchor may
reference a catalog product by id, but that id is resolved against the real
catalog and rejected if unknown. Recommended products can therefore only ever
originate from the catalog itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["strong", "moderate", "thin", "none"]


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """What the user already has.

    Either `product_id` (an item in our catalog) or a described item
    (`anchor_type` + `colour`). Described anchors are resolved to catalog
    vocabulary before scoring.
    """

    product_id: int | None = None
    anchor_type: str | None = None        # free text, e.g. "saree", "dress"
    colour: str | None = None             # free text, e.g. "black", "navy blue"

    def is_empty(self) -> bool:
        return self.product_id is None and not self.anchor_type and not self.colour


@dataclass(frozen=True)
class Preferences:
    """Everything the user asked for beyond the anchor itself."""

    occasion: str | None = None                       # "wedding", "party", ...
    style: str | None = None                          # "elegant", "minimal", ...
    gender: str | None = None                         # "women" | "men" | "unisex"
    preferred_colours: tuple[str, ...] = ()
    include_categories: tuple[str, ...] = ()          # restrict to these groups
    exclude_categories: tuple[str, ...] = ()          # never return these groups
    free_text: str | None = None                      # residual descriptor terms
    max_per_category: int = 2
    limit: int = 12


@dataclass(frozen=True)
class LookRequest:
    anchor: Anchor
    preferences: Preferences = field(default_factory=Preferences)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreComponent:
    """One named, weighted contribution to a product's score."""

    name: str
    raw: float          # 0..1 before weighting
    weight: float
    detail: str         # human-readable justification

    @property
    def contribution(self) -> float:
        return self.raw * self.weight


@dataclass(frozen=True)
class Recommendation:
    product_id: int
    name: str
    brand: str | None
    category_group: str
    product_type: str
    colour_family: str
    base_colour: str
    score: float
    components: tuple[ScoreComponent, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "brand": self.brand,
            "category_group": self.category_group,
            "product_type": self.product_type,
            "colour_family": self.colour_family,
            "base_colour": self.base_colour,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "score_breakdown": [
                {
                    "component": c.name,
                    "raw": round(c.raw, 4),
                    "weight": c.weight,
                    "contribution": round(c.contribution, 4),
                    "detail": c.detail,
                }
                for c in self.components
            ],
        }


@dataclass(frozen=True)
class CategoryResult:
    """Per-category outcome, including the honest 'we don't have enough' case."""

    category_group: str
    affinity: float
    why_considered: str
    candidates_before_filter: int
    candidates_after_filter: int
    confidence: Confidence
    recommendations: tuple[Recommendation, ...]
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "category_group": self.category_group,
            "affinity": round(self.affinity, 3),
            "why_considered": self.why_considered,
            "candidate_pool": {
                "before_filters": self.candidates_before_filter,
                "after_filters": self.candidates_after_filter,
            },
            "confidence": self.confidence,
            "note": self.note,
            "recommendations": [r.to_dict() for r in self.recommendations],
        }


@dataclass(frozen=True)
class LookResponse:
    resolved_anchor: dict
    categories: tuple[CategoryResult, ...]
    recommendations: tuple[Recommendation, ...]      # flattened, ranked
    warnings: tuple[str, ...]
    diagnostics: dict

    @property
    def is_empty(self) -> bool:
        return not self.recommendations

    def to_dict(self) -> dict:
        return {
            "resolved_anchor": self.resolved_anchor,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "categories": [c.to_dict() for c in self.categories],
            "warnings": list(self.warnings),
            "diagnostics": self.diagnostics,
        }


class EngineError(Exception):
    """Raised when a request cannot be served at all (vs. served with warnings)."""
