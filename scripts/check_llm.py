"""Is natural-language search working right now, and if not, why?

    python scripts/check_llm.py

Prints one plain verdict and what to do about it. Never prints the key.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000/health"

ADVICE = {
    "available": "Nothing to do - queries are going through the model.",
    "quota": "The daily free-tier allowance is used up. Create a new key in "
             "Google AI Studio, or wait for the quota to reset, then restart "
             "the backend.",
    "auth": "The key was rejected. Check GEMINI_API_KEY in .env, then restart "
            "the backend.",
    "not_configured": "No key is set. Copy .env.example to .env and add one.",
    "unavailable": "The provider is up but busy (503). This usually clears on "
                   "its own; try a different LLM_MODEL if it persists.",
    "network": "The provider could not be reached. Check the connection.",
    "timeout": "The provider did not answer in time.",
}


def main() -> int:
    try:
        health = json.load(urllib.request.urlopen(API, timeout=10))
    except urllib.error.URLError:
        print("Backend is not running on port 8000.")
        print("  start it with: python -m uvicorn src.api.app:app --port 8000")
        return 1

    llm = health.get("llm", {})
    state = llm.get("state", "unavailable")

    print(f"Search mode : {'AI-assisted matching' if llm.get('available') else 'Standard matching'}")
    print(f"Provider    : {llm.get('provider') or 'none'} ({llm.get('model') or 'n/a'})")
    print(f"State       : {state}")
    print(f"What to do  : {ADVICE.get(state, ADVICE['unavailable'])}")

    if state != "available":
        print("\nThe app keeps working either way - searches fall back to "
              "catalog matching.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
