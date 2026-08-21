# StyleSync

StyleSync is a fashion recommendation system that helps users find products and outfit combinations from a catalog of 43,165 items.

Users can search using normal language, for example:

- `black formal shirt for men`
- `what should I wear to a wedding?`
- `date outfit for women`
- `I am wearing a black saree to a wedding`

Depending on the query, the system either finds the requested product or builds a complete outfit.

## Project Overview

The project handles two different tasks:

**Product search:** If the user asks for a specific item, the system finds products that match the request.

**Outfit recommendation:** If the user asks what to wear for an occasion, the system builds a look using suitable clothing, footwear and accessories.

For example, searching for `black formal shirt` should return formal shirts first. Searching for `wedding outfit for men` should build a complete outfit instead of returning unrelated products.

The application uses a FastAPI backend, a React frontend and a catalog containing clothing, footwear, accessories and beauty products.

## Problem Statement

Normal catalog search mainly matches words from a query with product information. That works for finding a specific product, but it does not handle questions such as:

- What should I wear to a wedding?
- What goes with this saree?
- What should I wear for a date?
- Suggest an office outfit for men.

This project combines structured query understanding with a recommendation engine so that the system can understand the request and return relevant products or outfit combinations.

## Use Case and Motivation

The use case is a shopper who has one item, or an occasion, and needs the rest.
They know they are going to a wedding, or they already own a black saree, but
they do not know which shoes, jewellery or lip colour go with it.

I chose this because it is a compatibility problem rather than a similarity
problem, and the two need different techniques. Recommending another saree to
someone holding a saree is a search problem with an obvious answer.
Recommending the lipstick is not, because no purchase history links a drape to a
lip colour. The relationship has to be derived from product attributes: colour,
occasion and formality.

A second problem appeared while building it, and it shaped most of the design. A
system that only models "what goes with what" will answer a search for `red
shirt` with a handbag, because the handbag really does go with a red shirt. It
is a correct answer to a question nobody asked. Separating "does this match what
I searched for" from "does this go with it" became the main design decision in
the project.

The dataset also made the cross-category part possible. Clothing and beauty
products sit in the same catalog under the same colour vocabulary, so a black
saree and a maroon lipstick are described in one attribute space and can be
compared directly.

## How It Works

```text
User Query
    |
    v
Intent Extraction
    |
    v
Query Normalization
    |
    v
Recommendation Engine
    |
    +--> Product Search
    |
    +--> Outfit Composition
    |
    v
Ranked Recommendations
    |
    v
React User Interface
```

### Intent extraction

The system extracts information such as:

- Product or garment
- Colour
- Occasion
- Style
- Gender
- Whether the user already owns the item

Gemini can be used for natural-language intent extraction. If it is unavailable, the application falls back to a deterministic parser so the recommendation system can still work.

### Product matching

For product-specific searches, the requested product type is treated as the primary result.

For example:

```text
Query: black formal shirt for men
```

The system looks for men's shirts matching the requested colour and occasion before recommending complementary products.

### Outfit composition

If the user asks for a complete look, the system selects products from different categories.

```text
Main clothing item
        +
Bottom or matching garment
        +
Footwear
        +
Relevant accessories
```

The outfit structure changes depending on the occasion and gender. A wedding outfit is handled differently from a sports or office outfit.

## Recommendation Approach

This project uses a content and rule-based recommendation approach.

The catalog provides structured attributes such as product category, colour, gender and product information. These attributes are combined with the user's query to filter and rank products.

The LLM is used only for understanding the query. It does not choose product IDs directly. Product selection and ranking are handled by the recommendation engine.

This keeps recommendations tied to actual catalog items.

## Dataset

The system works with a fashion catalog containing **43,165 products** across categories including:

- Clothing
- Footwear
- Accessories
- Beauty products

The catalog is processed into a structured format used by the recommendation engine.

## Technology Stack

### Backend

- Python
- FastAPI
- Pydantic

### Recommendation and data processing

- Pandas
- NumPy
- Scikit-learn
- Custom ranking and compatibility logic

### AI-assisted query understanding

- Google Gemini API
- Deterministic fallback parser

### Frontend

- React
- Vite
- JavaScript

### Testing

- Pytest
- API and recommendation tests

## System Architecture

```text
React Frontend
      |
      | HTTP API
      v
FastAPI Backend
      |
      +--------------------+
      |                    |
      v                    v
Intent Layer        Recommendation Engine
      |                    |
      |                    +--> Filtering
      |                    +--> Scoring
      |                    +--> Diversity
      |                    +--> Outfit composition
      |
      +--> Gemini
      |
      +--> Deterministic fallback
               |
               v
          Product Catalog
               |
               v
        Product Recommendations
```

## Example Queries

### Product search

```text
red kurta for men
blue jeans
black formal shirt
sunglasses
perfume
```

### Outfit requests

```text
wedding outfit for men
date outfit for women
office wear for men
sport outfit for marathon
what should I wear to a wedding?
```

If gender is required for an outfit and is not provided, the application asks the user to choose rather than mixing men's and women's products.

## Evaluation

### Why not precision, recall, NDCG or MAP

