# Recommendation Method

How StyleSync scores, ranks and diversifies results. Covers the scoring
formula, category affinity, colour harmony, text relevance and the diversity
pass.

Given something the user already has, recommend complementary products **from other
categories** across fashion, accessories and beauty. Deterministic end to end: no LLM, no
randomness, no network call. Every returned product is a row from the the catalog build catalog;
every reason is generated from a score component that actually fired.

---

## Architecture

```
LookRequest (anchor + preferences)      <- the deterministic interface an LLM will fill
        |
   [1]  anchor resolution               product_id -> catalog row
        |                               or free text -> category_group + colour_family
   [2]  category affinity               which complement categories are worth considering
        |                               (base x occasion x anchor)
   [3]  candidate pool per category      can_be_complement, gender, adult
        |
   [4]  scoring                         colour . occasion . affinity . preference . text
        |                               weighted mean over *active* components
   [5]  acceptance floor                 drop everything below 0.45 rather than pad
        |
   [6]  affinity-scaled slots            a category's affinity governs how many it may take
        |
   [7]  diversity re-rank (MMR)          brand / colour / product-type penalties
        |
   [8]  deterministic explanations       from the components, ranked by contribution
        |
LookResponse (recommendations + per-category results + warnings + diagnostics)
```

### Module map

| Module | Lines | Responsibility |
|---|---|---|
| `src/engine/schemas.py` | 171 | Dataclass contracts — the LLM boundary |
| `src/engine/catalog_store.py` | 227 | Catalog access, anchor resolution, candidate pools |
| `src/engine/colour.py` | 249 | 15-family colour harmony model |
| `src/engine/affinity.py` | 246 | Category affinity + product-type refinement |
| `src/engine/occasion.py` | 207 | Occasion suitability — two separate paths |
| `src/engine/relevance.py` | 125 | TF-IDF text relevance |
| `src/engine/scoring.py` | 302 | Score components, weights, style profiles |
| `src/engine/diversity.py` | 127 | MMR re-ranking |
| `src/engine/explain.py` | 85 | Deterministic reason generation |
| `src/engine/engine.py` | 402 | Orchestration, confidence, failure handling |

### Two input forms, one interface

```python
# A. an existing catalog product
LookRequest(Anchor(product_id=34949), Preferences(occasion="wedding"))

# B. a described item
LookRequest(Anchor(anchor_type="saree", colour="black"),
            Preferences(occasion="wedding", style="elegant", gender="women"))
```

**No field in `LookRequest` can carry a recommended product.** An anchor may reference a
catalog id, which is resolved and rejected if unknown. Recommended products can therefore
only ever originate from the catalog — a hallucinated product has no route into a response
even when the API puts an LLM in front of this.

### Deliberately *not* built

No outfit slots, no top/bottom/footwear assembly, no greedy outfit generation, no
completeness requirement over a wardrobe. Categories are recommended **independently**,
each with its own affinity, confidence and candidate pool. A look with no bag is a normal
result here, not an incomplete one.

---

## Final scoring formula

```
score = Σ(weight_i × raw_i) / Σ(weight_i)      over ACTIVE components only
```

| Component | Weight | Active when | Source |
|---|---|---|---|
| `colour_harmony` | **0.35** | anchor colour known **and** `colour_role == "style"` | `colour.py` |
| `occasion_suitability` | **0.25** | a recognised occasion was requested | `occasion.py` |
| `category_affinity` | **0.18** | always | `affinity.py` |
| `preference_match` | **0.14** | a style or preferred colour was requested | `scoring.py` |
| `text_relevance` | **0.08** | free text was supplied and matched a term | `relevance.py` |

Weights live in `ScoreConfig` and are constructor-injectable.

**Renormalisation is the important part.** A missing signal is *absent*, not scored 0.5.
If the user names no occasion, occasion suitability does not quietly contribute a
mediocre value — it is dropped and the remaining weights re-normalise. Consequence:
a single perfect component yields 1.0, not 0.35.

