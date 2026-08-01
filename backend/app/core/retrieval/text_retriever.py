from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.core.retrieval.bm25 import BM25Index
from app.core.retrieval.fusion import ranked_ids, reciprocal_rank_fusion
from app.core.retrieval.filters import product_matches_filters
from app.core.retrieval.reranker import ProductReranker
from app.core.retrieval.query_expansion import expand_catalog_query
from app.core.text_encoder import create_text_encoder
from app.core.catalog_fields import enrich_commerce_fields


class TextRetriever:
    def __init__(self, index_dir: str | Path) -> None:
        self.index_dir = Path(index_dir).resolve()
        metadata_path = self.index_dir / "metadata.json"
        embeddings_path = self.index_dir / "embeddings.npy"
        products_path = self.index_dir / "products.jsonl"
        for path in (metadata_path, embeddings_path, products_path):
            if not path.is_file():
                raise FileNotFoundError(
                    f"Text index is incomplete; missing {path}. "
                    "Run backend\\scripts\\build_text_index.py first."
                )

        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.embeddings = np.load(embeddings_path, mmap_mode="r")
        with products_path.open("r", encoding="utf-8") as handle:
            self.products = [json.loads(line) for line in handle if line.strip()]

        if self.embeddings.ndim != 2:
            raise RuntimeError("Text embeddings must be a two-dimensional matrix.")
        if len(self.products) != self.embeddings.shape[0]:
            raise RuntimeError("Product metadata and embedding counts do not match.")
        expected_dimension = int(self.metadata["dimension"])
        if self.embeddings.shape[1] != expected_dimension:
            raise RuntimeError("Embedding dimension does not match metadata.json.")

        self.encoder = create_text_encoder(
            backend=self.metadata["backend"],
            model_name=self.metadata.get("model", ""),
            dimension=expected_dimension,
        )
        lexical_path = self.index_dir / "bm25.json"
        if lexical_path.is_file():
            self.bm25 = BM25Index.from_payload(
                json.loads(lexical_path.read_text(encoding="utf-8"))
            )
        else:
            # Existing local indexes remain readable; the next index build persists it.
            self.bm25 = BM25Index.from_documents(
                str(product.get("text_profile") or "") for product in self.products
            )
        if len(self.bm25.document_terms) != len(self.products):
            raise RuntimeError("BM25 index and product metadata counts do not match.")
        self.reranker = ProductReranker()

    def _candidate_indices(self, filters: dict[str, str | list[str]]) -> np.ndarray:
        if not filters:
            return np.arange(len(self.products), dtype=np.int64)
        indices = [
            index
            for index, product in enumerate(self.products)
            if product_matches_filters(product, filters)
        ]
        return np.asarray(indices, dtype=np.int64)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, str | list[str]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty.")
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")

        candidate_indices = self._candidate_indices(filters or {})
        total_candidates = int(candidate_indices.size)
        if total_candidates == 0:
            return [], 0

        expanded_query = expand_catalog_query(query)
        query_vector = self.encoder.encode([expanded_query])[0]
        dense_scores = np.asarray(self.embeddings[candidate_indices]) @ query_vector
        bm25_scores = self.bm25.scores(expanded_query, candidate_indices)
        candidate_ids = [
            str(self.products[int(index)]["article_id"]) for index in candidate_indices
        ]
        rankings = {
            "dense": ranked_ids(candidate_ids, dense_scores),
            "bm25": ranked_ids(candidate_ids, bm25_scores),
        }
        rrf_scores, source_ranks = reciprocal_rank_fusion(rankings)
        fused_ids = sorted(
            rrf_scores, key=lambda item_id: (-rrf_scores[item_id], item_id)
        )
        rerank_ids = fused_ids[: min(len(fused_ids), max(top_k * 10, 50))]
        positions = {item_id: offset for offset, item_id in enumerate(candidate_ids)}
        reranker_scores = self.reranker.score(
            expanded_query,
            [
                str(
                    self.products[int(candidate_indices[positions[item_id]])].get(
                        "text_profile"
                    )
                    or ""
                )
                for item_id in rerank_ids
            ],
        )
        rerank_score_by_id = dict(zip(rerank_ids, map(float, reranker_scores)))
        ordered_ids = sorted(
            rerank_ids,
            key=lambda item_id: (
                -rerank_score_by_id[item_id],
                -rrf_scores[item_id],
                item_id,
            ),
        )[:top_k]
        results: list[dict[str, Any]] = []
        for article_id in ordered_ids:
            local_index = positions[article_id]
            product = dict(self.products[int(candidate_indices[local_index])])
            source_rank = source_ranks[article_id]
            product.update(
                {
                    "score": round(rrf_scores[article_id], 8),
                    "reason": "BM25 与语义召回经 RRF 融合并重排",
                    "retrieval": {
                        "index_version": self.metadata.get("version", 1),
                        "sources": sorted(source_rank),
                        "source_ranks": source_rank,
                        "dense_score": round(float(dense_scores[local_index]), 6),
                        "bm25_score": round(float(bm25_scores[local_index]), 6),
                        "rrf_score": round(rrf_scores[article_id], 8),
                        "reranker_score": round(rerank_score_by_id[article_id], 6),
                        "reranker_backend": self.reranker.backend,
                        "query_expansion": expanded_query,
                    },
                }
            )
            results.append(enrich_commerce_fields(product))
        return results, total_candidates
