from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.core.retrieval.filters import product_matches_filters
from app.core.retrieval.fusion import ranked_ids, reciprocal_rank_fusion
from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.query_expansion import expand_catalog_query
from app.core.retrieval.text_retriever import TextRetriever
from app.core.catalog_fields import enrich_commerce_fields


class HybridRetriever:
    def __init__(
        self,
        text_index_dir: str | Path,
        image_index_dir: str | Path,
        image_device: str = "auto",
    ) -> None:
        self.text_retriever = TextRetriever(text_index_dir)
        self.image_retriever = ImageRetriever(image_index_dir, device=image_device)

        self.text_positions = {
            str(product.get("article_id", "")): index
            for index, product in enumerate(self.text_retriever.products)
            if product.get("article_id")
        }
        self.image_positions = {
            str(product.get("article_id", "")): index
            for index, product in enumerate(self.image_retriever.products)
            if product.get("article_id")
        }
        common_ids = self.text_positions.keys() & self.image_positions.keys()
        if not common_ids:
            raise RuntimeError(
                "Text and image indexes have no common article_id values."
            )
        self.common_ids = sorted(common_ids)

    def search(
        self,
        query: str,
        image: Image.Image,
        top_k: int = 10,
        filters: dict[str, str | list[str]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query = query.strip()
        if not query:
            raise ValueError("Hybrid search query cannot be empty.")
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")
        applied_filters = filters or {}

        candidate_ids = [
            article_id
            for article_id in self.common_ids
            if product_matches_filters(
                self.image_retriever.products[self.image_positions[article_id]],
                applied_filters,
            )
        ]
        total_candidates = len(candidate_ids)
        if total_candidates == 0:
            return [], 0

        expanded_query = expand_catalog_query(query)
        text_query = self.text_retriever.encoder.encode([expanded_query], batch_size=1)[
            0
        ]
        image_query = self.image_retriever.encoder.encode([image], batch_size=1)[0]
        text_indices = np.asarray(
            [self.text_positions[article_id] for article_id in candidate_ids],
            dtype=np.int64,
        )
        image_indices = np.asarray(
            [self.image_positions[article_id] for article_id in candidate_ids],
            dtype=np.int64,
        )
        text_raw = np.asarray(self.text_retriever.embeddings[text_indices]) @ text_query
        image_raw = (
            np.asarray(self.image_retriever.embeddings[image_indices]) @ image_query
        )
        bm25_scores = self.text_retriever.bm25.scores(expanded_query, text_indices)
        rankings = {
            "dense": ranked_ids(candidate_ids, text_raw),
            "bm25": ranked_ids(candidate_ids, bm25_scores),
            "image": ranked_ids(candidate_ids, image_raw),
        }
        rrf_scores, source_ranks = reciprocal_rank_fusion(rankings)
        fused_ids = sorted(
            rrf_scores, key=lambda item_id: (-rrf_scores[item_id], item_id)
        )
        rerank_ids = fused_ids[: min(len(fused_ids), max(top_k * 10, 50))]
        candidate_positions = {
            article_id: index for index, article_id in enumerate(candidate_ids)
        }
        reranker_scores = self.text_retriever.reranker.score(
            expanded_query,
            [
                str(
                    self.text_retriever.products[self.text_positions[article_id]].get(
                        "text_profile"
                    )
                    or ""
                )
                for article_id in rerank_ids
            ],
        )
        reranker_score_by_id = dict(zip(rerank_ids, map(float, reranker_scores)))
        ordered_ids = sorted(
            rerank_ids,
            key=lambda item_id: (
                -reranker_score_by_id[item_id],
                -rrf_scores[item_id],
                item_id,
            ),
        )[:top_k]

        results: list[dict[str, Any]] = []
        for article_id in ordered_ids:
            index = candidate_positions[article_id]
            product = dict(
                self.image_retriever.products[self.image_positions[article_id]]
            )
            source_rank = source_ranks[article_id]
            product.update(
                {
                    "score": round(rrf_scores[article_id], 8),
                    "reason": "文本语义、BM25 与图片召回经 RRF 融合并重排",
                    "retrieval": {
                        "index_version": self.text_retriever.metadata.get("version", 1),
                        "sources": sorted(source_rank),
                        "source_ranks": source_rank,
                        "dense_score": round(float(text_raw[index]), 6),
                        "bm25_score": round(float(bm25_scores[index]), 6),
                        "image_score": round(float(image_raw[index]), 6),
                        "rrf_score": round(rrf_scores[article_id], 8),
                        "reranker_score": round(reranker_score_by_id[article_id], 6),
                        "reranker_backend": self.text_retriever.reranker.backend,
                        "query_expansion": expanded_query,
                    },
                }
            )
            results.append(enrich_commerce_fields(product))
        return results, total_candidates
