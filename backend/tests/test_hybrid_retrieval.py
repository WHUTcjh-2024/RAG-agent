from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.search import get_hybrid_retriever
from app.core.retrieval.hybrid_retriever import HybridRetriever
from app.core.retrieval.image_retriever import ImageRetriever
from app.core.retrieval.text_retriever import TextRetriever
from app.main import app
from tests.test_image_retrieval import create_image_fixture


def build_fixture_indexes(root: Path) -> tuple[Path, Path, Path]:
    csv_path, query_image = create_image_fixture(root)
    text_index = root / "text_index"
    image_index = root / "image_index"
    commands = [
        [
            sys.executable,
            str(BACKEND_DIR / "scripts" / "build_text_index.py"),
            "--input_csv",
            str(csv_path),
            "--index_dir",
            str(text_index),
            "--backend",
            "hashing",
        ],
        [
            sys.executable,
            str(BACKEND_DIR / "scripts" / "build_image_index.py"),
            "--input_csv",
            str(csv_path),
            "--index_dir",
            str(image_index),
            "--backend",
            "pixel",
        ],
    ]
    for command in commands:
        completed = subprocess.run(
            command, cwd=PROJECT_DIR, capture_output=True, text=True
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    return text_index, image_index, query_image


def test_hybrid_api_fuses_text_image_and_filters(tmp_path: Path, monkeypatch) -> None:
    text_index, image_index, query_image = build_fixture_indexes(tmp_path)
    monkeypatch.setenv("TEXT_INDEX_DIR", str(text_index))
    monkeypatch.setenv("IMAGE_INDEX_DIR", str(image_index))
    get_hybrid_retriever.cache_clear()

    with TestClient(app) as client:
        with query_image.open("rb") as handle:
            response = client.post(
                "/api/search/hybrid",
                data={
                    "query": "red shirt",
                    "top_k": "2",
                    "filters": '{"category":"shirt"}',
                },
                files={"file": ("red-shirt.jpg", handle, "image/jpeg")},
            )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_candidates"] == 2
    assert payload["pipeline"] == ["dense", "bm25", "image", "rrf", "rerank"]
    top = payload["results"][0]
    assert top["article_id"] == "0000000001"
    assert set(top["retrieval"]["sources"]) == {"bm25", "dense", "image"}
    assert top["retrieval"]["source_ranks"]
    assert top["score"] == pytest.approx(top["retrieval"]["rrf_score"])
    get_hybrid_retriever.cache_clear()


def test_hybrid_api_requires_both_modalities(tmp_path: Path, monkeypatch) -> None:
    text_index, image_index, _ = build_fixture_indexes(tmp_path)
    monkeypatch.setenv("TEXT_INDEX_DIR", str(text_index))
    monkeypatch.setenv("IMAGE_INDEX_DIR", str(image_index))
    get_hybrid_retriever.cache_clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/search/hybrid",
            data={"query": "red shirt", "top_k": "2", "filters": "{}"},
        )
    assert response.status_code == 422
    get_hybrid_retriever.cache_clear()


def test_hybrid_retriever_reuses_preloaded_indexes(tmp_path: Path) -> None:
    text_index, image_index, _ = build_fixture_indexes(tmp_path)
    text_retriever = TextRetriever(text_index)
    image_retriever = ImageRetriever(image_index, device="cpu")

    hybrid_retriever = HybridRetriever(
        text_index,
        image_index,
        image_device="cpu",
        text_retriever=text_retriever,
        image_retriever=image_retriever,
    )

    assert hybrid_retriever.text_retriever is text_retriever
    assert hybrid_retriever.image_retriever is image_retriever
