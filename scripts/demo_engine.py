"""Run the recommendation engine from the command line.

Not a UI - a way to exercise the engine directly while there is no interface.

    python scripts/demo_engine.py --anchor saree --colour black \
        --occasion wedding --style elegant --gender women
    python scripts/demo_engine.py --product-id 34949 --occasion wedding
    python scripts/demo_engine.py --anchor dress --colour pink --occasion party --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.engine import RecommendationEngine  # noqa: E402
from src.engine.schemas import Anchor, LookRequest, Preferences  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-id", type=int)
    parser.add_argument("--anchor", help="garment you already have, e.g. saree")
    parser.add_argument("--colour", help="its colour, e.g. black")
    parser.add_argument("--occasion")
    parser.add_argument("--style")
    parser.add_argument("--gender")
    parser.add_argument("--text", help="free text, e.g. 'silk printed'")
    parser.add_argument("--include", nargs="*", default=[])
    parser.add_argument("--exclude", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="print the full response")
    args = parser.parse_args()

    engine = RecommendationEngine()
    response = engine.recommend(LookRequest(
        Anchor(product_id=args.product_id, anchor_type=args.anchor, colour=args.colour),
        Preferences(
            occasion=args.occasion, style=args.style, gender=args.gender,
            free_text=args.text, include_categories=tuple(args.include),
            exclude_categories=tuple(args.exclude), limit=args.limit,
        ),
    ))

    if args.json:
        print(json.dumps(response.to_dict(), indent=2))
        return

    anchor = response.resolved_anchor
    print("\nANCHOR (yours, not for sale)")
    print(f"  {anchor.get('name') or anchor.get('product_type') or 'not specified'}"
          f"  [{anchor.get('colour_family') or 'no colour'}]"
          f"  via {anchor.get('source')}")

    if not response.recommendations:
        print("\nNo recommendations.")
    else:
        print(f"\nCOMPLETE THE LOOK  ({len(response.recommendations)} items)")
        for rec in response.recommendations:
            print(f"\n  {rec.score:.3f}  [{rec.category_group}]  {rec.name}")
            print(f"         {rec.brand or 'unbranded'} - {rec.base_colour}")
            for reason in rec.reasons:
                print(f"         - {reason}")

    print("\nCATEGORIES CONSIDERED")
    for category in response.categories:
        print(f"  {category.category_group:<17} affinity {category.affinity:.2f}  "
              f"{category.candidates_after_filter:>5} qualifying  {category.confidence}")
        if category.note:
            print(f"      note: {category.note}")

    if response.warnings:
        print("\nWARNINGS")
        for warning in response.warnings:
            print(f"  - {warning}")

    print(f"\n{response.diagnostics['latency_ms']} ms  |  catalog "
          f"{response.diagnostics['catalog_size']} products")


if __name__ == "__main__":
    main()
