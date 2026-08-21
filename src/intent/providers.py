"""LLM providers for intent extraction.

The backend supports more than one provider so that whichever key you have
works, but the *contract* is identical for all of them and deliberately tiny:

    natural language  ->  ExtractedIntent

A provider never sees the catalog, never returns a product, and has no field in
which to put one. Swapping providers therefore cannot change what gets
recommended - only how well free text is understood before the deterministic
engine takes over.

Selection is automatic from the environment, so no code change is needed to
switch:

    ANTHROPIC_API_KEY   -> Anthropic (Claude), the default
    GEMINI_API_KEY      -> Google Gemini
    GOOGLE_API_KEY      -> Google Gemini
    LLM_PROVIDER        -> force one of: anthropic | gemini | none

The key is read from the environment on the **backend only**. It is never sent
to the browser and never written into any frontend file or build output.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .schema import ExtractedIntent

# --------------------------------------------------------------------------
# Shared prompt
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You extract structured shopping intent from a shopper's message for a beauty \
and fashion recommendation system.

Your ONLY job is to fill the given schema. You do not recommend, name, invent or \
select products. You have no product catalog and must never output a product \
name, product id, brand, price or rating.

Rules:
- Extract only what the shopper actually said or clearly implied. If something is not stated, omit the field. Never fill a field with a plausible guess.

- `intent_type` is the most important field. Use "outfit" when the shopper wants a whole look assembled ("I need an outfit for a wedding", "help me dress for Diwali", "what should I wear tomorrow", "I am going to a wedding"). Use "product" when they want one kind of item ("red kurta for a wedding", "blue shirt for office", "red lipstick").

  Naming a garment does NOT by itself make it an outfit request. Two signals   decide it:
  * If the shopper says they ALREADY HAVE or ARE WEARING the garment ("I'm     wearing a black saree to a wedding", "I have a pink dress"), it is a     "product" request - they want things that go with what they own, not a     replacement for it.
  * If they ask to be dressed, it is "outfit" - they want the whole look     assembled, including the main garment. The literal word "outfit" is not     required: "what should/can I wear", "help me dress", "style me", "give me     a look", "I need something to wear", "I am going to a wedding tomorrow"     and "date outfit for women" are all outfit requests.

- `anchor_type` is the GARMENT the shopper has, will wear, or is asking for - saree, kurta, shirt, dress, jeans, lehenga. Always put a named garment here, never in `include_categories`. `include_categories` is only for product GROUPS they ask you to suggest, like "makeup", "jewellery", "accessories", "footwear", "lipstick".

- `colour` is the colour of that garment. `preferred_colours` is only for colours they want the RECOMMENDATIONS to be, which is different.

- `gender` - set to "men" for man/male/men/men's/for him/I'm a man/gents, and "women" for woman/female/women/women's/for her/I'm a woman/ladies. The word may appear anywhere in the sentence, including at the end. If they do not say, omit it - do not infer gender from the garment.

- `occasion` must be one of: wedding, festive, party, formal, office, casual, sports. Extract it even when it appears in passing ("going for wedding tomorrow" -> wedding). Map synonyms: shaadi/mehendi/reception -> wedding, diwali/puja/traditional -> festive, dinner/date/evening/night out -> party, work/meeting/interview -> office, gym/workout/active -> sports. If the occasion has no equivalent in that list, omit the field rather than forcing it.

- `style` must be one of: elegant, minimal, bold, traditional, modern, glam. Map classy/sophisticated -> elegant, understated/simple -> minimal, sporty/athletic -> omit style and set occasion to sports.

- `owns_anchor` is true when they already have or are wearing the garment ("I'm wearing a red saree", "I have a pink dress"). It is false when they are asking to be shown that garment ("red kurta for men").

- `time_context` records a time word the shopper used ("tomorrow", "tonight", "this weekend"). It is context only - it says nothing about stock or delivery.

- `descriptors` takes material, pattern and cut words only (silk, printed, leather). Never colours, occasions or styles - those have their own fields.

- If the shopper rules something out ("no jewellery"), put it in `exclude_categories`.

Worked examples:
  "I am going for wedding tomorrow with red kurta man"
    -> intent_type=outfit, gender=men, occasion=wedding, anchor_type=kurta,
       colour=red, time_context=tomorrow
  "I need an outfit for a wedding tomorrow"
    -> intent_type=outfit, occasion=wedding, time_context=tomorrow
  "red kurta for a wedding"
    -> intent_type=product, anchor_type=kurta, colour=red, occasion=wedding
  "navy blue shirt for the office, men"
    -> intent_type=product, anchor_type=shirt, colour=navy blue,
       occasion=office, gender=men
  "red lipstick for a wedding"
    -> intent_type=product, occasion=wedding, preferred_colours=[red],
       include_categories=[lipstick]
"""

# The JSON contract, derived from the pydantic model so the two cannot drift.
INTENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent_type": {"type": "string",
                        "description": "outfit | product"},
        "time_context": {"type": "string",
                         "description": "A time word the shopper used, e.g. tomorrow"},
        "owns_anchor": {"type": "boolean",
                        "description": "true if they already have/are wearing the garment"},
        "anchor_type": {"type": "string",
                        "description": "Garment named by the shopper, e.g. saree, kurta, shirt"},
        "colour": {"type": "string", "description": "Colour of that garment"},
        "occasion": {"type": "string",
                     "description": "wedding|festive|party|formal|office|casual|sports"},
        "style": {"type": "string",
                  "description": "elegant|minimal|bold|traditional|modern|glam"},
        "gender": {"type": "string", "description": "women|men|unisex"},
        "preferred_colours": {"type": "array", "items": {"type": "string"}},
        "include_categories": {"type": "array", "items": {"type": "string"}},
        "exclude_categories": {"type": "array", "items": {"type": "string"}},
        "descriptors": {"type": "array", "items": {"type": "string"},
                        "description": "Material/pattern/cut words only"},
    },
    "required": [],
    "additionalProperties": False,
}

