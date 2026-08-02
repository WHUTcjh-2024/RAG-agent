from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.search import get_image_retriever
from app.main import app


def save_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), color=color).save(path, format="JPEG")


def create_image_fixture(root: Path) -> tuple[Path, Path]:
    images = root / "images" / "000"
    paths = {
        "0000000001": images / "0000000001.jpg",
        "0000000002": images / "0000000002.jpg",
        "0000000003": images / "0000000003.jpg",
    }
    save_image(paths["0000000001"], (240, 30, 30))
    save_image(paths["0000000002"], (30, 30, 240))
    save_image(paths["0000000003"], (30, 220, 30))
    rows = [
        {
            "article_id": article_id,
            "prod_name": name,
            "product_type_name": category,
            "colour_group_name": colour,
            "image_path": f"images/000/{article_id}.jpg",
            "price": "19.90",
        }
        for article_id, name, category, colour in (
            ("0000000001", "Red Shirt", "Shirt", "Red"),
            ("0000000002", "Blue Trousers", "Trousers", "Blue"),
            ("0000000003", "Green Shirt", "Shirt", "Green"),
        )
    ]
    csv_path = root / "articles_sample.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return csv_path, paths["0000000001"]


def test_build_and_search_image_api(tmp_path: Path, monkeypatch) -> None:
    csv_path, query_image = create_image_fixture(tmp_path)
    index_dir = tmp_path / "image_index"
    command = [
        sys.executable,
        str(BACKEND_DIR / "scripts" / "build_image_index.py"),
        "--input_csv",
        str(csv_path),
        "--index_dir",
        str(index_dir),
        "--backend",
        "pixel",
    ]
    completed = subprocess.run(command, cwd=PROJECT_DIR, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    metadata = json.loads((index_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["count"] == 3

    monkeypatch.setenv("IMAGE_INDEX_DIR", str(index_dir))
    get_image_retriever.cache_clear()
    with TestClient(app) as client:
        with query_image.open("rb") as handle:
            response = client.post(
                "/api/search/image",
                data={"top_k": "2", "filters": '{"category":"shirt"}'},
                files={"file": ("query.jpg", handle, "image/jpeg")},
            )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_candidates"] == 2
    assert payload["results"][0]["article_id"] == "0000000001"
    assert payload["results"][0]["score"] > payload["results"][1]["score"]
    get_image_retriever.cache_clear()


def test_image_api_rejects_invalid_file(tmp_path: Path, monkeypatch) -> None:
    csv_path, _ = create_image_fixture(tmp_path)
    index_dir = tmp_path / "image_index"
    subprocess.run(
        [
            sys.executable,
            str(BACKEND_DIR / "scripts" / "build_image_index.py"),
            "--input_csv",
            str(csv_path),
            "--index_dir",
            str(index_dir),
            "--backend",
            "pixel",
        ],
        cwd=PROJECT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setenv("IMAGE_INDEX_DIR", str(index_dir))
    get_image_retriever.cache_clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/search/image",
            data={"top_k": "2", "filters": "{}"},
            files={"file": ("bad.txt", io.BytesIO(b"not-an-image"), "text/plain")},
        )
    assert response.status_code == 400
    get_image_retriever.cache_clear()
