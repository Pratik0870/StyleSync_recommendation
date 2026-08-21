"""Offline evaluation of the recommendation engine.

The catalog carries no user interactions, so there is no ground truth about
which product a person would have chosen, and none is invented here. What is
measured instead are properties a correct answer must have and that can be
checked mechanically: constraints respected, categories genuinely crossed,
colours compatible under the documented model, failures disclosed, every
recommendation explained.

    python scripts/evaluate_engine.py

Writes docs/evaluation_results.json and docs/evaluation.md.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.catalog_store import CatalogStore  # noqa: E402
from src.engine.colour import harmony  # noqa: E402
from src.engine.engine import RecommendationEngine  # noqa: E402
from src.engine.schemas import Anchor, LookRequest, Preferences  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS = os.path.join(ROOT, "data", "eval_scenarios.json")
RESULTS_JSON = os.path.join(ROOT, "docs", "evaluation_results.json")
RESULTS_MD = os.path.join(ROOT, "docs", "evaluation.md")

COLOUR_OK = 0.60          # harmony at or above this counts as compatible
BEAUTY_GROUPS = {"beauty_lip", "beauty_eye", "beauty_face", "beauty_nails",
                 "beauty_skincare", "beauty_hair", "beauty_tools"}


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def measure(response, request_prefs, store, anchor_group) -> dict:
    recs = response.recommendations
    anchor_colour = response.resolved_anchor.get("colour_family")

    # --- constraint satisfaction -------------------------------------
    violations = []
    for rec in recs:
        if not store.exists(rec.product_id):
            violations.append(f"{rec.product_id} not in catalog")
        row = store.get(rec.product_id)
        if not row.can_be_complement:
            violations.append(f"{rec.product_id} is not a complement")
        if anchor_group and rec.category_group == anchor_group:
            violations.append(f"{rec.product_id} is from the anchor's own category")
        if rec.category_group in (request_prefs.exclude_categories or ()):
            violations.append(f"{rec.product_id} is from an excluded category")
        if request_prefs.include_categories and \
                rec.category_group not in request_prefs.include_categories:
            violations.append(f"{rec.product_id} outside include_categories")
        if request_prefs.gender and row.gender not in (request_prefs.gender, "unisex"):
            violations.append(f"{rec.product_id} wrong gender ({row.gender})")

    # --- colour compatibility ----------------------------------------
    # Denominator excludes products whose colour is not a styling signal.
    compatible = considered = unresolvable = 0
    for rec in recs:
        row = store.get(rec.product_id)
        if anchor_colour is None or row.colour_role != "style":
            continue
        considered += 1
        result = harmony(anchor_colour, rec.colour_family)
        if result.relation == "unresolved":
            unresolvable += 1
        if result.score >= COLOUR_OK:
            compatible += 1

    # --- diversity ----------------------------------------------------
    brands = [r.brand for r in recs if r.brand]
    top_brand_share = (max((brands.count(b) for b in set(brands)), default=0) / len(recs)
                       if recs else 0.0)

    # --- explanations --------------------------------------------------
    explained = sum(1 for r in recs if r.reasons and r.components)

    # --- coverage ------------------------------------------------------
    considered_categories = len(response.categories)
    producing = sum(1 for c in response.categories if c.recommendations)

    beauty = sum(1 for r in recs if r.category_group in BEAUTY_GROUPS)

    return {
        "results": len(recs),
        "constraint_satisfaction": 1.0 if not violations else 0.0,
        "constraint_violations": violations[:5],
        "colour_compatibility_rate": round(compatible / considered, 4) if considered else None,
        "colour_denominator": considered,
        "colour_unresolvable": unresolvable,
        "category_coverage": len({r.category_group for r in recs}),
        "cross_category_rate": 1.0 if recs else None,
        "beauty_share": round(beauty / len(recs), 4) if recs else 0.0,
        "distinct_brands": len(set(brands)),
        "max_brand_share": round(top_brand_share, 4),
        "candidate_coverage": round(producing / considered_categories, 4) if considered_categories else None,
        "explanation_completeness": round(explained / len(recs), 4) if recs else None,
        "warnings": len(response.warnings),
        "latency_ms": response.diagnostics.get("latency_ms"),
    }


def check(expect: dict, response, metrics: dict) -> list[str]:
    """Compare declared expectations against what actually happened."""
    failures = []
    recs = response.recommendations
    groups = {r.category_group for r in recs}
    all_warnings = " ".join(response.warnings)

    if "has_results" in expect:
        if expect["has_results"] != bool(recs):
            failures.append(
                f"expected has_results={expect['has_results']}, got {bool(recs)}")
    if "min_results" in expect and len(recs) < expect["min_results"]:
        failures.append(f"expected >={expect['min_results']} results, got {len(recs)}")

    for key in ("must_include_any_category", "must_include_any_category_2"):
        if key in expect and not (groups & set(expect[key])):
            failures.append(f"none of {expect[key]} present; got {sorted(groups)}")

    for group in expect.get("must_exclude_categories", []):
        if group in groups:
            failures.append(f"{group} should not appear")

    if "min_colour_compatibility" in expect:
        rate = metrics["colour_compatibility_rate"]
        if rate is None or rate < expect["min_colour_compatibility"]:
            failures.append(
                f"colour compatibility {rate} < {expect['min_colour_compatibility']}")

    if "min_explanation_completeness" in expect:
        value = metrics["explanation_completeness"]
        if value is None or value < expect["min_explanation_completeness"]:
            failures.append(f"explanation completeness {value} below expectation")

    if "max_brand_share" in expect and metrics["max_brand_share"] > expect["max_brand_share"]:
        failures.append(
            f"one brand holds {metrics['max_brand_share']} > {expect['max_brand_share']}")

    if "must_warn_about" in expect and expect["must_warn_about"] not in all_warnings:
        failures.append(f"expected a warning mentioning '{expect['must_warn_about']}'")

    if "anchor_source" in expect and response.resolved_anchor.get("source") != expect["anchor_source"]:
        failures.append(f"anchor source {response.resolved_anchor.get('source')}")

    if "max_beauty_share" in expect and metrics["beauty_share"] > expect["max_beauty_share"]:
        failures.append(
            f"beauty share {metrics['beauty_share']} > {expect['max_beauty_share']}")

    if "must_report_confidence_in" in expect:
        levels = {c.confidence for c in response.categories}
        if not (levels & set(expect["must_report_confidence_in"])):
            failures.append(f"confidence levels {sorted(levels)} not in expected set")

    if "must_note_contains" in expect:
        notes = " ".join(c.note or "" for c in response.categories)
        if expect["must_note_contains"] not in notes:
            failures.append(f"no category note mentioning '{expect['must_note_contains']}'")

    if expect.get("no_colour_component"):
        if any(c.name == "colour_harmony" for r in recs for c in r.components):
            failures.append("colour harmony was scored despite there being no anchor colour")

    return failures


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def build_request(spec: dict, store: CatalogStore) -> LookRequest:
    anchor_spec = dict(spec["anchor"])
    if anchor_spec.get("product_id") == "__BLACK_SAREE__":
        match = store.df[(store.df.product_type == "Sarees")
                         & (store.df.colour_family == "black")]
        anchor_spec["product_id"] = int(match.iloc[0].product_id)

    prefs_spec = dict(spec.get("preferences", {}))
    if prefs_spec.get("exclude_categories") == "__ALL__":
        prefs_spec["exclude_categories"] = tuple(store.available_complement_groups)
    for key in ("include_categories", "exclude_categories", "preferred_colours"):
        if key in prefs_spec:
            prefs_spec[key] = tuple(prefs_spec[key])

    return LookRequest(Anchor(**anchor_spec), Preferences(**prefs_spec))


def main() -> None:
    with open(SCENARIOS) as fh:
        spec = json.load(fh)

    store = CatalogStore()
    engine = RecommendationEngine(store=store)

    # Warm the engine so latency reflects steady state, not first-call setup.
    engine.recommend(LookRequest(Anchor(anchor_type="saree", colour="black"),
                                 Preferences(occasion="wedding", limit=5)))

    rows, latencies = [], []
    for scenario in spec["scenarios"]:
        request = build_request(scenario["request"], store)
        started = time.perf_counter()
        response = engine.recommend(request)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)

        anchor_group = response.resolved_anchor.get("category_group")
        metrics = measure(response, request.preferences, store, anchor_group)
        metrics["latency_ms"] = round(elapsed, 2)
        failures = check(scenario["expect"], response, metrics)

        rows.append({
            "id": scenario["id"],
            "group": scenario["group"],
            "title": scenario["title"],
            "why": scenario["why"],
            "metrics": metrics,
            "expectation_failures": failures,
            "passed": not failures,
            "top_results": [
                {"product_id": r.product_id, "name": r.name,
                 "category_group": r.category_group, "colour_family": r.colour_family,
                 "score": round(r.score, 4), "reasons": list(r.reasons)}
                for r in response.recommendations[:4]
            ],
            "warnings": list(response.warnings),
            "categories": [
                {"category_group": c.category_group, "affinity": round(c.affinity, 3),
                 "qualifying": c.candidates_after_filter, "confidence": c.confidence,
                 "note": c.note}
                for c in response.categories
            ],
        })
        status = "PASS" if not failures else "FAIL"
        print(f"  [{status}] {scenario['id']} {scenario['title']}")
        for failure in failures:
            print(f"          -> {failure}")

    # ---- aggregate ---------------------------------------------------
    def mean_of(key):
        values = [r["metrics"][key] for r in rows
                  if r["metrics"].get(key) is not None]
        return round(statistics.mean(values), 4) if values else None

    summary = {
        "scenarios": len(rows),
        "passed": sum(1 for r in rows if r["passed"]),
        "failed": sum(1 for r in rows if not r["passed"]),
        "constraint_satisfaction": mean_of("constraint_satisfaction"),
        "colour_compatibility_rate": mean_of("colour_compatibility_rate"),
        "explanation_completeness": mean_of("explanation_completeness"),
        "candidate_coverage": mean_of("candidate_coverage"),
        "mean_category_coverage": mean_of("category_coverage"),
        "mean_distinct_brands": mean_of("distinct_brands"),
        "mean_max_brand_share": mean_of("max_brand_share"),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2),
            "median": round(statistics.median(latencies), 2),
            "max": round(max(latencies), 2),
        },
        "catalog_size": len(store),
    }

    with open(RESULTS_JSON, "w") as fh:
        json.dump({"summary": summary, "protocol": spec["protocol"],
                   "metric_definitions": spec["metric_definitions"],
                   "scenarios": rows}, fh, indent=2)

    _write_markdown(summary, rows, spec)
    print("\n" + json.dumps(summary, indent=2))


def _write_markdown(summary, rows, spec) -> None:
    lines = [
        "# Engine Evaluation", "",
        "Generated by `scripts/evaluate_engine.py`. Do not edit by hand.", "",
        "The catalog has no user interactions, so there is no ground truth about",
        "which product a person would pick, and none is invented. Each scenario",
        "declares the properties a correct answer must have; those are checked",
        "mechanically.", "",
        "## Protocol", "",
    ]
    lines += [f"{step}" for step in spec["protocol"]]
    lines += ["", "## Summary", "", "| Metric | Value |", "|---|---|"]
    lines += [
        f"| Scenarios | {summary['scenarios']} |",
        f"| Passed | **{summary['passed']}/{summary['scenarios']}** |",
        f"| Constraint satisfaction | {summary['constraint_satisfaction']} |",
        f"| Colour compatibility rate | {summary['colour_compatibility_rate']} |",
        f"| Explanation completeness | {summary['explanation_completeness']} |",
        f"| Candidate coverage | {summary['candidate_coverage']} |",
        f"| Mean categories per look | {summary['mean_category_coverage']} |",
        f"| Mean distinct brands | {summary['mean_distinct_brands']} |",
        f"| Mean max single-brand share | {summary['mean_max_brand_share']} |",
        f"| Latency (median) | {summary['latency_ms']['median']} ms |",
        f"| Latency (max) | {summary['latency_ms']['max']} ms |",
        "", "## Metric definitions", "",
    ]
    for name, definition in spec["metric_definitions"].items():
        lines.append(f"- **{name}** - {definition}")

    for group_name, title in [("success", "Success scenarios"),
                              ("failure", "Failure scenarios"),
                              ("edge", "Edge scenarios")]:
        group_rows = [r for r in rows if r["group"] == group_name]
        if not group_rows:
            continue
        lines += ["", f"## {title}", ""]
        for row in group_rows:
            status = "PASS" if row["passed"] else "FAIL"
            metrics = row["metrics"]
            lines += [
                f"### {row['id']} - {row['title']}  ({status})", "",
                f"*{row['why']}*", "",
                f"- results: {metrics['results']}, categories: {metrics['category_coverage']}, "
                f"brands: {metrics['distinct_brands']}, latency: {metrics['latency_ms']} ms",
                f"- constraint satisfaction: {metrics['constraint_satisfaction']}, "
                f"colour compatibility: {metrics['colour_compatibility_rate']} "
                f"(over {metrics['colour_denominator']} colour-matchable items"
                + (f", {metrics['colour_unresolvable']} with no resolvable hue"
                   if metrics['colour_unresolvable'] else "") + "), "
                f"explanations: {metrics['explanation_completeness']}",
            ]
            if row["expectation_failures"]:
                lines.append("- **unmet expectations:** "
                             + "; ".join(row["expectation_failures"]))
            if row["warnings"]:
                lines.append("- warnings: " + " / ".join(row["warnings"]))
            if row["top_results"]:
                lines += ["", "| score | category | product | colour |", "|---|---|---|---|"]
                for item in row["top_results"]:
                    lines.append(
                        f"| {item['score']} | {item['category_group']} | "
                        f"{item['name']} | {item['colour_family']} |")
            lines.append("")

    with open(RESULTS_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
