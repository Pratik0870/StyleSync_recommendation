"""Diversity re-ranking.

The problem this solves is concrete: 38.9% of catalog products share a display
name with another product, and a top-scoring pool routinely contains 40 near
-identical items - "Lucera Women Silver Earrings" covers 82 distinct designs
that score almost identically. Returning ten of them is technically the highest
-scoring answer and a useless one.

The mechanism is greedy Maximal Marginal Relevance with an explicit, inspectable
penalty rather than an opaque similarity kernel:

    adjusted = score - lambda * penalty(candidate, already_selected)

where the penalty accumulates from repeated brand, repeated colour family and
repeated product type. MMR was chosen over clustering because it is O(n*k), it
needs no tuning beyond one lambda, and - most importantly here - the reason a
product was demoted can be stated in words.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiversityConfig:
    lambda_: float = 0.35          # how hard repetition is punished
    brand_penalty: float = 0.55
    colour_penalty: float = 0.30
    product_type_penalty: float = 0.35
    max_per_brand: int = 2         # hard cap regardless of score


DEFAULT_DIVERSITY = DiversityConfig()


@dataclass
class _Selected:
    brands: dict[str, int]
    colours: dict[str, int]
    types: dict[str, int]


def _penalty(candidate: dict, seen: _Selected, config: DiversityConfig) -> tuple[float, list[str]]:
    penalty, notes = 0.0, []

    brand = candidate.get("brand")
    if brand and seen.brands.get(brand):
        penalty += config.brand_penalty * seen.brands[brand]
        notes.append(f"{seen.brands[brand]} already from {brand}")

    colour = candidate.get("colour_family")
    if colour and seen.colours.get(colour):
        penalty += config.colour_penalty * seen.colours[colour]
        notes.append(f"{seen.colours[colour]} already in {colour}")

    ptype = candidate.get("product_type")
    if ptype and seen.types.get(ptype):
        penalty += config.product_type_penalty * seen.types[ptype]
        notes.append(f"{seen.types[ptype]} already of type {ptype}")

    return penalty, notes


def rerank(
    candidates: list[dict],
    limit: int,
    config: DiversityConfig = DEFAULT_DIVERSITY,
) -> list[dict]:
    """Greedy MMR over scored candidates.

    Each candidate is a dict with at least `score`, `brand`, `colour_family`
    and `product_type`. Returns at most `limit` items, each annotated with
    `diversity_penalty` and `diversity_note`.
    """
    if not candidates:
        return []

    pool = sorted(candidates, key=lambda c: -c["score"])
    seen = _Selected({}, {}, {})
    chosen: list[dict] = []

    while pool and len(chosen) < limit:
        best_index, best_adjusted, best_notes = None, None, []
        for index, candidate in enumerate(pool):
            brand = candidate.get("brand")
            if brand and seen.brands.get(brand, 0) >= config.max_per_brand:
                continue
            penalty, notes = _penalty(candidate, seen, config)
            adjusted = candidate["score"] - config.lambda_ * penalty
            if best_adjusted is None or adjusted > best_adjusted:
                best_index, best_adjusted, best_notes = index, adjusted, notes

        if best_index is None:      # everything left is brand-capped
            break

        picked = dict(pool.pop(best_index))
        picked["diversity_penalty"] = round(picked["score"] - best_adjusted, 4)
        picked["diversity_note"] = "; ".join(best_notes) if best_notes else None
        chosen.append(picked)

        if picked.get("brand"):
            seen.brands[picked["brand"]] = seen.brands.get(picked["brand"], 0) + 1
        if picked.get("colour_family"):
            seen.colours[picked["colour_family"]] = seen.colours.get(picked["colour_family"], 0) + 1
        if picked.get("product_type"):
            seen.types[picked["product_type"]] = seen.types.get(picked["product_type"], 0) + 1

    return chosen


def measure(items: list[dict]) -> dict:
    """Diversity of a result set, for evaluation."""
    if not items:
        return {"brands": 0, "colours": 0, "product_types": 0, "categories": 0,
                "max_share_one_brand": 0.0}
    def distinct(key):
        return len({i.get(key) for i in items if i.get(key)})
    brands = [i.get("brand") for i in items if i.get("brand")]
    top_brand = max((brands.count(b) for b in set(brands)), default=0)
    return {
        "brands": distinct("brand"),
        "colours": distinct("colour_family"),
        "product_types": distinct("product_type"),
        "categories": distinct("category_group"),
        "max_share_one_brand": round(top_brand / len(items), 3) if items else 0.0,
    }
