# Known Limitations

Everything here is a real constraint of the current implementation. Nothing is
worked around silently: where the engine cannot answer well, it reports a
warning or returns fewer results.

## Data

The catalog is an open dataset of product metadata. It has no user interactions,
no prices, no ratings, no reviews and no stock. None of these are simulated, so
there is no collaborative filtering and no popularity signal.

| Limitation | Effect |
|---|---|
| No interaction data | Category affinity weights are declared priors, not learned. They are configurable and could be replaced with mined affinities if behavioural data existed. |
| Beauty occasion labels are unusable | The source marks 2,136 of 2,139 personal care products "Casual". Suitability is derived from shade family and finish instead, which is a model rather than observed data. |
| Sparse occasions | Only 28 products are labelled "party" and 67 "smart_casual". Party requests are served from ethnic, formal and smart-casual products, and the API returns a warning saying so. |
| Thin categories | Eyeshadow has 32 products, blush 37, mascara 12, concealer 11. Men's ethnic bottoms amount to six churidars. These sections are marked `thin` and are not padded. |
| Some records are wrong at source | A few products carry the wrong photograph or a bad occasion label. One novelty T-shirt is labelled "formal". Where this distorts results the code compensates; where it cannot, the bad data shows. |

## Colour model

Colour families carry hue but not saturation or lightness, so the model
expresses a preference ordering rather than a verdict. It cannot detect a
genuine clash. Hue distance is computed in RGB, so red and green score as
triadic rather than complementary.

## Intent extraction

The language model converts a sentence into structured fields. When it is
unavailable the deterministic parser takes over, using a fixed vocabulary of
roughly 35 garment words and 60 colour words. Unusual phrasing is recognised
less often on that path. Unrecognised input is reported rather than guessed.

The Gemini free tier allows a limited number of requests per day, and the
service returns 503 when busy. Either condition switches the app to catalog
matching. The interface shows which mode produced the result.

## Images

The catalog ships 60x80 thumbnails. Higher resolution images are fetched on
demand from a public mirror of the same dataset and cached on disk, so the first
view of an unseen product is slower. A few source photographs are soft even at
full size; these are measured and reported rather than presented as sharp.

## Performance

A recommendation takes roughly 240 ms on a warm engine. This is a linear scan of
each candidate pool. A precomputed colour by occasion matrix would reduce it if
that mattered.

## Scope

The system recommends from a fixed catalog. There is no personalization, no user
accounts and no history. Results depend only on the current query.