**Ordering rationale.** Colour is largest because coordination is the entire premise of
cross-category recommendation, and it is the one attribute the catalog carries at 100%
coverage. Occasion is second because it is what makes a wedding answer differ from an
everyday one. Affinity is third *because it already exerts influence by selecting which
categories appear* — weighting it heavily again inside the item score would double-count
it. Text is smallest because it was measured to be worth little (§E).

Verified by test: contributions divided by total weight reproduce the reported score
exactly, for every recommendation.

---

## Category-affinity strategy

A flat anchor × complement matrix would be 6 × 17 = **102 opaque numbers**. Affinity is
instead *composed* from three factors, each stateable in a sentence:

```
affinity = base_relevance × occasion_fit × anchor_fit
```

| Factor | Question it answers | Example |
|---|---|---|
| `base_relevance` | How often does this category feature in a look at all? | footwear 0.95, wallet 0.15 |
| `occasion_fit` | How much does *this occasion* call for it? | jewellery ×1.20 at a wedding, ×0.20 at the gym |
| `anchor_fit` | How well does it pair with *this garment*? | belt ×1.30 with bottomwear, ×0.25 with a saree |

Worked example, printed verbatim in every explanation:

> `jewellery`: jewellery is the primary way a look is dressed up (base 0.80, ×1.20 for the
> occasion, ×1.20 for this anchor) = 1.00

**Product-type refinement.** Category groups are sometimes coarser than the styling
decision. `fragrance` holds both perfume and deodorant; `bag` holds both evening clutches
and laptop cases. Without refinement the engine surfaced *"Reebok Women Reeshine Deo"* and
*"Belkin Unisex Black Dash Laptop 16 Toploader"* for a wedding and a party respectively —
both real outputs from an intermediate build. `PRODUCT_TYPE_RELEVANCE` multiplies the
affinity component per product (Deodorant 0.40, Laptop Bag 0.20, Clutches 1.00).

**Affinity governs presence, not just ranking.** A category's affinity decides how many
final slots it may occupy:

| Affinity | Slots |
|---|---|
| ≥ 0.60 | full allowance (`max_per_category`, default 2) |
| 0.35 – 0.60 | 1 |
| < 0.35 | 0 — still reported in `categories[]` with its affinity, absent from the look |

This was added because a watch (affinity 0.16 at a wedding) was taking two of ten slots on
colour score alone, contradicting the affinity the engine had just reported.

**Explicit user intent overrides the floor.** `MIN_AFFINITY` (0.15) is a default-relevance
floor, not a veto. If the user explicitly includes `headwear` for a wedding (affinity
0.08), it is returned with its weakness reported rather than silently dropped. This was
found by evaluation scenario F06 and is now covered by a regression test.

**These are declared editorial priors, not learned weights.** The catalog has no
interaction data to learn from. They are configurable and could be replaced by mined
affinities if behavioural data is ever added.

---

## Colour-harmony strategy

Hue angles are **computed from the representative hex codes** in the the catalog build taxonomy, not
typed in by hand, so the colour model stays tied to the values the catalog was built with.

Families are classed as **neutral** (black, white, grey, beige), **metallic** (gold,
silver), **unresolved** (multi) or **chromatic**.

| Relation | Score | When |
|---|---|---|
| `metallic_on_neutral` | 0.95 | gold/silver against a neutral base |
| `metallic_tone_match` | 0.92 | gold with warm, silver with cool |
| `accent_on_neutral` | 0.90 | saturated complement, neutral anchor |
| `neutral_grounding` | 0.85 | neutral complement, saturated anchor |
| `analogous` | 0.80 | ≤ 45° apart |
| `metallic_tone_clash` | 0.78 | gold with cool, silver with warm |
| `complementary` | 0.75 | > 150° apart |
| `same_family` | 0.68 | tonal — valid but flat |
| `near_analogous` | 0.66 | 45–90° |
| `neutral_on_neutral` | 0.62 | safe, low contrast |
| `triadic` | 0.60 | 90–150° |
| `unresolved` | 0.50 | "Multi" — no single hue exists |

