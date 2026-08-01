from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.search import get_text_retriever
from app.main import app


def create_fixture_csv(path: Path) -> None:
    fieldnames = [
        "article_id",
        "prod_name",
        "product_group_name",
        "product_type_name",
        "colour_group_name",
        "garment_group_name",
        "detail_desc",
        "image_path",
        "text_profile",
    ]
    rows = [
        {
            "article_id": "0000000001",
            "prod_name": "White Office Shirt",
            "product_group_name": "Garment Upper body",
            "product_type_name": "Shirt",
            "colour_group_name": "White",
            "garment_group_name": "Shirts Blouses",
            "detail_desc": "适合夏天通勤的白色衬衫",
            "image_path": "images/000/0000000001.jpg",
            "text_profile": "白色衬衫 夏天 通勤 White office shirt",
        },
        {
            "article_id": "0000000002",
            "prod_name": "Black Hoodie",
            "product_group_name": "Garment Upper body",
            "product_type_name": "Sweater",
            "colour_group_name": "Black",
            "garment_group_name": "Jersey Fancy",
            "detail_desc": "黑色宽松卫衣，适合上课",
            "image_path": "images/000/0000000002.jpg",
            "text_profile": "黑色 宽松 卫衣 上课 Black loose hoodie",
        },
        {
            "article_id": "0000000003",
            "prod_name": "Blue Jeans",
            "product_group_name": "Garment Lower body",
            "product_type_name": "Trousers",
            "colour_group_name": "Blue",
            "garment_group_name": "Trousers",
            "detail_desc": "蓝色直筒牛仔裤",
            "image_path": "images/000/0000000003.jpg",
            "text_profile": "蓝色 直筒 牛仔裤 Blue straight jeans",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_build_and_search_api(tmp_path: Path, monkeypatch) -> None:
    fixture_csv = tmp_path / "articles_sample.csv"
    index_dir = tmp_path / "text_index"
    create_fixture_csv(fixture_csv)
    command = [
        sys.executable,
        str(BACKEND_DIR / "scripts" / "build_text_index.py"),
        "--input_csv",
        str(fixture_csv),
        "--index_dir",
        str(index_dir),
        "--backend",
        "hashing",
    ]
    completed = subprocess.run(command, cwd=PROJECT_DIR, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    metadata = json.loads((index_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["count"] == 3
    assert metadata["version"] == 2
    assert metadata["lexical_index"] == {"file": "bm25.json", "version": 1}
    assert (index_dir / "bm25.json").is_file()

    monkeypatch.setenv("TEXT_INDEX_DIR", str(index_dir))
    get_text_retriever.cache_clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/search/text",
            json={
                "query": "夏天通勤白色衬衫",
                "top_k": 2,
                "filters": {"color": "white", "category": "shirt"},
            },
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_candidates"] == 1
    assert payload["pipeline"] == ["dense", "bm25", "rrf", "rerank"]
    assert payload["results"][0]["article_id"] == "0000000001"
    assert payload["results"][0]["retrieval"]["sources"] == ["bm25", "dense"]
    assert payload["results"][0]["image_path"].endswith("0000000001.jpg")
    get_text_retriever.cache_clear()
