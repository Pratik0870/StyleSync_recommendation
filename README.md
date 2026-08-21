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

The project includes automated evaluation scenarios and test cases covering product searches, outfit requests and edge cases.

The latest project verification included:

- **328 automated tests passing**
- **15/15 evaluation scenarios passing**
- Mean measured recommendation latency of approximately **240 ms** in the documented evaluation run

The evaluation checks whether the returned recommendations satisfy the expected constraints for the scenario, such as product type, gender, colour or occasion.

## Example Test Cases

| Query | Expected behaviour |
|---|---|
| `red kurta for men` | Men's kurtas should appear as the primary results |
| `black formal shirt` | Formal shirts should be prioritized |
| `date outfit for women` | Build a women's outfit with relevant categories |
| `wedding outfit for men` | Build a men's wedding look |
| `what should I wear to a wedding?` | Ask for gender before building the outfit |
| `I am wearing a red saree` | Treat the saree as the user's existing item and suggest complementary products |

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

Add the live application URL here after deployment.

The deployment requires:

1. Hosting the FastAPI backend.
2. Making the catalog available during the build or runtime.
3. Configuring environment variables such as `GEMINI_API_KEY`.
4. Building the React frontend with the production backend URL.

> Do not commit the `.env` file or API keys to GitHub.

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

## What I Learned

The main challenges in this project were understanding user intent, separating product search from outfit composition, handling imperfect catalog data and keeping the application functional when an external AI service is unavailable.

The project helped me understand how structured data, ranking logic, rule-based constraints and AI-assisted natural language understanding can work together in a recommendation system.

## Repository

GitHub: https://github.com/Pratik0870/StyleSync_recommendation