**The design point.** A complement is not a duplicate. `same_family` (0.68) is deliberately
scored *below* `accent_on_neutral` (0.90) and `metallic_on_neutral` (0.95), so black + gold
beats black + black. Without this the engine degenerates into a similarity recommender —
which is the exact failure this product exists to avoid. Covered by test.

**Only `colour_role == "style"` products are colour-matched.** Foundation shades
(`skin_match`, 118 products) match a face; perfume bottles (`packaging`, 6,410 products)
match nothing. For these, **no colour component is produced at all** and the remaining
components carry the full weight — they are not scored badly, they are scored on what is
real about them. Four tests enforce this, including an end-to-end assertion that no
foundation or perfume in a response ever carries a `colour_harmony` component.

**Two bugs found and fixed while building this:**

1. `grey` inherited Charcoal's hex (`#36454F`), which is blue-tinted, giving the grey
   family a spurious 204° hue and making it behave as a cool chromatic. Canonical hexes now
   prefer the source colour whose name *is* the family name. Regression test added.
2. The 45–90° band was labelled `clash` at 0.25, which made green→yellow (68°) a clash.
   That band is now `near_analogous`.

**Stated limitation — no clash detection.** Fifteen coarse families carry hue but not
saturation or lightness, and discord is largely a saturation/value effect: a pale sage and
a neon lime share a family and behave completely differently. Claiming to detect a clash at
this granularity would be false precision, so the model expresses a *preference ordering*
(0.50–0.95) rather than a pass/fail verdict. A test asserts no clash verdict is claimed.

A second known discrepancy: red and green are complementary in painterly (RYB) colour
theory but sit 130° apart in RGB hue space, so they score `triadic` (0.60) rather than
`complementary`. This is a property of computing hue in RGB and is documented rather than
special-cased.

---

## Semantic retrieval approach

**Decision: TF-IDF, at the smallest weight (0.08). Sentence embeddings were benchmarked
and rejected.** This was measured, not assumed — `scripts/benchmark_retrieval.py`, results
in `docs/retrieval_benchmark.json`.

**Experiment 1** — 12 realistic queries with unambiguous structured answers
("red matte lipstick for a wedding" → `beauty_lip` ∧ `red`):

| Strategy | P@10 | Query latency |
|---|---|---|
| Structured attribute filter | **1.000** | — |
| Embeddings (all-MiniLM-L6-v2) | 0.917 | 18.8 ms |
| TF-IDF | 0.842 | 15.7 ms |

Embeddings beat TF-IDF — **and both lose to the structured fields.** Category and colour,
which is what those queries are about, are already columns in the catalog. Text is not the
right tool for that job, so the engine does not use it for that job.

**Experiment 2** — the question that actually matters: does text add anything *after*
structured filtering, on terms only the product name carries?

| Term / pool | Base rate | Unranked P@10 | TF-IDF P@10 |
|---|---|---|---|
| `printed` in ethnic_wear | 47.1% | 0.00 | **1.00** |
| `matte` in beauty_lip | 14.6% | 0.00 | **1.00** |
| `leather` in bag | 5.4% | 0.00 | **1.00** |
| `solid` in topwear | 5.4% | 0.10 | **1.00** |
| `silk` in ethnic_wear | 1.1% | 0.00 | **1.00** |
| `classic` in any category | 1.1% | 0.00 | **1.00** |

Text has real, measurable value — but only for material, pattern and cut, which live
nowhere else in the schema.

**Why not embeddings, given they scored higher in experiment 1?**

1. Experiment 1 measures a job the structured fields already do perfectly.
2. For exact descriptor terms, TF-IDF is already at 1.00 — there is no headroom to buy.
3. The catalog has almost no natural-language style vocabulary to embed: **"elegant"
   appears in 3 of 43,165 product names, "traditional" in 1.** Names average 5.8 tokens of
   the form `<brand> <gender> <colour> <type>`.
