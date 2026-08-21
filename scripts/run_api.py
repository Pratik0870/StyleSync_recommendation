"""Start the backend.

    python scripts/run_api.py                 # http://127.0.0.1:8000
    python scripts/run_api.py --port 9000 --reload
    python scripts/run_api.py --no-llm        # force the deterministic parser

Equivalent to `uvicorn src.api.app:app`; this wrapper just checks the catalog
exists first so a missing data build fails with a clear message instead of a
stack trace on the first request.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

from src.engine.catalog_store import DEFAULT_CATALOG  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--no-llm", action="store_true",
                        help="disable LLM intent extraction entirely")
    args = parser.parse_args()

    if not os.path.exists(DEFAULT_CATALOG):
        raise SystemExit(
            f"Catalog not found at {DEFAULT_CATALOG}.\n"
            f"Build it first:  python scripts/ingest_catalog.py")

    if args.no_llm:
        os.environ["DISABLE_LLM"] = "1"

    import uvicorn

    print(f"  docs   http://{args.host}:{args.port}/docs")
    print(f"  health http://{args.host}:{args.port}/health")
    uvicorn.run("src.api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
