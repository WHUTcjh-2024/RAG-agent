from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from PIL import Image

from app.core.image_encoder import ImageEncoder, create_image_encoder
from app.core.catalog_fields import enrich_commerce_fields
from app.core.retrieval.filters import product_matches_filters


class ImageRetriever:
    def __init__(self, index_dir: str | Path, device: str = "auto") -> None:
        self.index_dir = Path(index_dir).resolve()
        metadata_path = self.index_dir / "metadata.json"
        embeddings_path = self.index_dir / "embeddings.npy"
        products_path = self.index_dir / "products.jsonl"
        for path in (metadata_path, embeddings_path, products_path):
            if not path.is_file():
                raise FileNotFoundError(
                    f"Image index is incomplete; missing {path}. "
                    "Run backend\\scripts\\build_image_index.py first."
                )

        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.embeddings = np.load(embeddings_path, mmap_mode="r")
        with products_path.open("r", encoding="utf-8") as handle:
            self.products = [json.loads(line) for line in handle if line.strip()]

        if self.embeddings.ndim != 2:
            raise RuntimeError("Image embeddings must be a two-dimensional matrix.")
        if len(self.products) != self.embeddings.shape[0]:
            raise RuntimeError("Product metadata and image embedding counts do not match.")
        dimension = int(self.metadata["dimension"])
        if self.embeddings.shape[1] != dimension:
            raise RuntimeError("Image embedding dimension does not match metadata.json.")

        self._device = device
        self._dimension = dimension
        self._encoder: ImageEncoder | None = None
        self._encoder_lock = Lock()

    @property
    def encoder(self) -> ImageEncoder:
        """Load the expensive vision model only when an image query needs it."""
        if self._encoder is None:
            with self._encoder_lock:
                if self._encoder is None:
                    self._encoder = create_image_encoder(
                        backend=self.metadata["backend"],
                        model_name=self.metadata.get("model", ""),
                        device=self._device,
                        dimension=self._dimension,
                    )
        return self._encoder

    def _candidate_indices(self, filters: dict[str, str | list[str]]) -> np.ndarray:
        if not filters:
            return np.arange(len(self.products), dtype=np.int64)
        return np.asarray(
            [
                index
                for index, product in enumerate(self.products)
                if product_matches_filters(product, filters)
            ],
            dtype=np.int64,
        )

    def search(
        self,
        image: Image.Image,
        top_k: int = 10,
        filters: dict[str, str | list[str]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")
        candidate_indices = self._candidate_indices(filters or {})
        total_candidates = int(candidate_indices.size)
        if total_candidates == 0:
            return [], 0

        query_vector = self.encoder.encode([image], batch_size=1)[0]
        candidate_vectors = np.asarray(self.embeddings[candidate_indices])
        scores = candidate_vectors @ query_vector
        result_count = min(top_k, total_candidates)
        if result_count == total_candidates:
            local_order = np.argsort(-scores)
        else:
            partition = np.argpartition(-scores, result_count - 1)[:result_count]
            local_order = partition[np.argsort(-scores[partition])]

        results: list[dict[str, Any]] = []
        for local_index in local_order[:result_count]:
            product_index = int(candidate_indices[local_index])
            product = dict(self.products[product_index])
            product["score"] = round(float(scores[local_index]), 6)
            product["reason"] = "上传图片视觉相似度与结构化筛选匹配"
            results.append(enrich_commerce_fields(product))
        return results, total_candidates
