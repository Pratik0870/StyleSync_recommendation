"""Fetch high-resolution product images for a bounded set of products.

Phase 1 validated that every catalog product maps to a row in a 900x1200 mirror
of the same Kaggle dataset, and stored that mapping in
`data/processed/image_fetch_index.csv` (alignment verified 6/6). This script
uses it to pull real high-resolution photography for *specific products only*.

It deliberately does NOT download the 6.3 GB mirror. Each product costs two
small HTTP requests, so the download is proportional to what you ask for and
nothing else.

    # products that appear in the built-in demo queries (recommended)
    python scripts/fetch_hires_images.py --from-queries

    # or an explicit set / a wider sweep
    python scripts/fetch_hires_images.py --ids 33135 30709 55488
    python scripts/fetch_hires_images.py --ids-file data/processed/_sweep_ids.json
    python scripts/fetch_hires_images.py --from-queries --limit 400

Images are stored at `data/processed/images_large/{product_id}.jpg`, downsampled
to fit 600x800 (plenty for the card and detail layouts) to keep the footprint
small. The API serves them automatically when present and falls back to the
Phase 1 thumbnails when not, so running this is always optional.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "data", "processed", "image_fetch_index.csv")
OUT_DIR = os.path.join(ROOT, "data", "processed", "images_large")

MIRROR = "benitomartin/fashion-product-images-small-900x1200"
ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"

TARGET_SIZE = (600, 800)
JPEG_QUALITY = 82
# The dataset-server rate-limits aggressive parallelism: 8 workers produced a
# wave of HTTP 429s. Three workers plus backoff completes reliably instead.
WORKERS = 3
TIMEOUT = 60
RETRIES = 4
BACKOFF_SECONDS = 2.5

# The queries the product is demonstrated with. Fetching exactly the products
# these surface gives a sharp demo for a few MB instead of gigabytes.
DEMO_QUERIES = [
    {"query": "I'm wearing a black saree to a wedding. I want an elegant look."},
    {"query": "I have a pink dress for a party. Suggest makeup and accessories."},
    {"query": "green silk kurta for diwali, traditional style, no jewellery"},
    {"query": "navy blue shirt for the office, men"},
    {"query": "Minimal office look for women"},
    {"query": "Something sporty for an active day"},
    {"query": "Green kurta for Diwali with traditional accessories"},
    {"anchor_type": "saree", "colour": "red", "occasion": "wedding", "gender": "women"},
    {"anchor_type": "dress", "colour": "black", "occasion": "party", "gender": "women"},
    {"anchor_type": "kurta", "colour": "blue", "occasion": "festive", "gender": "women"},
]


def product_ids_from_demo_queries(limit: int) -> list[int]:
    """Run the engine locally and collect every product the demos surface."""
    from src.engine.engine import RecommendationEngine
    from src.intent.extractor import IntentExtractor, intent_to_engine_request
    from src.engine.catalog_store import CatalogStore
    from src.engine.schemas import Anchor, LookRequest, Preferences

    store = CatalogStore()
    engine = RecommendationEngine(store=store)
    extractor = IntentExtractor(
        known_groups=store.available_complement_groups, use_llm=False)

    found: list[int] = []
    for spec in DEMO_QUERIES:
        if "query" in spec:
            intent, _ = extractor.extract(spec["query"])
            request = intent_to_engine_request(intent, limit=24, max_per_category=4)
        else:
            request = LookRequest(
                anchor=Anchor(anchor_type=spec.get("anchor_type"),
                              colour=spec.get("colour")),
                preferences=Preferences(
                    occasion=spec.get("occasion"), gender=spec.get("gender"),
                    limit=24, max_per_category=4),
            )
        response = engine.recommend(request)
        found.extend(int(r.product_id) for r in response.recommendations)

    unique = list(dict.fromkeys(found))
    print(f"demo queries surfaced {len(unique)} distinct products")
    return unique[:limit]


def _get(url: str) -> bytes:
    """GET with backoff, because the dataset server rate-limits bursts."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            return urllib.request.urlopen(url, timeout=TIMEOUT).read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise
        except urllib.error.URLError as exc:
            last = exc
        time.sleep(BACKOFF_SECONDS * (attempt + 1))
    raise last if last else RuntimeError("request failed")


