"""Phase 1 ingestion: raw Myntra dataset -> normalised product catalog.

Reproducible and idempotent. Downloads the source parquet shards once (cached
under data/raw/parquet), then validates, normalises, de-duplicates and exports.

    python scripts/ingest_catalog.py

Outputs
    data/processed/catalog.parquet     normalised catalog (one row per product)
    data/processed/images_thumb.parquet  validated 60x80 source images
    data/processed/image_fetch_index.csv  id -> row offset for the hi-res mirror
    docs/data_quality_report.json      machine-readable quality metrics
    static/sample_images/              a few decoded PNGs for visual QA

This script does not compute prices, scores, rankings or recommendations.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import time
import urllib.request
from collections import Counter, defaultdict

import pandas as pd
import pyarrow.parquet as pq
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.catalog.normalize import (  # noqa: E402
    build_brand_lexicon,
    build_text_blob,
    clean_name,
    classify_colour_role,
    colour_is_meaningful,
    name_key,
    extract_brand,
    normalise_audience,
    normalise_category_group,
    normalise_colour,
    normalise_domain,
    normalise_occasion,
    parse_finish,
    product_roles,
)
from src.catalog.taxonomy import (  # noqa: E402
    CATEGORY_GROUP_MAP,
    COLOUR_MAP,
    DOMAIN_MAP,
    GENDER_MAP,
    OCCASION_MAP,
)

DATASET = "ashraq/fashion-product-images-small"
PARQUET_API = "https://datasets-server.huggingface.co/parquet?dataset=ashraq%2Ffashion-product-images-small"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw", "parquet")
OUT_DIR = os.path.join(ROOT, "data", "processed")
DOCS_DIR = os.path.join(ROOT, "docs")
SAMPLE_DIR = os.path.join(ROOT, "static", "sample_images")

MIN_IMAGE_BYTES = 200          # below this a JPEG cannot carry a real photo
MIN_IMAGE_DIM = 40             # source thumbnails are 60x80
SAMPLE_IMAGE_COUNT = 24


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# 1. Source acquisition
# --------------------------------------------------------------------------


def download_shards() -> list[str]:
    os.makedirs(RAW_DIR, exist_ok=True)
    meta = json.load(urllib.request.urlopen(PARQUET_API, timeout=90))
    paths = []
    for f in meta["parquet_files"]:
        dest = os.path.join(RAW_DIR, f["filename"])
        if os.path.exists(dest) and os.path.getsize(dest) == f["size"]:
            log(f"cached  {f['filename']} ({f['size']/1e6:.1f} MB)")
        else:
            log(f"fetching {f['filename']} ({f['size']/1e6:.1f} MB)")
            urllib.request.urlretrieve(f["url"], dest)
        paths.append(dest)
    return sorted(paths)


# --------------------------------------------------------------------------
# 2. Load + validate
# --------------------------------------------------------------------------


def load_rows(shard_paths: list[str]) -> tuple[pd.DataFrame, dict[int, bytes]]:
    """Read every shard, decode-validate each image, return metadata + bytes."""
    frames, images = [], {}
    stats = Counter()
    offset = 0

    for path in shard_paths:
        table = pq.read_table(path)
        log(f"read {os.path.basename(path)}: {table.num_rows} rows")
        df = table.drop(["image"]).to_pandas()
        df["source_row_index"] = range(offset, offset + len(df))
        offset += len(df)

        image_col = table.column("image").to_pylist()
        widths, heights, byte_sizes, hashes, ok = [], [], [], [], []
        for pid, cell in zip(df["id"].tolist(), image_col):
            raw = cell.get("bytes") if isinstance(cell, dict) else None
            if not raw:
                stats["missing_bytes"] += 1
                widths.append(None); heights.append(None); byte_sizes.append(0)
                hashes.append(None); ok.append(False)
                continue
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    im.load()
                    w, h = im.size
            except Exception:
                stats["undecodable"] += 1
                widths.append(None); heights.append(None); byte_sizes.append(len(raw))
                hashes.append(None); ok.append(False)
                continue
            valid = (
                len(raw) >= MIN_IMAGE_BYTES
                and w >= MIN_IMAGE_DIM
                and h >= MIN_IMAGE_DIM
            )
            if not valid:
                stats["too_small"] += 1
            widths.append(w); heights.append(h); byte_sizes.append(len(raw))
            hashes.append(hashlib.md5(raw).hexdigest()); ok.append(valid)
            if valid:
                images[int(pid)] = raw

        df["image_width"] = widths
        df["image_height"] = heights
        df["image_bytes"] = byte_sizes
        df["image_md5"] = hashes
        df["image_ok"] = ok
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    log(f"image validation: {int(combined.image_ok.sum())}/{len(combined)} usable "
        f"({dict(stats) or 'no failures'})")
    return combined, images


# --------------------------------------------------------------------------
# 3. Vocabulary guard
# --------------------------------------------------------------------------


def assert_vocabularies_complete(df: pd.DataFrame) -> None:
    """Fail loudly on an unmapped source value rather than defaulting it."""
    checks = [
        ("baseColour", COLOUR_MAP), ("masterCategory", DOMAIN_MAP),
        ("articleType", CATEGORY_GROUP_MAP), ("usage", OCCASION_MAP),
        ("gender", GENDER_MAP),
    ]
    problems = []
    for column, mapping in checks:
        unmapped = sorted(set(df[column].dropna().unique()) - set(mapping))
        if unmapped:
            problems.append(f"{column}: {unmapped}")
    if problems:
        raise SystemExit("Unmapped source values:\n  " + "\n  ".join(problems))
    log("vocabulary check: all source values mapped")


# --------------------------------------------------------------------------
# 4. Normalise
# --------------------------------------------------------------------------


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    names = [clean_name(v) for v in df["productDisplayName"]]
    lexicon = build_brand_lexicon([n for n in names if n])
    log(f"brand lexicon: {len(lexicon)} brands derived from product names")

    records = []
    for row, name in zip(df.itertuples(index=False), names):
        domain = normalise_domain(row.masterCategory)
        group = normalise_category_group(row.articleType)
        colour = normalise_colour(row.baseColour)
        occasion, occasion_reliable = normalise_occasion(row.usage, domain)
        gender, age_group = normalise_audience(row.gender)
        brand = extract_brand(name, lexicon) if name else None
        finish = parse_finish(name, group) if name else None
        can_anchor, can_complement = product_roles(group)

        records.append({
            "product_id": int(row.id),
            "name": name,
            "brand": brand,
            "domain": domain,
            "category_group": group,
            "product_type": row.articleType,
            "master_category": row.masterCategory,
            "sub_category": row.subCategory,
            "base_colour": row.baseColour,
            **colour,
            "colour_role": classify_colour_role(row.articleType, group),
            "colour_meaningful": colour_is_meaningful(row.articleType, group),
            "occasion": occasion,
            "occasion_reliable": occasion_reliable,
            "gender": gender,
            "age_group": age_group,
            "season": row.season if isinstance(row.season, str) else None,
            "year": int(row.year) if pd.notna(row.year) else None,
            "finish": finish,
            "can_be_anchor": can_anchor,
            "can_be_complement": can_complement,
            "image_width": row.image_width,
            "image_height": row.image_height,
            "image_md5": row.image_md5,
            "image_ok": row.image_ok,
            "source_row_index": row.source_row_index,
            "text_blob": build_text_blob(
                name or "", brand, row.articleType, row.baseColour,
                colour["colour_family"], occasion, gender, finish,
            ) if name else None,
        })
    return pd.DataFrame.from_records(records)


# --------------------------------------------------------------------------
# 5. Clean
# --------------------------------------------------------------------------


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Drop unusable and duplicate records; return survivors + an audit trail."""
    removed: dict[str, int] = {}
    n0 = len(df)

    df = df.sort_values("product_id").reset_index(drop=True)

    mask = df["name"].notna()
    removed["missing_name"] = int((~mask).sum())
    df = df[mask]

    mask = df["image_ok"]
    removed["unusable_image"] = int((~mask).sum())
    df = df[mask]

    mask = df["domain"] != "excluded"
    removed["non_product_category"] = int((~mask).sum())
    df = df[mask]

    mask = df["category_group"] != "excluded"
    removed["non_product_type"] = int((~mask).sum())
    df = df[mask]

    # True duplicates are identical *images*, not identical names. Myntra reuses
    # generic display names across distinct designs (82 different products are
    # all called "Lucera Women Silver Earrings"), so name-based de-duplication
    # would delete the candidate variety a recommender depends on.
    dup_img = df.duplicated("image_md5", keep="first")
    removed["duplicate_image"] = int(dup_img.sum())
    df = df[~dup_img]

    # Flag - do not remove - products whose display name is shared with others.
    keys = [name_key(r.name, r.product_type, r.base_colour, r.gender)
            for r in df.itertuples(index=False)]
    df = df.assign(_key=keys)
    shared = df["_key"].map(df["_key"].value_counts())
    df = df.assign(name_shared_by=shared.astype(int),
                   name_is_generic=(shared > 1))
    df = df.drop(columns=["_key"]).reset_index(drop=True)
    removed["_total_removed"] = n0 - len(df)
    log(f"cleaning: {n0} -> {len(df)} rows ({removed})")
    return df, removed


