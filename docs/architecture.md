# Architecture

The backend, the intent layer and the React frontend: how a query travels from
the browser to the catalog and back.

Exposes the approved the engine as a product-ready API and adds controlled
natural-language intent extraction. The engine remains the single source of truth for
which products come back; the catalog remains the single source of truth for what those
products are.

**167 tests pass** (47 the catalog build + 77 the engine + 43 the API layer). the 15/15 evaluation
scenarios still pass.

---

## API architecture

```
HTTP request
     |
 [1] pydantic validation          RecommendRequest - unknown fields rejected
     |
 [2] intent resolution            query -> LLM -> ExtractedIntent
     |                                     \--(any failure)--> deterministic parser
     |                            structured fields override either
     |
 [3] normalisation                every value mapped through the ENGINE's own
     |                            vocabulary; unrecognised values dropped + reported
     |
 [4] the engine               unchanged: filter -> score -> diversity -> explain
     |
 [5] response shaping             catalog values + image refs + reasons
     |
HTTP response
```

### Module map

| Path | Lines | Responsibility |
|---|---|---|
| `src/intent/schema.py` | 236 | `ExtractedIntent` (LLM contract), `NormalisedIntent` (engine contract), normalisation |
| `src/intent/fallback.py` | 140 | Deterministic parser, the no-LLM path |
| `src/intent/llm.py` | 180 | Provider wrapper, circuit breaker, typed failures |
| `src/intent/extractor.py` | 99 | LLM → fallback orchestration |
| `src/api/models.py` | 161 | Public request/response models |
| `src/api/images.py` | 79 | the catalog build image store |
| `src/api/app.py` | 447 | FastAPI app, endpoints, error handlers |

### What the API layer deliberately does not do

It does not rank, filter, score, or select. It has no product logic of its own. The one
substantive thing it adds beyond transport is *intent normalisation*, and that is
implemented by calling the engine's own resolvers, not by reimplementing them.

**the engine logic was not modified**, with one exception documented in §G.

---

## Intent schema

Two objects, deliberately separated.

### `ExtractedIntent`, the only thing an LLM may produce

| Field | Type | Meaning |
|---|---|---|
| `anchor_type` | `str?` | The garment the user already has |
| `colour` | `str?` | That garment's colour |
| `occasion` | `str?` | wedding · festive · party · formal · office · casual · sports |
| `style` | `str?` | elegant · minimal · bold · traditional · modern · glam |
| `gender` | `str?` | women · men · unisex |
| `preferred_colours` | `str[]` | Colours the *recommendations* should be |
| `include_categories` | `str[]` | Categories explicitly asked for |
| `exclude_categories` | `str[]` | Categories explicitly ruled out |
| `descriptors` | `str[]` | Material/pattern/cut only, silk, printed, leather |

`model_config = {"extra": "forbid"}`.

**Read what is absent: there is no `product_id`, `product_name`, `brand`, `price`,
`rating`, `score`, or `image` field.** A model that hallucinated a product would have
nowhere to put it. Hallucinated products cannot reach a response, not because they are
filtered out afterwards, but because the schema provides no channel for them. Two tests
assert this structurally, including one that fails if a future edit adds such a field.

### `NormalisedIntent`, what the engine receives

Produced by `normalise()`, which runs every field through the engine's own resolvers:

| Field | Resolver | Unrecognised value |
|---|---|---|
| `anchor_type` | `resolve_anchor_type` | dropped → `rejected` |
| `colour`, `preferred_colours` | `resolve_colour` | dropped → `rejected` |
| `occasion` | `normalise_occasion` | dropped → `rejected` |
| `style` | `normalise_style` | dropped → `rejected` |
| `gender` | literal set | dropped → `rejected` |
| `include/exclude_categories` | `CATEGORY_PHRASES` → the catalog build groups | dropped → `rejected` |
| `descriptors` | joined → engine `free_text` |, |

The LLM therefore cannot introduce a colour, garment, occasion, style or category the
engine does not already understand. Everything dropped is returned in `intent.rejected`
and surfaced in `notes`, **normalised or rejected, never guessed**.

`CATEGORY_PHRASES` maps everyday words onto the taxonomy: "makeup" → the four colour-
cosmetic groups, "accessories" → jewellery + bag, "shoes" → the four footwear groups.

---

## LLM responsibility

**One job: natural language to structured intent.** Default model `gemini-2.5-flash` on Gemini, or `claude-opus-5` on Anthropic,
`messages.parse()` with `output_format=ExtractedIntent` and `output_config={"effort":
"low"}` (extraction is a simple task; low effort keeps it fast).

