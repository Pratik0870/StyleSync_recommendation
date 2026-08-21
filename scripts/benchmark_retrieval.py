"""Does text retrieval earn its place in the engine?

The Phase 1 catalog has almost no natural-language style vocabulary: "elegant"
appears in 3 of 43,165 product names, "traditional" in 1, and names average 5.8
tokens of the form "<brand> <gender> <colour> <type>". That predicts text
retrieval will add little over structured attributes - but the point of this
script is to measure it instead of assuming it.

Three retrieval strategies are compared on the same queries:

    structured   attribute filter only (category_group + colour_family)
    tfidf        TF-IDF cosine over text_blob
    embeddings   sentence-transformers all-MiniLM-L6-v2 over text_blob

Ground truth is a *structured* proxy, not human labels: a query like "red matte
lipstick for a wedding" has an unambiguous correct answer set (category_group =
beauty_lip AND colour_family = red). No labels are invented.

    python scripts/benchmark_retrieval.py            # tfidf + structured
    python scripts/benchmark_retrieval.py --embeddings   # also runs MiniLM
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "data", "processed", "catalog.parquet")
OUT = os.path.join(ROOT, "docs", "retrieval_benchmark.json")

# Each query states, in the words a user would plausibly use, something whose
# correct answer set is unambiguous in structured terms.
QUERIES = [
    ("red matte lipstick for a wedding",        {"category_group": "beauty_lip",      "colour_family": "red"}),
    ("deep brown lipstick, elegant look",       {"category_group": "beauty_lip",      "colour_family": "brown"}),
    ("pink nail polish for a party",            {"category_group": "beauty_nails",    "colour_family": "pink"}),
    ("black kajal eyeliner",                    {"category_group": "beauty_eye",      "colour_family": "black"}),
    ("gold earrings for a traditional look",    {"category_group": "jewellery",       "colour_family": "gold"}),
    ("silver necklace, minimal style",          {"category_group": "jewellery",       "colour_family": "silver"}),
    ("black heels for an evening event",        {"category_group": "footwear_dress",  "colour_family": "black"}),
    ("beige flat sandals for daywear",          {"category_group": "footwear_flat",   "colour_family": "beige"}),
    ("gold clutch bag for a wedding",           {"category_group": "bag",             "colour_family": "gold"}),
    ("red handbag, bold and modern",            {"category_group": "bag",             "colour_family": "red"}),
    ("green saree for a festive occasion",      {"category_group": "ethnic_wear",     "colour_family": "green"}),
    ("blue printed dress for a party",          {"category_group": "dress",           "colour_family": "blue"}),
]

K = 10


def precision_at_k(ranked_ids: list[int], truth: set[int], k: int = K) -> float:
    if not ranked_ids:
        return 0.0
    top = ranked_ids[:k]
    return sum(1 for pid in top if pid in truth) / len(top)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embeddings", action="store_true",
                    help="also benchmark sentence-transformers (downloads ~90 MB)")
    args = ap.parse_args()

    df = pd.read_parquet(CATALOG)
    df = df[df.can_be_complement | df.can_be_anchor].reset_index(drop=True)
    ids = df.product_id.tolist()
    corpus = df.text_blob.fillna("").tolist()
    print(f"corpus: {len(corpus)} products")

    truths = []
    for query, spec in QUERIES:
        mask = pd.Series(True, index=df.index)
        for column, value in spec.items():
            mask &= df[column] == value
        truths.append(set(df.loc[mask, "product_id"]))

    results: dict[str, dict] = {}

    # ---- structured baseline -------------------------------------------
    # Rank by attribute match only, ignoring text entirely. This is the bar
    # that text retrieval has to clear to be worth including.
    scores = []
    for (query, spec), truth in zip(QUERIES, truths):
        ranked = list(truth)[:K]
        scores.append(precision_at_k(ranked, truth))
    results["structured"] = {
        "mean_precision_at_10": round(sum(scores) / len(scores), 4),
        "per_query": {q: round(s, 3) for (q, _), s in zip(QUERIES, scores)},
        "note": "attribute filter only; correct by construction - the reference bar",
    }

    # ---- TF-IDF ---------------------------------------------------------
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import linear_kernel

    t0 = time.time()
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)
    matrix = vec.fit_transform(corpus)
    fit_s = time.time() - t0

    scores, latencies = [], []
    for (query, _), truth in zip(QUERIES, truths):
        t = time.time()
        sims = linear_kernel(vec.transform([query]), matrix).ravel()
        order = sims.argsort()[::-1][:K]
        latencies.append((time.time() - t) * 1000)
        scores.append(precision_at_k([ids[i] for i in order], truth))
    results["tfidf"] = {
        "mean_precision_at_10": round(sum(scores) / len(scores), 4),
        "per_query": {q: round(s, 3) for (q, _), s in zip(QUERIES, scores)},
        "fit_seconds": round(fit_s, 2),
        "mean_query_ms": round(sum(latencies) / len(latencies), 2),
        "vocabulary": len(vec.vocabulary_),
    }

    # ---- embeddings -----------------------------------------------------
    if args.embeddings:
        from sentence_transformers import SentenceTransformer

        t0 = time.time()
        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(corpus, batch_size=256, convert_to_numpy=True,
                           normalize_embeddings=True, show_progress_bar=True)
        fit_s = time.time() - t0

        scores, latencies = [], []
        for (query, _), truth in zip(QUERIES, truths):
            t = time.time()
            q = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
            order = (emb @ q[0]).argsort()[::-1][:K]
            latencies.append((time.time() - t) * 1000)
            scores.append(precision_at_k([ids[i] for i in order], truth))
        results["embeddings"] = {
            "model": "all-MiniLM-L6-v2",
            "mean_precision_at_10": round(sum(scores) / len(scores), 4),
            "per_query": {q: round(s, 3) for (q, _), s in zip(QUERIES, scores)},
            "encode_seconds": round(fit_s, 1),
            "mean_query_ms": round(sum(latencies) / len(latencies), 2),
            "dimensions": int(emb.shape[1]),
        }

    # ---- experiment 2: incremental value after structured filtering ------
    # Experiment 1 asks "can text find the right products?" - but the engine
    # already knows the category and colour from structured fields, so that is
    # not the question. The real question is whether text adds anything the
    # structured fields cannot express: material, pattern and cut, which live
    # only in the product name. Ground truth here is "name contains the term",
    # which is objective, and the baseline is catalog order within the same
    # already-filtered pool.
    residual = {}
    for term, group in [("printed", "ethnic_wear"), ("solid", "topwear"),
                        ("silk", "ethnic_wear"), ("classic", None),
                        ("matte", "beauty_lip"), ("leather", "bag")]:
        pool = df if group is None else df[df.category_group == group]
        if len(pool) < 50:
            continue
        truth = set(pool.loc[pool.name.str.contains(term, case=False, na=False), "product_id"])
        if len(truth) < 5:
            continue
        pool_ids = pool.product_id.tolist()
        pool_idx = pool.index.tolist()

        sims = linear_kernel(vec.transform([term]), matrix[pool_idx]).ravel()
        order = sims.argsort()[::-1][:K]
        text_p = precision_at_k([pool_ids[i] for i in order], truth)
        baseline_p = precision_at_k(pool_ids[:K], truth)

        residual[f"{term} in {group or 'any category'}"] = {
            "pool_size": len(pool),
            "products_with_term": len(truth),
            "base_rate": round(len(truth) / len(pool), 4),
            "tfidf_precision_at_10": round(text_p, 3),
            "unranked_baseline_precision_at_10": round(baseline_p, 3),
        }
    results["residual_text_value"] = residual

    with open(OUT, "w") as fh:
        json.dump({"k": K, "queries": len(QUERIES), "results": results}, fh, indent=2)

    print("\n" + "=" * 62)
    for name, r in results.items():
        if "mean_precision_at_10" not in r:
            continue
        print(f"{name:<12} P@{K} = {r['mean_precision_at_10']:.3f}"
              + (f"   {r.get('mean_query_ms', 0):.1f} ms/query" if "mean_query_ms" in r else ""))
    print("-" * 62)
    print("residual value of text after structured filtering (descriptor terms):")
    for label, r in results.get("residual_text_value", {}).items():
        print(f"  {label:<32} base {r['base_rate']:.3f} -> "
              f"tfidf P@{K} {r['tfidf_precision_at_10']:.2f} "
              f"(unranked {r['unranked_baseline_precision_at_10']:.2f})")
    print("=" * 62)
    print(f"written to {OUT}")


if __name__ == "__main__":
    main()