Those metrics need relevance labels, and this dataset has none. It is product
metadata with no user interactions, no ratings and no purchase history, so there
is no record of which product a person would actually have picked. Reporting a
precision score would have meant inventing the labels it was measured against,
so I did not report one.

### What is measured instead

Each scenario declares in advance the properties a correct answer must have, and
those properties are checked automatically. The expectations were written before
the evaluator was first run. From `scripts/evaluate_engine.py`:

| Metric | Result | What it checks |
|---|---|---|
| Scenarios passed | 15 / 15 | Declared expectations met |
| Constraint satisfaction | 1.00 | Every product exists in the catalog, is a valid complement, and respects gender and category exclusions |
| Colour compatibility | 0.91 | Share of colour-carrying products whose harmony with the anchor is above threshold |
| Explanation completeness | 1.00 | Share of products carrying a reason and a scored component |
| Candidate coverage | 0.93 | Categories that produced a recommendation, over categories considered |
| Mean category coverage | 4.87 | Distinct categories in a returned look |
| Mean distinct brands | 5.2 | Brand spread per result set |
| Largest single brand share | 0.28 | Diversity check |
| Latency | 240 ms mean | One recommendation on a warm engine |

Diversity, coverage and latency are from the assignment's suggested list and are
measurable here. Constraint satisfaction and explanation completeness cover
things that matter for this system specifically: a recommendation must be a real
catalog product of the right gender, and it must be able to say why it was
chosen.

A separate retrieval benchmark compares text methods on 12 queries where
correctness can be checked from attributes: attribute filtering scored 1.00
precision@10, sentence embeddings 0.92 and TF-IDF 0.84. This is why text
relevance carries the smallest weight in the scoring formula, and why embeddings
were measured and then not adopted.

There are also **328 automated tests** covering catalog normalization, scoring,
API contracts, outfit composition, intent extraction and image handling.

Full results are in [docs/evaluation.md](docs/evaluation.md).

## Example Test Cases

| Query | Expected behaviour |
|---|---|
| `red kurta for men` | Men's kurtas should appear as the primary results |
| `black formal shirt` | Formal shirts should be prioritized |
| `date outfit for women` | Build a women's outfit with relevant categories |
| `wedding outfit for men` | Build a men's wedding look |
| `what should I wear to a wedding?` | Ask for gender before building the outfit |
| `I am wearing a red saree` | Treat the saree as the user's existing item and suggest complementary products |

### Failure and edge scenarios

These are the cases where the system either refuses to answer or answers
imperfectly. They are part of the evaluation suite and behave as described.

| Scenario | What happens |
|---|---|
| Unknown product id as the anchor | Returns 404 with a message. No substitute is guessed. |
| Every category excluded by the request | Returns nothing and warns, rather than ignoring the filter. |
| Unsupported occasion, for example "funeral" | Reported as unrecognised instead of being mapped to something close. |
| Query with nothing usable in it, for example `zzzz qqqq` | Says nothing could be extracted and returns a broad selection. |
| Impossible combination, for example a saree for the gym | Returns what the catalog can support and warns that the occasion is being served from adjacent labels. |
| Rare category requested alone, for example mascara | Section is marked thin. It is not padded with poor matches. |
| Outfit requested without a gender | Asks which gender before building anything, because a mixed outfit is never correct. |
| Anchor colour that resolves to "Multi" | Colour harmony is skipped for that product rather than guessed. |
| Gemini quota exhausted or provider unavailable | Falls back to the rule-based parser. The interface shows "Standard matching". |
| Product with a wrong or low quality source photograph | Reported as low quality rather than presented as sharp. |

Two of these are worth calling out as genuine weaknesses rather than deliberate
behaviour. The rule-based parser uses a fixed vocabulary, so an unusual phrasing
like "smart but not too formal for a dinner date" is understood less precisely
than it would be by the language model. And a handful of catalog products carry
a photograph of the wrong item, which no amount of ranking can fix.

## Assumptions

- The catalog is treated as the source of truth. If a product is labelled
  formal, the system trusts that label even when the product name suggests
  otherwise.
- A query that names a garment is a request to see that garment. A query that
  says the user already owns it is a request for complements.
- Gender is a hard requirement rather than a preference. A men's kurta is not a
  weaker match for a women's outfit, it is the wrong answer.
- Colour compatibility can be approximated from hue relationships between colour
  families. This is a simplification, since the catalog records no saturation or
  lightness.
- Occasion labels are reliable for clothing but not for beauty, where 2,136 of
  2,139 products are labelled "Casual". Beauty suitability is derived instead.
- Category affinity weights are reasonable editorial priors. With no interaction
  data there is nothing to learn them from.
- Users are anonymous. There is no history, so every query is answered on its
  own.

## Known Limitations

- Recommendation quality depends on the quality of the source catalog.
- Some catalog images do not always match the product metadata.
- Some source images may be low quality.
- Gemini availability depends on API quota and provider availability.
- When the AI provider is unavailable, the deterministic parser may understand unusual phrasing less effectively.
- The current system does not use real user interaction history such as clicks, purchases or ratings.

## Future Improvements