# Gemini's `response_schema` accepts an OpenAPI subset that has no
# `additionalProperties` and rejects the request outright if it is present.
# Stripping it here does not weaken the contract: the response is still
# validated against the strict pydantic model afterwards, which forbids extras.
GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": INTENT_JSON_SCHEMA["properties"],
}

MAX_TOKENS = 1024
TIMEOUT_SECONDS = 12.0


class ProviderError(RuntimeError):
    """Any failure that should make the caller fall back to the parser."""


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    model: str


# --------------------------------------------------------------------------
# Anthropic (default)
# --------------------------------------------------------------------------


class AnthropicProvider:
    """Claude via the official SDK, using structured outputs."""

    name = "anthropic"
    default_model = "claude-opus-5"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.model = model or os.environ.get("LLM_MODEL") or self.default_model
        try:
            import anthropic
        except ImportError as exc:                       # pragma: no cover
            raise ProviderError("the `anthropic` package is not installed") from exc

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        try:
            client = anthropic.Anthropic(**({"api_key": key} if key else {}))
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        # Constructing a client does not validate credentials - it succeeds with
        # none set and only fails at request time. Check that something resolved
        # so /health cannot claim a capability the service does not have.
        if not any([getattr(client, "api_key", None),
                    getattr(client, "auth_token", None),
                    getattr(client, "credentials", None)]):
            raise ProviderError(
                "no Anthropic credentials found - set ANTHROPIC_API_KEY")
        self._client = client

    def extract(self, query: str) -> ExtractedIntent:
        import anthropic

        try:
            response = self._client.with_options(
                timeout=TIMEOUT_SECONDS
            ).messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": query}],
                output_format=ExtractedIntent,
                output_config={"effort": "low"},
            )
        except anthropic.RateLimitError as exc:
            raise ProviderError(f"rate limited: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"could not reach the API: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"unexpected failure: {exc}") from exc

        parsed = getattr(response, "parsed_output", None)
        if not isinstance(parsed, ExtractedIntent):
            raise ProviderError("response did not validate against the intent schema")
        return parsed


# --------------------------------------------------------------------------
# Google Gemini
# --------------------------------------------------------------------------


class GeminiProvider:
    """Google Gemini via the google-genai SDK, using JSON response schema."""

    name = "gemini"
    # gemini-2.0-flash was retired. Measured against this project's key:
    # gemini-3.6-flash returns 429 RESOURCE_EXHAUSTED (0/3 calls), and
    # gemini-flash-latest 503s intermittently (2/3); gemini-2.5-flash answered
    # 3/3 in ~2.9s. Reliability matters more than tier here because a failure
    # silently costs the request its natural-language understanding.
    # Override per deployment with LLM_MODEL.
    default_model = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.model = model or os.environ.get("LLM_MODEL") or self.default_model
        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError(
                "the `google-genai` package is not installed - "
                "`pip install google-genai`") from exc

        key = (api_key or os.environ.get("GEMINI_API_KEY")
               or os.environ.get("GOOGLE_API_KEY"))
        if not key:
            raise ProviderError(
                "no Google credentials found - set GEMINI_API_KEY or GOOGLE_API_KEY")
        try:
            self._client = genai.Client(api_key=key)
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

    def extract(self, query: str) -> ExtractedIntent:
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=query,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=GEMINI_RESPONSE_SCHEMA,
                    max_output_tokens=MAX_TOKENS,
                    temperature=0.0,
                ),
            )
        except Exception as exc:
            raise ProviderError(f"{type(exc).__name__}: {exc}") from exc

        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise ProviderError("empty response")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"response was not valid JSON: {exc}") from exc

        # Validate against the same strict pydantic model the other provider
        # uses, so an unexpected field is rejected rather than passed through.
        try:
            return ExtractedIntent.model_validate(payload)
        except Exception as exc:
            raise ProviderError(f"response did not validate: {exc}") from exc


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------

PROVIDERS = {"anthropic": AnthropicProvider, "gemini": GeminiProvider}


def detect_provider_name() -> str | None:
    """Which provider the environment is configured for, if any."""
    forced = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if forced:
        return None if forced in {"none", "off", "disabled"} else forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    # No explicit key: Anthropic can still resolve an `ant auth login` profile,
    # so give it the chance to and let it report if it cannot.
    return "anthropic"


def build_provider(api_key: str | None = None, model: str | None = None):
    """Construct the configured provider, or raise ProviderError."""
    name = detect_provider_name()
    if name is None:
        raise ProviderError("LLM disabled by configuration (LLM_PROVIDER)")
    factory = PROVIDERS.get(name)
    if factory is None:
        raise ProviderError(
            f"unknown LLM_PROVIDER '{name}' - expected one of "
            f"{', '.join(sorted(PROVIDERS))}")
    return factory(api_key=api_key, model=model)