def fetch_one(product_id: int, offset: int) -> tuple[int, str]:
    """Fetch, downsample and store one product image."""
    destination = os.path.join(OUT_DIR, f"{product_id}.jpg")
    if os.path.exists(destination):
        return product_id, "cached"

    url = (f"{ROWS_ENDPOINT}?dataset={urllib.parse.quote(MIRROR)}"
           f"&config=default&split=train&offset={offset}&length=1")
    payload = json.loads(_get(url))
    row = payload["rows"][0]["row"]

    # Guard the mapping every time rather than trusting it blindly.
    if int(row["id"]) != product_id:
        return product_id, f"skipped (mirror row {offset} holds id {row['id']})"

    raw = _get(row["image"]["src"])
    # Write to a temporary file and rename: a running API may be serving this
    # directory, and a half-written JPEG renders as a broken image.
    staging = destination + ".part"
    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert("RGB")
        image.thumbnail(TARGET_SIZE, Image.LANCZOS)
        image.save(staging, "JPEG", quality=JPEG_QUALITY, optimize=True)
    os.replace(staging, destination)
    return product_id, "fetched"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=int, nargs="*", default=None)
    parser.add_argument("--ids-file", default=None,
                        help="JSON file holding a list of product ids")
    parser.add_argument("--from-queries", action="store_true",
                        help="fetch the products the demo queries surface")
    parser.add_argument("--limit", type=int, default=250,
                        help="hard cap on how many products to fetch")
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()

    if not os.path.exists(INDEX):
        raise SystemExit(f"{INDEX} not found - run scripts/ingest_catalog.py first")

    if args.ids_file:
        wanted = json.load(open(args.ids_file))[:args.limit]
    elif args.ids:
        wanted = args.ids[:args.limit]
    elif args.from_queries:
        wanted = product_ids_from_demo_queries(args.limit)
    else:
        raise SystemExit("pass --from-queries or --ids")

    offsets = pd.read_csv(INDEX).set_index("product_id")["source_row_index"].to_dict()
    tasks = [(pid, int(offsets[pid])) for pid in wanted if pid in offsets]
    missing = len(wanted) - len(tasks)
    if missing:
        print(f"{missing} requested ids are not in the catalog index; skipped")

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"fetching up to {len(tasks)} images at {TARGET_SIZE[0]}x{TARGET_SIZE[1]} "
          f"from the {MIRROR} mirror")

    counts = {"fetched": 0, "cached": 0, "failed": 0, "skipped": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, pid, off): pid for pid, off in tasks}
        for done, future in enumerate(as_completed(futures), start=1):
            product_id = futures[future]
            try:
                _, status = future.result()
                key = status if status in counts else "skipped"
                counts[key] += 1
                if status.startswith("skipped"):
                    print(f"  ! {product_id}: {status}")
            except Exception as exc:
                counts["failed"] += 1
                print(f"  ! {product_id}: {type(exc).__name__}: {exc}")
            if done % 25 == 0:
                print(f"  {done}/{len(tasks)}…", flush=True)

    total_bytes = sum(
        os.path.getsize(os.path.join(OUT_DIR, f)) for f in os.listdir(OUT_DIR))
    print(f"\n{counts} — store now holds {len(os.listdir(OUT_DIR))} images "
          f"({total_bytes / 1e6:.1f} MB) in {OUT_DIR}")
    print("The API serves these automatically; products without one fall back to "
          "the Phase 1 thumbnail.")


if __name__ == "__main__":
    main()