| The LLM does | The LLM cannot |
|---|---|
| Read the user's sentence | See the catalog. It is never sent |
| Fill a fixed attribute schema | Name, invent or select a product |
| Map synonyms (shaadi → wedding) | Set a price, rating or popularity |
| Detect negation ("no jewellery") | Influence a score or a ranking |
|, | Return any field outside the schema (`extra: forbid`) |

Three independent guarantees, not one:

1. **Structural.** The schema has no product-shaped field.
2. **Vocabulary**, output is re-resolved against the engine's own lexicons.
3. **Selection**, product choice happens entirely inside the the engine, from the
   catalog, after intent is fixed.

**Failure handling.** `IntentLLMError` wraps every failure mode, missing credentials,
rate limit, HTTP error, connection failure, schema-validation failure, so the caller has
exactly one thing to catch. A **circuit breaker** opens after 3 consecutive failures for
60 s, so a dead provider costs one timeout rather than one per request. Timeout 12 s,
query truncated at 2,000 chars.

---

## Deterministic fallback

Not a stub. `src/intent/fallback.py` parses the same query shapes using the same
vocabularies the engine already ships, and its output goes through the **identical**
`normalise()` call, so both paths are bound by the same contract.

Verified output with no API key:

| Query | Parsed |
|---|---|
| "I'm wearing a black saree to a wedding. I want an elegant look." | saree · black · wedding · elegant |
| "I have a pink dress for a party. Suggest makeup and accessories." | dress · pink · party · include: makeup, accessories |
| "green silk kurta for diwali, traditional style, no jewellery" | kurta · green · festive · traditional · **exclude: jewellery** · descriptor: silk |
| "navy blue shirt for the office, men" | shirt · **blue** (from "navy blue") · office · men |
| "printed cotton dress for brunch, minimal, suggest flats and a bag" | dress · casual · minimal · include: flats, bag · descriptors: printed, cotton |

Techniques: longest-phrase non-overlapping matching; the colour nearest *before* the
garment becomes the anchor colour and the rest become preferences; negation within 24
characters before a category word flips it to an exclusion; "party" is not double-counted
as both occasion and style.

