"""Text relevance over `text_blob`.

Why TF-IDF and not sentence embeddings - measured, not assumed
(`scripts/benchmark_retrieval.py`, results in `docs/retrieval_benchmark.json`):

  1. On 12 realistic queries, structured attribute filtering scores P@10 = 1.00,
     embeddings 0.92, TF-IDF 0.84. Both text methods *lose* to the structured
     fields, because category and colour - which is what those queries are
     about - are already columns in the catalog. Text is not the right tool for
     that job and is not used for it here.

  2. Where text genuinely is the only source of signal - material, pattern and
     cut, which live only in the product name - TF-IDF lifts P@10 from ~0.00 to
     1.00 against base rates of 1.1%-47% ("silk" within ethnic_wear: 1.1% base
     rate, 0.00 unranked, 1.00 with TF-IDF).

  3. The catalog has almost no natural-language style vocabulary to embed:
     "elegant" appears in 3 of 43,165 product names and "traditional" in 1.
     A 22M-parameter transformer has nothing to understand here that a term
     match does not already capture.

  4. TF-IDF term overlap can be *shown* to the user ("matched: silk, printed").
     An embedding cosine cannot, and this engine has to explain itself.

So text relevance is a low-weight residual signal for descriptor terms, applied
after structured filtering - never the primary retrieval mechanism.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

# Words carried by the query that the structured fields already handle. Leaving
# them in would let a colour or category term dominate the text score and
# double-count a signal that colour/affinity scoring has already applied.
_STOPWORDS = {
    "a", "an", "the", "for", "with", "and", "or", "my", "i", "im", "want",
    "need", "looking", "suggest", "recommend", "something", "outfit", "look",
    "wear", "wearing", "colour", "color", "occasion", "please", "some",
}

_TOKEN_RE = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class Relevance:
    score: float
    matched_terms: tuple[str, ...]

    @property
    def explanation(self) -> str:
        if not self.matched_terms:
            return "no descriptive terms from the request appear in this product"
        return "matches " + ", ".join(f"'{t}'" for t in self.matched_terms)


class TextRelevance:
    """TF-IDF cosine over `text_blob`, with the matched terms kept for display."""

    def __init__(self, frame: pd.DataFrame):
        self._ids = frame.product_id.to_numpy()
        self._row_of = {int(p): i for i, p in enumerate(self._ids)}
        corpus = frame.text_blob.fillna("").tolist()
        # min_df=2 drops one-off tokens, which is right for the 19,576-product
        # catalog but impossible on a corpus of one or two documents - sklearn
        # raises "max_df corresponds to < documents than min_df". Fall back to 1
        # so a very small candidate pool degrades rather than crashes.
        min_df = 2 if len(corpus) >= 10 else 1
        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, min_df=min_df, lowercase=True,
        )
        self._matrix = self._vectorizer.fit_transform(corpus)
        self._vocabulary = self._vectorizer.vocabulary_
        self._texts = [c.lower() for c in corpus]

    @property
    def vocabulary_size(self) -> int:
        return len(self._vocabulary)

    def query_terms(self, query: str) -> list[str]:
        """Content terms from a query that actually exist in the corpus."""
        seen, terms = set(), []
        for token in _TOKEN_RE.findall((query or "").lower()):
            if len(token) < 3 or token in _STOPWORDS or token in seen:
                continue
            seen.add(token)
            if token in self._vocabulary:
                terms.append(token)
        return terms

    def score(self, query: str, product_ids) -> dict[int, Relevance]:
        """Cosine similarity of `query` against the given products.

        Returns 0.0 for every product when the query carries no usable term, so
        an empty query contributes nothing rather than adding noise.
        """
        ids = [int(p) for p in product_ids]
        terms = self.query_terms(query)
        if not terms:
            return {pid: Relevance(0.0, ()) for pid in ids}

        rows = [self._row_of[p] for p in ids if p in self._row_of]
        if not rows:
            return {pid: Relevance(0.0, ()) for pid in ids}

        query_vector = self._vectorizer.transform([" ".join(terms)])
        sims = (self._matrix[rows] @ query_vector.T).toarray().ravel()
        top = float(sims.max()) if sims.size else 0.0

        out: dict[int, Relevance] = {}
        for pid, row, sim in zip((p for p in ids if p in self._row_of), rows, sims):
            text = self._texts[row]
            matched = tuple(t for t in terms if t in text)
            # Normalise against the best match in this pool so the component
            # spans 0..1 regardless of absolute TF-IDF magnitudes.
            normalised = float(sim / top) if top > 0 else 0.0
            out[pid] = Relevance(normalised, matched)
        for pid in ids:
            out.setdefault(pid, Relevance(0.0, ()))
        return out