# --------------------------------------------------------------------------
# 6. Export
# --------------------------------------------------------------------------


def export(df: pd.DataFrame, images: dict[int, bytes]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    # rebuild the QA sample directory so stale files from an earlier run cannot
    # be mistaken for current output
    if os.path.isdir(SAMPLE_DIR):
        for stale in os.listdir(SAMPLE_DIR):
            os.remove(os.path.join(SAMPLE_DIR, stale))
    os.makedirs(SAMPLE_DIR, exist_ok=True)

    df.to_parquet(os.path.join(OUT_DIR, "catalog.parquet"), index=False)

    # The source thumbnails are 60x80 but average 12.8 KB - they are stored at
    # near-zero compression. Re-encoding the same pixels at JPEG q88 shrinks the
    # store roughly 8x with no visible difference at this resolution.
    kept = df["product_id"].tolist()
    encoded, widths, heights = [], [], []
    for pid in kept:
        with Image.open(io.BytesIO(images[pid])) as im:
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=88, optimize=True)
        encoded.append(buf.getvalue())
        widths.append(im.width)
        heights.append(im.height)
    pd.DataFrame({
        "product_id": kept,
        "image_bytes": encoded,
        "width": widths,
        "height": heights,
    }).to_parquet(os.path.join(OUT_DIR, "images_thumb.parquet"), index=False)
    log(f"thumbnail store: {sum(len(b) for b in encoded)/1e6:.0f} MB re-encoded "
        f"from {sum(len(images[p]) for p in kept)/1e6:.0f} MB of source bytes")

    df[["product_id", "source_row_index"]].to_csv(
        os.path.join(OUT_DIR, "image_fetch_index.csv"), index=False)

    step = max(1, len(df) // SAMPLE_IMAGE_COUNT)
    for row in df.iloc[::step].head(SAMPLE_IMAGE_COUNT).itertuples(index=False):
        with Image.open(io.BytesIO(images[row.product_id])) as im:
            im.convert("RGB").save(
                os.path.join(SAMPLE_DIR, f"{row.product_id}_{row.category_group}.png"))

    log(f"exported catalog ({len(df)} products), images, and SQLite database")


# --------------------------------------------------------------------------
# 7. Quality report
# --------------------------------------------------------------------------


def quality_report(raw: pd.DataFrame, cat: pd.DataFrame, removed: dict) -> dict:
    def dist(col, frame=cat):
        return {str(k): int(v) for k, v in frame[col].value_counts().items()}

    beauty = cat[cat.domain == "beauty"]
    colour_meaningful = cat[cat.colour_meaningful]

    per_group = (
        cat.groupby("category_group")
        .agg(products=("product_id", "size"),
             colours=("colour_family", "nunique"),
             brands=("brand", "nunique"))
        .sort_values("products", ascending=False)
    )

    return {
        "source": {
            "dataset": DATASET,
            "license": "MIT (declared by the Kaggle source dataset)",
            "raw_rows": int(len(raw)),
        },
        "final_product_count": int(len(cat)),
        "removed": removed,
        "distribution": {
            "domain": dist("domain"),
            "category_group": dist("category_group"),
            "colour_family": dist("colour_family"),
            "occasion": dist("occasion"),
            "gender": dist("gender"),
            "age_group": dist("age_group"),
        },
        "beauty": {
            "total": int(len(beauty)),
            "by_category_group": dist("category_group", beauty),
            "by_product_type": dist("product_type", beauty),
            "women_or_unisex": int((beauty.gender != "men").sum()),
            "colour_coverage_pct": round(float(beauty.colour_family.notna().mean() * 100), 2),
        },
        "fashion_and_accessories": {
            "apparel": int((cat.domain == "apparel").sum()),
            "accessory": int((cat.domain == "accessory").sum()),
            "footwear": int((cat.domain == "footwear").sum()),
        },
        "colour": {
            "base_colour_coverage_pct": round(float(cat.base_colour.notna().mean() * 100), 2),
            "colour_family_coverage_pct": round(float(cat.colour_family.notna().mean() * 100), 2),
            "hex_resolved_pct": round(float(cat.colour_hex.notna().mean() * 100), 2),
            "multi_unresolvable": int((cat.colour_family == "multi").sum()),
            "colour_meaningful_products": int(len(colour_meaningful)),
            "colour_role": dist("colour_role"),
            "families": sorted(cat.colour_family.unique().tolist()),
        },
        "images": {
            "raw_rows_checked": int(len(raw)),
            "raw_decoded_ok": int(raw.image_ok.sum()),
            "raw_validated_ok_pct": round(float(raw.image_ok.mean() * 100), 2),
            "source_resolution": "60x80",
            "width_distribution": dist("image_width"),
            "height_distribution": dist("image_height"),
            "every_catalog_product_has_image": bool(cat.image_ok.all()),
        },
        "brand": {
            "coverage_pct": round(float(cat.brand.notna().mean() * 100), 2),
            "distinct_brands": int(cat.brand.nunique()),
            "top": {str(k): int(v) for k, v in cat.brand.value_counts().head(15).items()},
        },
        "occasion_reliability": {
            "reliable_rows": int(cat.occasion_reliable.sum()),
            "unreliable_rows": int((~cat.occasion_reliable).sum()),
            "note": "usage is not trustworthy for beauty products (source labels "
                    "virtually all personal care as Casual)",
        },
        "roles": {
            "anchor_candidates": int(cat.can_be_anchor.sum()),
            "complement_candidates": int(cat.can_be_complement.sum()),
        },
        "per_group": {
            str(idx): {"products": int(r.products), "colours": int(r.colours),
                       "brands": int(r.brands)}
            for idx, r in per_group.iterrows()
        },
    }


def main() -> None:
    shards = download_shards()
    raw, images = load_rows(shards)
    assert_vocabularies_complete(raw)
    cat = normalise(raw)
    cat, removed = clean(cat)
    export(cat, images)

    report = quality_report(raw, cat, removed)
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "data_quality_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    log("wrote docs/data_quality_report.json")
    print(json.dumps({k: report[k] for k in
                      ("final_product_count", "removed", "roles")}, indent=2))


if __name__ == "__main__":
    main()