**Honest limits.** It cannot handle unusual phrasing, implicit occasion ("my cousin's big
day"), or vocabulary outside the lexicons. Those are reported as unparsed. The response
carries *"Nothing usable could be extracted from the request"* rather than a guess.

**This environment has no Anthropic credentials, so every test and every example in this
document ran on the fallback path.** The LLM path is exercised by tests through injected
doubles.

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + catalog size, image count, engine state, LLM state |
| `POST` | `/recommend` | Natural language and/or structured input → real catalog products |
| `GET` | `/images/{product_id}.jpg` | Product photograph (JPEG, cached 7 days, immutable) |
| `GET` | `/products/{product_id}` | One catalog product, for resolving an anchor in a UI |
| `GET` | `/categories` | Complement categories with affinity and the reason for each |
| `GET` | `/docs`, `/openapi.json` | Interactive docs and schema |

CORS is enabled for `localhost:3000` and `localhost:5173` so the the frontend can
develop against this.

### `/health`, states what it can actually do

```json
{
  "status": "ok",
  "catalog_products": 43165,
  "images_available": 43165,
  "engine_ready": true,
  "llm": {
    "available": false,
    "reason": "no Anthropic credentials found - set ANTHROPIC_API_KEY or run `ant auth login`",
    "model": "claude-opus-5"
  },
  "version": "0.3.0"
}
```

Constructing an Anthropic client does **not** validate credentials, it succeeds with
none set and only fails at request time. An early build reported `"available": true`
here and then fell back on every request. `/health` now checks that a credential source
actually resolved, so it cannot claim a capability the service does not have.

---

## Request / response examples

### Natural language

```bash
curl -X POST http://127.0.0.1:8000/recommend -H 'Content-Type: application/json' -d '{
  "query": "I'\''m wearing a black saree to a wedding. I want an elegant look.",
  "limit": 4
}'
```

```json
{
  "query": "I'm wearing a black saree to a wedding. I want an elegant look.",
  "intent": {
    "anchor_type": "saree", "anchor_category": "ethnic_wear",
    "colour": "black", "occasion": "wedding", "style": "elegant",
    "gender": null, "preferred_colours": [], "include_categories": [],
    "exclude_categories": [], "descriptors": null,
    "source": "fallback", "rejected": []
  },
  "anchor": {
    "source": "described", "category": "ethnic_wear",
    "product_type": "Sarees", "colour_family": "black"
  },
  "recommendations": [
    {
      "product_id": 33135,
      "name": "Catwalk Women Bronze Heels",
      "brand": "Catwalk",
      "category": "footwear_dress",
      "product_type": "Heels",
      "colour": "Bronze",
      "colour_family": "gold",
      "score": 0.981,
      "image": { "url": "/images/33135.jpg", "width": 60, "height": 80,
                 "media_type": "image/jpeg" },
      "reasons": [
        "Colour: gold metallic lifts a black base",
        "Occasion: catalogued as ethnic wear, which suits a wedding (1.00)",
        "Category: footwear is part of essentially every look (base 0.95, x1.15 for the occasion, x1.05 for this anchor) = 1.00",
        "Preference: suits a elegant brief - elegant looks favour deep or metallic tones and matte finishes"
      ],
      "score_breakdown": null
    }
  ],
  "categories": [
    { "category": "beauty_lip", "affinity": 1.0, "confidence": "strong",
      "qualifying_candidates": 425,
      "why_considered": "beauty_lip: lip colour is the most visible makeup decision (base 0.80, x1.20 for the occasion, x1.10 for this anchor) = 1.00. 425 of 425 products qualified.",
      "note": null }
  ],
  "notes": [
    "Language model not in use (no Anthropic credentials found - set ANTHROPIC_API_KEY or run `ant auth login`); used the deterministic parser instead."
  ],
  "meta": {
    "catalog_products": 43165, "categories_considered": 11,
    "engine_latency_ms": 126.01, "total_latency_ms": 178.61,
    "intent_source": "fallback", "version": "0.3.0"
  }
}
```

Every value above is a real catalog value. Nothing is defaulted, padded or invented, `brand` is `null` for the 0.41% of products with no derivable brand rather than filled in.

### Structured input (no query)

```json
{ "anchor_type": "saree", "colour": "black", "occasion": "wedding",
  "style": "elegant", "gender": "women", "limit": 8 }
```

### Anchor an existing catalog product

```json
{ "product_id": 34949, "occasion": "wedding", "limit": 6 }
```

### Query plus a correction

Structured fields always beat anything parsed from `query`, so a UI can let a user fix an
extracted value without re-parsing prose:

```json
{ "query": "I'm wearing a black saree to a wedding", "colour": "red" }
```
→ `intent.colour == "red"`.

### Other options

`use_llm: false` forces the deterministic parser. `include_score_breakdown: true` returns
the full per-component decomposition (component, raw, weight, contribution, detail), opt-in, so the default payload stays clean.

---

## Error handling

Every failure returns a consistent body, `{error, detail, code}`, with a user-facing
message and an actionable detail. Nothing is hidden.

| Case | Status | Code | Behaviour |
|---|---|---|---|
| Empty body / blank query | 422 | `invalid_request` | Lists the fields that would satisfy the request |
| Unknown field (`budget: 5000`) | 422 | `invalid_request` | `"budget: Extra inputs are not permitted"` |
| `limit` out of range | 422 | `invalid_request` | Bounds stated |
| Unknown `product_id` | 404 | `unknown_product` | *"Anchor products must be real catalog items."* |
| Unknown product image | 404 | `image_not_found` |, |
| LLM unavailable | 200 |, | Falls back; the reason appears in `notes` |
| Invalid LLM output | 200 |, | Unsupported values dropped, listed in `intent.rejected` |
| Unintelligible query | 200 |, | *"Nothing usable could be extracted…"* |
| No candidates | 200 |, | Empty list + *"Nothing was returned rather than filling the list with poor matches."* |
| Catalog not built | 503 | `engine_unavailable` | Names the script to run |
| Unexpected exception | 500 | `internal_error` | Logged with traceback; type and message returned |

### One the engine change was strictly required

`resolve_colour` and `resolve_anchor_type` matched vocabulary by **substring**, so:

| Input | Was | Now |
|---|---|---|
| `"ultraviolet"` | `purple` (contains "violet") | `None` |
| `"blackberry"` | `black` | `None` |
| `"greenhouse"` | `green` | `None` |
| `"laptop bag"` | `("topwear", "Tops")`, contains "top" | `(None, None)` |

the API feeds these resolvers free text from users *and from an LLM*, so a loose match
silently hands the engine an attribute nobody asked for. Fixed to whole-word matching
(longest phrase wins, so "navy blue" still beats "blue"). This is a correctness fix in
vocabulary resolution, **no scoring, ranking, affinity or colour-harmony logic was
touched.** the 15/15 evaluation scenarios still pass, and a regression test was
added to the the engine test suite.

The fix also improved evaluation honesty: scenario F04 now correctly reports *both*
"spacesuit" and "ultraviolet" as uninterpretable, where previously it silently accepted a
purple anchor the user never mentioned.

---

## Testing

**167 passing, ~8 seconds.**

| Suite | Tests |
|---|---|
| `tests/test_normalize.py` (the catalog build) | 47 |
| `tests/test_engine.py` (the engine) | 77 |
| `tests/test_api.py` (the API layer) | 43 |

API coverage, against the required list:

| # | Required | Covered by |
|---|---|---|
| 1 | Health endpoint | Ready state; LLM state disclosed with a reason when unavailable |
| 2 | Normal recommendation | Natural language; crosses ≥3 categories; beauty + accessories present; anchor category never returned |
| 3 | Structured request | No-query structured input; anchor by `product_id`; **structured fields override the parsed query**; exclusions respected |
| 4 | Empty query | Empty body, blank query, unknown field, out-of-range limit, unintelligible query |
| 5 | LLM unavailable fallback | `use_llm: false`; injected failing LLM falls back and reports why; missing credentials; circuit breaker opens after 3 failures |
| 6 | Invalid LLM response | Hallucinated vocabulary fully rejected (≥6 values); **schema has no product-shaped field**; extra fields rejected; partially-valid output keeps the good parts |
| 7 | No-result request | Exclude every category; unknown product 404; thin category disclosed |
| 8 | Real product IDs | Every id exists in the catalog; **every returned field matches the catalog row**; no price/rating/popularity key present |
| 9 | Image references | Every recommendation carries one; URL shape; real JPEG bytes (SOI marker checked); cacheable; 404 for unknown |
| 10 | Explanation presence | Every recommendation has reasons; reasons cite actual signals; breakdown contributions reproduce the score |

Plus determinism (identical request → identical products), the `/categories` endpoint, and
the OpenAPI schema.

---

## Running the backend locally

```bash
# one-time, if the catalog has not been built
python scripts/ingest_catalog.py

# start
python scripts/run_api.py                    # http://127.0.0.1:8000
python scripts/run_api.py --reload --port 9000
python scripts/run_api.py --no-llm           # force the deterministic parser

# or directly
uvicorn src.api.app:app --reload --port 8000
```

Interactive docs at `/docs`, schema at `/openapi.json`.

**The LLM is optional.** With no credentials the service starts normally, `/health`
reports why the LLM is unavailable, and every request is answered by the deterministic
parser. To enable it:

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # or: ant auth login
```

Set `DISABLE_LLM=1` to turn it off regardless of credentials.

```bash
python -m pytest tests/ -q               # 167 tests
python scripts/evaluate_engine.py        # the engine scenarios, still 15/15
```

---

## Frontend

A polished web application over the existing FastAPI backend. No recommendation logic
moved into JavaScript: the client sends intent and renders what the engine returns.

**167 Python tests still pass.** Phases 1–3 are unchanged apart from an additive,
backwards-compatible image capability (§G).

---

### Frontend architecture

```
main.jsx ─ BrowserRouter
   └── App ─ Header (brand · search · engine status)
        ├── /                  HomePage      hero, examples, how it works
        ├── /results?q=…       ResultsPage   intent editor + category sections
        └── /product/:id       ProductPage   catalog detail + why it was recommended
```

- **React 19 + Vite 7 + Tailwind 4** (CSS-first `@theme` tokens, no config file).
- **URL is the state.** `/results?q=…&colour=…&occasion=…&style=…&gender=…&include=…&exclude=…`
  A search is therefore reloadable, shareable and back-button-safe, and a correction is
  just a URL change that re-runs the same request path.
- **`api/client.js` is the only network boundary.** Everything else receives data as props.
- **No scoring, ranking, filtering or re-sorting in JS.** `groupIntoSections()` groups the
  already-ranked list by category using insertion order, so a category appears in the
  position its best product earned. Re-sorting would silently override the engine's
  diversity re-ranking.
- 82 npm packages, 66 MB `node_modules`, 266 KB JS + 28 KB CSS built (84 KB gzipped).

### Design direction

An original identity, not derived from the reference project: warm ivory paper, deep ink,
a berry accent for actions and muted gold for match signals; Fraunces display serif over
Inter for UI. Editorial retail spacing, generous whitespace, 3:4 product imagery.

---

### API integration

| Endpoint | Used by |
|---|---|
| `GET /health` | Header status badge; surfaces a dead backend before the user types |
| `POST /recommend` | Results page (natural language and structured corrections) |
| `GET /images/{id}.jpg` | Product cards and detail |
| `GET /products/{id}` | Product detail page |
| `GET /categories` | Available in the client; not needed by the current screens |

**Dev proxy.** `vite.config.js` proxies `/recommend`, `/health`, `/images`, `/products`
and `/categories` to `http://127.0.0.1:8000`. The API returns relative image URLs
(`/images/123.jpg`), so they resolve untouched, no rewriting on the client. For a build
served from another origin, `VITE_API_BASE` sets the absolute base.

**Request shaping.** `buildRecommendPayload()` omits empty values, so a blank control never
overwrites something the parser extracted, and only sends fields the backend accepts, which matters because the backend rejects unknown fields with 422.

**Correction flow.** the API guarantees structured fields beat anything parsed from the
query. The intent editor writes its values to the URL, they go back as structured fields,
and the backend applies the override. Verified: query says "black saree", user sets
colour → red, response comes back with `intent.colour = "red"`.

---

### Screens implemented

**Home**, hero (“Find what completes your look.”), the natural-language input, six
example queries that run on click, a section showing the four complement families the
catalog actually covers, and a four-step explanation of how matching works. Closes with a
plain statement that this is a demo over an open dataset with no prices or ratings.

**Results**, the original query, an intent summary bar (`Saree · Black · Wedding ·
Elegant`) with a **Refine** panel, a count (“16 products to complete it, across 7
categories”), then one section per category. Each section carries the engine's own
confidence, a collapsed “Why this category” holding the affinity arithmetic verbatim, and
a card grid. Rejected intent values and thin categories are disclosed rather than hidden.

**Product card**, real image, brand, name, category · colour, colour swatch, match
percentage, and the top “why this matches” reason. No price, rating, review or stock.

**Product detail**, large image, name, brand, category/type/colour pills, a “Why this was
recommended” panel (only when arrived at from a recommendation, carried in router state),
and a catalog attribute table. Unset attributes read “Not recorded”. States plainly that
the catalog has no price, rating or review data.

**Refinement**, chips for colour (with swatches), occasion, style, gender, plus include /
exclude category pickers. Clicking an active chip clears it back to unset. **Update
recommendations** is disabled until something changes.

---

### UX decisions

1. **Absence is shown as absence.** Unset intent fields render as an em dash and unknown
   attributes as “Not recorded”, never as a plausible-looking default.
2. **The engine's reasoning is surfaced but not shoved forward.** The affinity arithmetic
   is real product differentiation, but `beauty_lip: lip colour is the most visible makeup
   decision (base 0.80, ×1.20 …) = 1.00` reads like a dashboard. It now sits behind a
   “Why this category” disclosure; the card-level reason stays visible.
3. **Category order comes from the engine.** An earlier build sorted Beauty first, which
   overrode the engine's diversity re-ranking. Sections now appear in the order the
   backend ranked them, for a black saree that surfaces Heels first, which is also the
   better answer.
4. **Confidence is only mentioned when it is not “strong”**, so the common case stays
   quiet and a genuine caveat stands out.
5. **Skeletons mirror the real layout**, and on a refinement the previous results stay
   visible at reduced opacity instead of collapsing to a spinner.
6. **Each failure state does something different**: a dead backend prints the command to
   start it; an unparsed query shows the sentence shape that works; an empty result says
   nothing was returned rather than padding the page.
7. **Per-image failure is handled per card.** A broken image falls back to a labelled
   placeholder inside that card and does not affect the rest of the grid.
8. **The LLM status is a quiet badge**, and the deterministic parser is labelled “Built-in
   parser”, not an error. It is a normal path, not a broken one.

---

### Commands to run

The project lives at **`D:/ai-fashion-recommender`**.

```bash
# 1. Backend (terminal 1)
cd /d/ai-fashion-recommender
python scripts/run_api.py                 # http://127.0.0.1:8000  · docs at /docs

# 2. Frontend (terminal 2)
cd /d/ai-fashion-recommender/frontend
npm install                               # first time only
npm run dev                               # http://localhost:5173
```

Open **http://localhost:5173**. Use `localhost`, not `127.0.0.1` (§G.3).

```bash
# optional: widen high-resolution image coverage beyond the 93 demo products
python scripts/fetch_hires_images.py --from-queries --limit 400

# optional: enable natural-language understanding
export ANTHROPIC_API_KEY=sk-ant-...       # or: ant auth login

# checks
python -m pytest tests/ -q                # 167 tests
python scripts/evaluate_engine.py         # 15/15 scenarios
cd frontend && npm run build              # production bundle
```

The frontend works with no API key, the backend falls back to the deterministic parser
and the header shows “Built-in parser”.

---