4. TF-IDF term overlap can be *shown* ("matches 'silk', 'printed'"). An embedding cosine
   cannot, and this engine has to explain itself.
5. No 90 MB model download, no encoding step, fully reproducible.

**Consequence for the interface:** `style` is handled structurally by `preference_match`,
**not** fed to the text index. Doing both double-counted the signal and forced the TF-IDF
index to be built on every request (494 ms → 121 ms once separated).

---

## Preference matching

| Preference | Effect |
|---|---|
| `preferred_colours` | Exact family match scores 1.0; otherwise the best harmony against any requested colour |
| `style` | Mapped to a `StyleProfile` (colour + finish preferences) |
| `gender` | Hard filter on the candidate pool (`gender` or `unisex`) |
| `include_categories` | Restricts categories; overrides the affinity floor |
| `exclude_categories` | Hard removal |
| `max_per_category` | Cap per category, scaled down by affinity |
| `free_text` | Drives text relevance |

Six style profiles — `elegant`, `minimal`, `bold`, `traditional`, `modern`, `glam` — plus
a synonym map ("classy" → elegant, "understated" → minimal). Each profile is expressed
**only in terms the catalog can express**: colour-family preferences, finish preferences,
and a metallic flag. Nothing is claimed that the data cannot support.

Style is applied as a **nudge, not a filter**, so a strong match is not lost on a soft
preference. A product whose colour is `skin_match` or `packaging` cannot express a style
through colour, so only its finish counts.

---

## Diversity approach

Greedy **Maximal Marginal Relevance** with an inspectable penalty:

```
adjusted = score − λ × (0.55·repeat_brand + 0.30·repeat_colour + 0.35·repeat_type)
```

with `λ = 0.35` and a hard cap of 2 per brand.

The problem is concrete: 38.9% of catalog products share a display name with another
product, and 82 distinct designs are all called "Lucera Women Silver Earrings" with nearly
identical scores. Returning ten of them is the highest-scoring answer and a useless one.

MMR was chosen over clustering because it is O(n·k), needs one tunable parameter, and —
decisively here — **the reason an item was demoted can be stated in words**. Every
selected item carries a `diversity_note` ("2 already in gold"), which is surfaced in the
explanation.

Measured across the 15 evaluation scenarios: **mean 5.2 distinct brands** per look, **mean
maximum single-brand share 0.28**.

---

## Explanation approach

Deterministic, generated from the components that actually fired. No LLM.

Reasons are ranked **by contribution, not by component order** — the reason shown first is
the reason the product ranked where it did. Components below 0.55 raw are not claimed as
positives; components below 0.40 are surfaced as caveats. If nothing was strong, the
explanation says so ("Weak match overall — the strongest signal was only 0.42: …") rather
than staying silent.

Every response also carries a full `score_breakdown` with each component's raw value,
weight, contribution and detail sentence, so a number can always be traced.

Sample output:

```
0.955  [beauty_lip]  Revlon Bronze Shimmer Colorburst Lip Gloss 30
  - Colour: gold metallic lifts a black base
  - Occasion: gold shade with a shimmer finish reads as an evening/occasion look,
    which suits a wedding (0.93); derived from product attributes because the source
    occasion label is unreliable for beauty products
  - Category: lip colour is the most visible makeup decision
    (base 0.80, x1.20 for the occasion, x1.10 for this anchor) = 1.00
  - Shown for variety (1 already in gold).
```

the API may pass these to an LLM to rewrite as prose, but the **content** will still
originate here.

---

## Evaluation results

`python scripts/evaluate_engine.py` → `docs/EVALUATION.md` + `docs/evaluation_results.json`.

**No ground truth was fabricated.** The catalog has no user interactions, so there is no
label for "which product would a person pick". Instead each scenario declares the
properties a correct answer must have, written **before** the evaluator was run, and those
are checked mechanically.

