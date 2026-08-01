from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.retrieval.bm25 import BM25Index, tokenize
from app.core.retrieval.fusion import reciprocal_rank_fusion
from app.core.retrieval.reranker import ProductReranker
from app.core.retrieval.query_expansion import expand_catalog_query


def test_mixed_chinese_tokenization_and_bm25_ranking() -> None:
    assert "衬衫" in tokenize("通勤白色衬衫")
    index = BM25Index.from_documents(["白色 通勤 衬衫", "黑色 连衣裙"])
    scores = index.scores("白色衬衫", np.asarray([0, 1], dtype=np.int64))
    assert scores[0] > scores[1]


def test_rrf_retains_rank_origin_for_trace() -> None:
    scores, origins = reciprocal_rank_fusion(
        {"dense": ["a", "b"], "bm25": ["b", "a"], "image": ["b"]}
    )
    assert scores["b"] > scores["a"]
    assert origins["b"] == {"dense": 2, "bm25": 1, "image": 1}


def test_lexical_reranker_prefers_query_coverage() -> None:
    reranker = ProductReranker(backend="lexical")
    scores = reranker.score("白色衬衫", ["白色衬衫 通勤", "黑色连衣裙"])
    assert scores[0] > scores[1]


def test_chinese_query_expansion_is_deterministic_and_catalog_aligned() -> None:
    assert expand_catalog_query("白色通勤衬衫") == "白色通勤衬衫 white shirt office"
