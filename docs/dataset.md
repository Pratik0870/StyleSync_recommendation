# Dataset

How the catalog was built and validated, and what it does not contain.
**Date:** 2026-08-19
**Machine-readable companion:** [`data_quality_report.json`](data_quality_report.json)

Every figure in this document is produced by `scripts/ingest_catalog.py` and
regenerated on each run. Nothing here is estimated.

---

## A. Dataset license status

**Verified: MIT.**

| | |
|---|---|
| Working dataset | [`ashraq/fashion-product-images-small`](https://huggingface.co/datasets/ashraq/fashion-product-images-small) (Hugging Face) |
| Upstream source | [`paramaggarwal/fashion-product-images-small`](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small) (Kaggle) |
| Declared license | **MIT** |
| Attribution | Param Aggarwal (dataset author) |
| Access | Anonymous — no Kaggle account, no HF token, no credentials of any kind |

**How it was verified.** Neither Hugging Face mirror declares a license in its dataset
card; the HF card states only that the data "was obtained from" the Kaggle dataset. The
license therefore had to be read from the Kaggle source. The Kaggle page is
JavaScript-rendered, so the declaration was extracted from the embedded schema.org
metadata:

```
"license":{"@type":"CreativeWork","name":"MIT","url":"https://www.mit.edu/~amini/LICENSE.md"}
```

The same MIT declaration is present on both the `-small` variant we use and the full
`fashion-product-images-dataset`. The result was reproduced across repeat requests.

**Image source (the engine).** High-resolution images will come from
[`benitomartin/fashion-product-images-small-900x1200`](https://huggingface.co/datasets/benitomartin/fashion-product-images-small-900x1200),
a re-render of the *same* Kaggle catalog and therefore covered by the same upstream MIT
declaration. That mirror's own card declares no license, which is why the upstream
Kaggle declaration is the governing statement for both.

**Stated honestly:** MIT is the license the *dataset author* applied to the compilation.
The underlying photographs and product names are Myntra's commercial catalog content.
The MIT declaration is what governs our use of the dataset as published, and it is
sufficient for this project's research/assignment use. It is not a transfer of Myntra's
own rights in the imagery. **Nothing has been published, and nothing will be published
without re-confirming this.**

---

## B. Final usable product count

| Stage | Rows |
|---|---|
| Source rows | 44,072 |
| Removed — non-product categories (Home, Sporting Goods, Free Items) | −131 |
| Removed — duplicate listings (identical image bytes) | −776 |
| Removed — missing/blank product name | −0 |
| Removed — unusable image | −0 |
| **Final catalog** | **43,165** |

Retention: **97.9%**. The source is unusually clean — no missing names, no broken images.

### On what was *not* removed

An earlier pass de-duplicated on product name and cut 12,665 rows. That was **wrong** and
was reverted. Myntra reuses generic display names across genuinely distinct products:

| Display name | Distinct products sharing it |
|---|---|
| Lucera Women Silver Earrings | 82 |
| Lucera Women Silver Pendant | 56 |
| Lucera Women Silver Ring | 50 |
| Catwalk Women Black Heels | 49 |
| Q&Q Men Black Dial Watch | 42 |

Each has its own product ID and its own photograph. Collapsing them would have destroyed
exactly the candidate variety a recommender depends on. De-duplication is therefore done
on **identical image bytes** only, and shared names are *flagged* instead
(`name_is_generic`, `name_shared_by`) so later stages know a name is not distinctive.

---

## C. Category distribution

### By domain

| Domain | Products | Share |
|---|---|---|
| Apparel | 20,628 | 47.8% |
| Accessory | 11,216 | 26.0% |
| Footwear | 9,188 | 21.3% |
| **Beauty / Personal Care** | **2,133** | **4.9%** |

### By category group (the normalised taxonomy, 30 groups)

| Group | n | Group | n | Group | n |
|---|---|---|---|---|---|
| topwear | 12,078 | eyewear | 1,058 | headwear | 293 |
| bag | 3,058 | accessory_other | 1,023 | beauty_nails | 284 |
| ethnic_wear | 2,944 | fragrance | 1,004 | outerwear | 270 |
| footwear_casual | 2,843 | wallet | 926 | beauty_face | 155 |
| watch | 2,539 | belt | 812 | beauty_eye | 141 |
| bottomwear | 2,387 | footwear_formal | 636 | beauty_skincare | 102 |
| footwear_flat | 2,375 | neckwear | 619 | apparel_set | 37 |
| footwear_sports | 2,014 | dress | 467 | beauty_hair | 19 |
| innerwear | 1,782 | loungewear | 462 | beauty_tools | 4 |
| footwear_dress | 1,332 | beauty_lip | 425 | | |
| jewellery | 1,076 | | | | |

### By occasion (`usage`)

casual 33,637 · sports 3,976 · **ethnic 3,188** · formal 2,243 · smart_casual 67 · party 28 · travel 26

### By audience

women 18,749 · men 22,328 · unisex 2,088 — of which adult 42,078, kids 1,087

---

## D. Beauty / personal-care product count

**2,133 products.** 1,563 are women's or unisex.

| Category group | n | Product types |
|---|---|---|
| fragrance | 1,003 | Perfume & Body Mist 599, Deodorant 347, Fragrance Gift Set 57 |
| **beauty_lip** | **425** | Lipstick 260, Lip Gloss 109, Lip Liner 45, Lip Care 7, Lip Plumper 4 |
| **beauty_nails** | **284** | Nail Polish 278, Nail Essentials 6 |
| **beauty_face** | **155** | Foundation & Primer 68, Compact 39, Highlighter & Blush 37, Concealer 11 |
| **beauty_eye** | **141** | Kajal & Eyeliner 93, Eyeshadow 32, Mascara 12, Eye Cream 4 |
| beauty_skincare | 102 | moisturisers, cleansers, sunscreen, masks, serums |
| beauty_hair | 19 | Hair Colour |
| beauty_tools | 4 | grooming kits, accessories |

Real brands present, with counts across colour cosmetics: **Lakme** 101, **Colorbar** 100,
**Revlon** 76, **Lotus Herbals** 54, **Streetwear** 37, **Deborah** 27.

**Colour coverage on beauty: 100%.**

---

## E. Fashion / accessory product count

**41,032 products** across apparel (20,628), accessories (11,216) and footwear (9,188).

Categories that matter for cross-category recommendation:

| Complement category | n | Anchor category | n |
|---|---|---|---|
| Bags (handbag, clutch, backpack…) | 3,058 | Ethnic wear (kurta, saree, lehenga…) | 2,944 |
| Watches | 2,539 | Topwear | 12,078 |
| Dress footwear (heels, booties) | 1,332 | Bottomwear | 2,387 |
| Flat footwear (flats, sandals) | 2,375 | Dresses | 467 |
| **Jewellery** (earring, necklace, ring, bangle, bracelet, pendant) | **1,076** | Outerwear | 270 |
| Eyewear | 1,058 | | |
| Neckwear (dupatta, stole, scarf, tie) | 619 | | |

**Anchor candidates: 18,183. Complement candidates: 19,576.** No category group is both —
enforced by test.

### Flagship query is answerable

For *"black saree for a wedding"*: **22 black sarees** exist (427 sarees overall,
13 colour families). Complement pools for a women's/unisex adult look:

bag 2,963 · footwear_dress 1,319 · watch 1,043 · footwear_flat 1,029 · jewellery 1,011 ·
wallet 486 · eyewear 469 · fragrance 435 · **beauty_lip 425** · neckwear 288 ·
**beauty_nails 284** · belt 271 · headwear 179 · **beauty_face 155** · **beauty_eye 141**

---

## F. baseColour coverage

**100% — zero nulls across all 43,165 products, on fashion and beauty alike.**
This is the attribute the whole cross-category concept rests on, and it is complete.

| Metric | Value |
|---|---|
| `base_colour` populated | **100.00%** |
| `colour_family` resolved | **100.00%** |
| Representative hex resolved | 99.09% (391 "Multi" products have no single hex — correct) |
| Source colour values | 46 → normalised to **15 families** |

**Family distribution:** black 9,566 · blue 6,668 · white 5,515 · brown 3,579 ·
grey 3,398 · red 2,974 · green 2,479 · pink 1,910 · purple 1,749 · beige 1,447 ·
silver 1,124 · yellow 835 · gold 779 · orange 751 · multi 391

### Colour semantics — not every colour means the same thing

A meaningful finding: `beauty_face` is 127/155 beige, because foundation and compact
shades describe **skin**, not a style choice. Matching a foundation shade to a saree would
be nonsense. Every product therefore carries a `colour_role`:

| `colour_role` | n | Meaning |
|---|---|---|
| **style** | 36,637 | Colour is a look decision (lipstick, saree, handbag, heels) |
| **packaging** | 6,410 | Colour describes the container (perfume bottle, face wash) |
| **skin_match** | 118 | Colour is the wearer's skin tone (foundation, concealer, compact) |

Only the 36,637 `style` products may be colour-matched to an anchor.

### Colour cosmetics by family — the usable matching surface

| Family | lip | eye | nails | face |
|---|---|---|---|---|
| brown | 128 | 8 | 33 | 2 |
| pink | 102 | 5 | 72 | 14 |
| red | 101 | 0 | 46 | 0 |
| purple | 60 | 13 | 35 | 1 |
| orange | 13 | 0 | 17 | 6 |
| gold | 7 | 11 | 14 | 5 |
| black | 2 | 40 | 6 | 0 |
| blue | 0 | 27 | 14 | 0 |
| green | 2 | 18 | 9 | 0 |
| beige | 5 | 4 | 6 | 127 |

Lip and nail products span the warm/cool range well. Eye products concentrate in
black (kajal), which is accurate for this market.

---

## G. Image availability

**100% — all 44,072 source images decoded successfully; zero failures.**

Validation actually opened and decoded every image rather than checking that a field was
non-empty.

| Check | Result |
|---|---|
| Rows checked | 44,072 |
| Decoded successfully | 44,072 (**100.00%**) |
| Corrupt / truncated | 0 |
| Missing bytes | 0 |
| Below minimum size | 0 |
| Every catalog product has an image | **Yes** |

**Resolution:** 60×80 for 43,153 of 43,165. A tail of 12 products is slightly smaller
(53–54 px wide; 75–79 px tall) — usable, but recorded per product in `image_width` /
`image_height` so the engine can handle them.

**Storage.** The source JPEGs are 60×80 yet average **12.8 KB** — stored at near-zero
compression. Re-encoding the identical pixels at JPEG q88 produced a **62 MB** store from
**555 MB** of source bytes, a ~9× reduction with no visible difference at this size.

**High-resolution path is verified and ready.** `image_fetch_index.csv` maps every
`product_id` to its row offset in the 900×1200 mirror. Alignment was tested on 6 products
spread across the file (offsets 3,994 → 33,760): **6/6 exact ID matches**. the engine can
fetch real 900×1200 photography for any subset without downloading the 6.3 GB mirror.

---

## H. Data quality issues

| # | Issue | Severity | Status |
|---|---|---|---|
| 1 | **`usage` is meaningless for beauty** — 2,136 of 2,139 personal-care rows are labelled "Casual" regardless of product | **High** | Carried, but every beauty row is flagged `occasion_reliable = 0`. **2,133 rows unreliable, 41,032 reliable.** Beauty occasion must be derived in the engine, never read from this column. |
| 2 | **No price data anywhere** | High (by decision, deferred) | Out of scope for the catalog build per project decision. No price column exists in the catalog. **No prices were fabricated.** |
| 3 | **No ratings, reviews or popularity signal** | Medium | The dataset has none. Popularity must come from within-catalog frequency (e.g. brand × category density) or be dropped. Not invented. |
| 4 | **Generic display names** — **16,780 products (38.9%)** share their display name with at least one other product; 82 are all named "Lucera Women Silver Earrings" | **High for text retrieval** | Not removed (see §B). Flagged via `name_is_generic` / `name_shared_by`. At 38.9%, name-based semantic similarity alone would collapse large blocks of the catalog into indistinguishable candidates — the engine must weight structured attributes, not just `text_blob`. |
| 5 | **Source colour errors** — e.g. ids 47153/47154 share one photograph but are labelled "Pink Capris" and "Black Capris" | Low | Caught by image-hash de-duplication; one of each such pair removed (776 total). |
| 6 | **Casing inconsistency in names** — "United Colors of Benetton" also appears as "Of", "united Colors Of", "united colors of" | Low | Resolved: brand matching is case-insensitive with a canonical casing per brand. Recovered 63 products. |
| 7 | **Occasion vocabulary is thin at the top end** — only 28 "party" and 67 "smart_casual" products | Medium | Real limitation. "Ethnic" (3,188) and "Formal" (2,243) are well populated, so wedding/festive queries are supported; explicit "party" queries will need to map onto adjacent occasions in the engine. |
| 8 | **Thin beauty sub-categories** — Eyeshadow 32, Highlighter & Blush 37, Mascara 12, Concealer 11 | Medium | Usable but shallow. the engine must report per-category candidate counts and say when a category is thin rather than returning a poor match. |
| 9 | **No brand column in source** | Low | Resolved: brand derived from the corpus (see §I). 99.59% coverage, 392 brands. |
| 10 | **Catalog is 2007–2019 Myntra data** | Low | Products are dated; the recommendation problem is unaffected. |
| 11 | **Inefficient source image encoding** (12.8 KB per 60×80 JPEG) | Low | Resolved by re-encoding (§G). |

---

## I. Final normalized schema

`data/processed/catalog.parquet` / `.csv` / `.db` — **43,165 rows × 32 columns.**

### Identity
| Column | Type | Coverage | Notes |
|---|---|---|---|
| `product_id` | int | 100% | Source `id`; primary key, unique index |
| `name` | text | 100% | Cleaned `productDisplayName` |
| `brand` | text | **99.59%** | Derived — no source column (see below) |

### Category
| Column | Type | Coverage | Notes |
|---|---|---|---|
| `domain` | text | 100% | apparel · accessory · footwear · beauty |
| `category_group` | text | 100% | 30 normalised groups |
| `product_type` | text | 100% | Source `articleType` (141 values) |
| `master_category`, `sub_category` | text | 100% | Source values, retained for traceability |

### Colour — the cross-category join key
| Column | Type | Coverage | Notes |
|---|---|---|---|
| `base_colour` | text | **100%** | Source `baseColour`, 46 values |
| `colour_family` | text | **100%** | 15 families |
| `colour_hex` | text | 99.09% | Representative hex; null for "Multi" |
| `is_neutral` | bool | 100% | Black, white, grey, beige, nude, skin |
| `is_metallic` | bool | 100% | Gold, silver, bronze, copper |
| `colour_role` | text | 100% | style · skin_match · packaging |
| `colour_meaningful` | bool | 100% | True iff `colour_role = 'style'` |

### Context
| Column | Type | Coverage | Notes |
|---|---|---|---|
| `occasion` | text | 100% | casual · ethnic · formal · sports · party · smart_casual · travel |
| `occasion_reliable` | bool | 100% | **False for all 2,133 beauty rows** |
| `gender` | text | 100% | women · men · unisex |
| `age_group` | text | 100% | adult · kids |
| `season`, `year` | text/int | 100% | 2007–2019 |
| `finish` | text | beauty only | matte · shimmer · metallic · satin · gloss, parsed from name |

### Roles
| Column | Type | Notes |
|---|---|---|
| `can_be_anchor` | bool | 18,183 — the garment a user says they are wearing |
| `can_be_complement` | bool | 19,576 — recommendable alongside an anchor |

### Image
| Column | Type | Notes |
|---|---|---|
| `image_width`, `image_height` | int | Measured by decoding, not assumed |
| `image_md5` | text | Duplicate detection (parquet/CSV only) |
| `image_ok` | bool | True for every catalog row |
| `source_row_index` | int | Offset for high-resolution fetch — **verified 6/6** |

### Derived text
| Column | Type | Notes |
|---|---|---|
| `text_blob` | text | Flattened attributes, prepared for the semantic retrieval |
| `name_is_generic`, `name_shared_by` | bool/int | Display-name distinctiveness |

**Brand derivation.** The dataset has no brand column. A lexicon of **392 brands** was
derived from the corpus itself: a leading token starting ≥5 products is a candidate,
extended token-by-token while the longer prefix still accounts for ≥60% of the shorter
one's products, then trimmed so a brand can never end on an audience word ("Catwalk
Women" → "Catwalk"), a colour word, or a connector ("United Colors of" → "United Colors
of Benetton"). Brands whose first token *is* a colour word are recovered separately, so
"Red Tape" survives. Matching is case-insensitive with canonical casing.
**Coverage 99.59%**; the unmatched 0.41% are genuine long-tail labels.

**SQLite indexes:** `(category_group, colour_family)`, `(domain, category_group)`,
`(can_be_complement, category_group)`, `(can_be_anchor, colour_family)`, unique `product_id`.

---

## J. Files created

### Code
| Path | Purpose |
|---|---|
| `src/catalog/taxonomy.py` | Controlled vocabularies: colour map (46→15), domain map, 141 article types → 30 groups, occasion, audience, colour-role rules |
| `src/catalog/normalize.py` | Pure normalisation functions — no I/O, no scoring |
| `scripts/ingest_catalog.py` | The reproducible pipeline: download → validate → normalise → clean → export → report |
| `tests/test_normalize.py` | **47 unit tests, all passing**, run without the dataset |

### Data (`data/processed/`, 87 MB)
| File | Size | Contents |
|---|---|---|
| `catalog.parquet` | 3.6 MB | Normalised catalog, 43,165 × 32 |
| `images_thumb.parquet` | 62 MB | Re-encoded 60×80 images, keyed by product_id |
| `image_fetch_index.csv` | 0.5 MB | product_id → hi-res mirror row offset |

### Cache & docs
| Path | Notes |
|---|---|
| `data/raw/parquet/*.parquet` | 259 MB source cache; re-downloaded only if absent |
| `docs/data_quality_report.json` | Machine-readable metrics |
| `docs/DATA_QUALITY_REPORT.md` | This document |
| `static/sample_images/` | 24 decoded PNGs for visual QA (not committed) |

**Not created, by design:** no UI, no API, no LLM code, no scoring or ranking logic, no
price column, no fabricated products.

---

## K. How the data can be reproduced

```bash
pip install pandas pyarrow pillow pytest      # already present in this environment
python -m pytest tests/ -q                    # 47 tests, no dataset needed
python scripts/ingest_catalog.py              # ~90 s warm, ~2 min cold
```

The script is **idempotent** and safe to re-run: source shards are cached by exact byte
size and re-downloaded only if missing, outputs are overwritten, and the QA sample
directory is cleared so stale files cannot be mistaken for current output.

Guarantees that make the result trustworthy rather than merely repeatable:

- **No credentials.** Anonymous HTTPS to Hugging Face; no Kaggle account, no tokens.
- **Fails loudly on drift.** `assert_vocabularies_complete()` aborts the build if the
  source ever introduces a colour, article type, usage or gender value that is not
  explicitly mapped. Unknown values can never silently become "other".
- **Deterministic.** No sampling, no randomness, no timestamps in the output. Identical
  input produces byte-identical output.
- **Self-documenting.** Every run regenerates `data_quality_report.json`, so the numbers
  in this document cannot drift away from the data.

Pinned source: `ashraq/fashion-product-images-small`, 44,072 rows, 2 parquet shards
(136.1 MB + 135.4 MB), fetched via the HF `datasets-server` parquet endpoint.

---

## L. What the engine needs from the catalog

the engine is the recommendation engine. The foundation gives it the following, and these
are the things it should build on:

### Ready to use

1. **A complete colour join.** `colour_family` (15 values) + `colour_hex` + `is_neutral` +
   `is_metallic`, at 100% coverage, in one vocabulary shared by sarees and lipsticks.
   This is what makes cross-category matching computable rather than guessed.
2. **A clean anchor/complement split.** 18,183 anchors, 19,576 complements, provably
   disjoint. Filtering "don't recommend the category they already have" is one column.
3. **30 category groups** to define category-affinity, plus `domain` for coarse targeting.
4. **`text_blob`** on every product, ready to embed for semantic retrieval.
5. **Images guaranteed present** for every product, plus a verified path to 900×1200.

### Must be respected

6. **`occasion_reliable = 0` on all 2,133 beauty rows.** Beauty occasion-suitability has
   to be derived from product type, finish and shade family. Reading `occasion` for a
   beauty product is a bug.
7. **`colour_role`.** Only `style` products may be colour-matched. Never match a
   foundation shade (`skin_match`) or a perfume bottle (`packaging`) to an outfit colour.
8. **`name_is_generic` — this affects 38.9% of the catalog.** Text similarity over
   "Lucera Women Silver Earrings" cannot separate 82 different earrings. Semantic
   retrieval over `text_blob` must be combined with structured attribute matching, not
   used on its own.
9. **Thin categories.** Eyeshadow 32, Blush 37, Mascara 12, Concealer 11. Report
   candidate counts; say "no strong match" rather than returning a weak one.
10. **Party occasion is nearly empty** (28 products). Wedding/festive queries should map
    onto `ethnic` (3,188) and `formal` (2,243), which are well populated.

### Still to be built in the engine

11. **Occasion enrichment for beauty** — the one derived attribute the source cannot give.
12. **A colour-harmony table** over the 15 families (contrast, analogous, metallic,
    neutral-pairing), which does not exist yet.
13. **Category-affinity weights** — which complement groups matter for which anchor.
14. **Embeddings + index** over `text_blob`.
15. **A working subset decision.** The catalog is the full 43,165. the engine may want to
    restrict to women's/unisex adult products (20,350) for the core experience —
    the data supports either choice, and nothing has been narrowed prematurely.

### Explicitly still absent

No price, no ratings, no reviews, no user interactions. Any the engine component that needs
these must either derive a documented proxy or be dropped — **not** filled with invented
values.