- Add user interaction data for collaborative or hybrid recommendations.
- Add user preference profiles.
- Improve semantic retrieval.
- Add feedback such as like, dislike or not relevant.
- Improve image validation for catalog inconsistencies.
- Add personalization based on previous searches.
- Compare different ranking strategies using larger evaluation sets.

## Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/Pratik0870/StyleSync_recommendation.git
cd StyleSync_recommendation
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS/Linux:

```bash
source venv/bin/activate
```

### 3. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file based on `.env.example`.

```env
GEMINI_API_KEY=your_key_here
```

The application can still use the fallback parser when no API key is configured or the provider is unavailable.

### 5. Prepare the catalog

If the processed catalog is not already available:

```bash
python scripts/ingest_catalog.py
```

### 6. Start the backend

Use the project's configured FastAPI startup command.

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the local URL shown by Vite.

## Deployment

**Live application:** https://style-sync-recommendation.vercel.app

**API:** https://stylesync-api-iv3g.onrender.com (health check at `/health`)

The frontend is a static Vite build on Vercel. The backend runs on Render, where
the catalog is built during deploy by `scripts/ingest_catalog.py`. The two are
connected by two environment variables: `VITE_API_BASE` on Vercel points at the
API, and `CORS_ORIGINS` on Render allows the frontend origin.

Both run on free tiers, which has two visible effects. The backend sleeps after
about 15 minutes of inactivity, so the first request after a pause takes 30 to
60 seconds. The disk is not persistent, so high resolution images are re-fetched
on demand after a restart and the first page view is slower than later ones.

Deployment steps are in [DEPLOYMENT.md](DEPLOYMENT.md).

> The `.env` file is git-ignored. API keys are set in the hosting dashboards,
> never committed.

## Project Structure

```text
StyleSync_recommendation/
│
├── src/                 # Backend and recommendation logic
├── frontend/            # React application
├── tests/               # Automated tests
├── scripts/             # Data preparation and evaluation scripts
├── docs/                # Technical documentation
├── data/                # Evaluation and catalog-related files
├── README.md
├── requirements.txt
└── .env.example
```

## Key Design Decisions

- Product search and outfit generation are handled separately.
- Gender is treated as a hard constraint for outfit generation.
- The LLM is used for query understanding rather than selecting products directly.
- A deterministic fallback keeps the application working when the external AI provider is unavailable.
- Recommendations are generated from actual catalog items.

## Comparison With Existing Products

The catalog comes from Myntra, and the product covers both fashion and beauty,
so Myntra and Nykaa are the closest reference points. The interface borrows from
that style of site: a search bar at the top, results grouped into category
sections, and product cards showing brand, name, colour and image.

### Similarities

- Products are grouped into browsable categories such as wardrobe, beauty,
  accessories and footwear.
- Results are cards with brand, product name and attributes, in a grid.
- Search accepts a free text query rather than only filters.
- Both fashion and beauty products sit in the same catalog and can appear in one
  set of results.

### Differences

- Those sites are built around similarity and popularity. If you search for a
  red shirt you get more red shirts, ranked partly by what other people bought.
  StyleSync answers a second question as well: what goes with the red shirt.
- There is no collaborative filtering here. Real platforms have purchase and
  click history; this dataset has none, so recommendations come from product
  attributes only.
- StyleSync builds a complete outfit when the query does not name a product.
  Myntra and Nykaa mostly leave that to editorial content or curated collections.
- Every recommendation shows a reason. Commercial sites rarely explain why an
  item was surfaced.
- There are no prices, ratings, reviews or stock, because the dataset has none.
  Those drive a lot of real ranking and none of it is available here.

### Current limitations compared with those platforms

- No personalization. A real platform knows what you looked at last week; this
  answers each query on its own.
- No business signals. Real ranking factors in margin, stock, delivery time and
  sponsored placement.
- The catalog is fixed and roughly 43,000 items, against millions on a live site,
  so some requests have thin coverage.
- No search-as-you-type, filters on results, wishlists or cart. The interface is
  built to demonstrate the recommendation logic, not to be a store.

### Areas for improvement

- Filters on the results page for price band, brand or size, which is the first
  thing a shopper reaches for.
- Faster first load. Images are fetched on demand, so a cold start is slower
  than a real site would allow.
- Better handling of loose phrasing when the language model is unavailable.

### What I would build next with more time

- Log which recommendations users click, then use that to replace the
  hand-chosen category affinity weights with learned ones. That is the single
  change that would most improve ranking quality.
- Build a relevance test set from those clicks, which would make precision and
  NDCG meaningful for this system.
- Add a "more like this, but in blue" control on each card, so a user can steer
  the results instead of retyping the query.
- Let a user save an outfit and come back to it, which is the first step towards
  personalization.

## What I Learned

The main challenges in this project were understanding user intent, separating product search from outfit composition, handling imperfect catalog data and keeping the application functional when an external AI service is unavailable.

The project helped me understand how structured data, ranking logic, rule-based constraints and AI-assisted natural language understanding can work together in a recommendation system.

## Repository

GitHub: https://github.com/Pratik0870/StyleSync_recommendation