### Summary — 15/15 scenarios pass

| Metric | Value |
|---|---|
| Constraint satisfaction | **1.000** |
| Explanation completeness | **1.000** |
| Colour compatibility rate | 0.917 |
| Candidate coverage | 0.947 |
| Mean categories per look | 4.87 |
| Mean distinct brands | 5.2 |
| Mean max single-brand share | 0.279 |
| Latency — median / max | 157 ms / 299 ms |

**On the 0.917 colour figure.** Every scenario where colour compatibility is *establishable*
scores **1.000**. The aggregate is pulled down by one scenario alone — F09, a
multi-coloured anchor, which scores 0.0 because "Multi" has no resolvable hue and the model
correctly refuses to invent one. That is the model working as designed, and the evaluator
now reports `colour_unresolvable` alongside the rate so the 0.0 is not mistaken for a
failure.

### Scenarios

| ID | Scenario | Result |
|---|---|---|
| S01 | Black saree + wedding + elegant | PASS — 6 categories, colour 1.00 |
| S02 | Pink dress + party | PASS — discloses the 28-product party sparsity |
| S03 | Green kurta + festive + traditional | PASS — 7 categories, colour 1.00 |
| S04 | Anchor by catalog `product_id` | PASS — resolves to `catalog_product` |
| S05 | Men's white shirt + office | PASS — watches/belts/formal shoes, not makeup |
| S06 | Blue jeans + casual | PASS — 8 categories |
| F01 | Unknown product id | PASS — empty + explicit warning |
| F02 | Every category excluded | PASS — empty + explanation |
| F03 | Unsupported occasion ("moon landing") | PASS — warns, still answers on colour |
| F04 | Uninterpretable anchor ("spacesuit"/"ultraviolet") | PASS — reports, does not guess |
| F05 | Impossible combination (saree + gym) | PASS — affinity strips makeup out |
| F06 | Very rare category alone (headwear) | PASS *(after fix — see below)* |
| F07 | Mixed colour-role category alone (beauty_face) | PASS — discloses non-matchable share |
| F08 | Completely generic request | PASS — no colour component invented |
| F09 | Multi-coloured anchor | PASS — falls back to `unresolved` |

**F06 initially failed and found a real design flaw.** Headwear for a wedding scores 0.08
affinity, below `MIN_AFFINITY`, so an explicitly requested category was being silently
dropped with a misleading warning about include/exclude filters. Fixed so explicit user
intent overrides the relevance floor; regression test added.

### Flagship output — "black saree, wedding, elegant"

| Score | Category | Product | Colour |
|---|---|---|---|
| 0.981 | footwear_dress | Catwalk Women Bronze Heels | gold |
| 0.981 | jewellery | Fabindia Women Ananya Gold Earrings | gold |
| 0.955 | beauty_lip | Revlon Bronze Shimmer Colorburst Lip Gloss 30 | gold |
| 0.947 | footwear_dress | Catwalk Women Ethnic Red Heels | red |
| 0.928 | footwear_flat | Portia Women Gold Flats | gold |
| 0.926 | bag | Fabindia Red Silk Sling Purse | red |
| 0.917 | beauty_eye | Lakme Absolute Eye Chromatic Day Shimmer Baked Eye Shadow | gold |

---

## Test results

**123 tests, all passing** (47 from the catalog build + 76 for the engine), in ~3 seconds.

