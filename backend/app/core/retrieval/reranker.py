from __future__ import annotations

import os
from typing import Sequence

import numpy as np

from app.core.retrieval.bm25 import tokenize


class ProductReranker:
    """Cross-encoder when explicitly configured, deterministic lexical fallback otherwise."""

    def __init__(
        self, backend: str | None = None, model_name: str | None = None
    ) -> None:
        self.backend = (
            (backend or os.getenv("RERANKER_BACKEND", "lexical")).strip().casefold()
        )
        self.model_name = model_name or os.getenv(
            "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"
        )
        self._model = None
        if self.backend not in {"lexical", "cross-encoder"}:
            raise ValueError("RERANKER_BACKEND must be 'lexical' or 'cross-encoder'.")

    def _cross_encoder_scores(self, query: str, documents: Sequence[str]) -> np.ndarray:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as error:
                raise RuntimeError(
                    "Cross-encoder reranking requires sentence-transformers."
                ) from error
            self._model = CrossEncoder(self.model_name)
        scores = self._model.predict([(query, document) for document in documents])
        return np.asarray(scores, dtype=np.float32)

    @staticmethod
    def _lexical_scores(query: str, documents: Sequence[str]) -> np.ndarray:
        query_terms = set(tokenize(query))
        if not query_terms:
            return np.zeros(len(documents), dtype=np.float32)
        scores: list[float] = []
        phrase = "".join(query.casefold().split())
        for document in documents:
            terms = set(tokenize(document))
            coverage = len(query_terms & terms) / len(query_terms)
            normalized_document = "".join(document.casefold().split())
            phrase_bonus = (
                0.2 if len(phrase) >= 2 and phrase in normalized_document else 0.0
            )
            scores.append(coverage + phrase_bonus)
        return np.asarray(scores, dtype=np.float32)

    def score(self, query: str, documents: Sequence[str]) -> np.ndarray:
        if self.backend == "cross-encoder":
            return self._cross_encoder_scores(query, documents)
        return self._lexical_scores(query, documents)