| Area | Coverage |
|---|---|
| Colour harmony | Full 15×15 matrix scores; neutral/metallic/accent ordering; hue wrap; determinism; grey regression; no-clash claim |
| **`colour_role` filtering** | `skin_match` and `packaging` never produce a colour component; end-to-end assertion over a real response; preference path also respects it |
| Category affinity | Three-factor composition; occasion and anchor effects; include/exclude; sorting/threshold; product-type refinement; explicit-include override |
| Candidate filtering | Complements only; anchor category never returned; gender filter; unknown id; every result exists in the catalog |
| Scoring | Weighted mean; **absent components do not dilute**; bounds; determinism across repeated calls; breakdown sums to score |
| Occasion | Synonyms; **`beauty_suitability` signature carries no source-occasion parameter**; deep vs pale shades by occasion; skin-match ignores shade |
| Diversity | Brand break-up; hard cap; colour preference; best-first; demotion notes; empty pool |
| Explanations | Generated from fired components; ordered by contribution; weak components not claimed; honest empty case |
| Thin categories | Thin/none confidence reported; mixed colour-role disclosure; acceptance floor respected |
| No-result handling | Unknown anchor, all-excluded, empty catalog, unrecognised occasion/anchor/style, generic request |
| Text relevance | Descriptor matching; empty query contributes nothing; stopwords rejected |
| Integration | Flagship scenario; anchor by id; party sparsity disclosure; latency budget |

A robustness bug was found by the tests and fixed: `TfidfVectorizer(min_df=2)` raises on a
corpus of fewer than 2 documents, so a very small candidate pool crashed the engine. It now
falls back to `min_df=1`.

---

## Known limitations

| # | Limitation | Severity | Position |
|---|---|---|---|
| 1 | **Affinity weights are editorial priors, not learned** | High | The catalog has no interaction data. They are declared as priors, composed from three stateable factors, fully configurable, and replaceable by mined affinities if behavioural data is added. Not presented as empirical. |
| 2 | **Colour model cannot detect clashes** | Medium | 15 families carry hue but not saturation/lightness. The model expresses a preference ordering, not a verdict. Asserted by test rather than quietly assumed. |
| 3 | **Beauty occasion is derived, never observed** | Medium | The catalog build established the source label is unusable (2,136/2,139 say "Casual"). Derivation from shade intensity + finish is documented and testable, but it is a model, not data. |
| 4 | **No price, no ratings, no popularity, no collaborative signal** | Medium | None exist in the catalog. Nothing was invented to fill the gap. |
| 5 | **Style profiles are hand-authored** | Medium | Only expressible in colour/finish/metallic terms — the only style-adjacent attributes the catalog has. "Elegant" appears in 3 product names, so there is nothing to learn from. |
| 6 | **Sparse occasions** | Medium | Only 28 products labelled "party" and 67 "smart_casual". Party requests are served from ethnic/formal/smart-casual and the engine **says so in a warning**. |
| 7 | **Thin beauty categories** | Medium | Eyeshadow 32, blush/highlighter 37, mascara 12, concealer 11. Reported as `thin` confidence with a note; nothing is padded to fill a slot. |
| 8 | **Latency 157 ms median** | Low | Acceptable for interactive use, but it is a full linear scan of each candidate pool with memoised component construction. A precomputed colour × occasion matrix would cut it materially if needed. |
| 9 | **Anchor vocabulary is a fixed lexicon** | Low | ~35 garment words and ~60 colour words. Unrecognised input is reported, never guessed. the LLM is intended to widen this. |
| 10 | **RGB hue ≠ painterly colour theory** | Low | Red/green score `triadic` rather than `complementary`. Documented, not special-cased. |
| 11 | **Category groups are occasionally coarser than the decision** | Low | Mitigated by `PRODUCT_TYPE_RELEVANCE` for the cases found (deodorant, laptop bags, concealer). Others may remain. |

---

## Reproducing

```bash
python -m pytest tests/ -q                        # 123 tests
python scripts/evaluate_engine.py                 # 15 scenarios -> docs/EVALUATION.md
python scripts/benchmark_retrieval.py             # TF-IDF vs structured
python scripts/benchmark_retrieval.py --embeddings # adds MiniLM (downloads ~90 MB)
python scripts/demo_engine.py --anchor saree --colour black \
    --occasion wedding --style elegant --gender women
```

Deterministic: no randomness, no network, no model download on the default path. The same
request returns the same products every time, asserted by test.
