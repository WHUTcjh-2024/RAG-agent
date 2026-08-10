from __future__ import annotations

# ruff: noqa: E402

import io
import sqlite3
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api import try_on
from app.core.virtual_try_on import VirtualTryOnService, VirtualTryOnSettings
from app.main import app


def _jpeg(width: int = 900, height: int = 1200) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color=(168, 127, 147)).save(output, format="JPEG")
    return output.getvalue()


class _FakeProvider:
    configured = True

    async def render(self, **_: object) -> bytes:
        return _jpeg()


def _catalog(tmp_path: Path) -> tuple[Path, Path]:
    image_dir = tmp_path / "catalog" / "images"
    image_dir.mkdir(parents=True)
    (image_dir / "garment.jpg").write_bytes(_jpeg())
    database = tmp_path / "catalog.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE products (
                article_id TEXT PRIMARY KEY,
                prod_name TEXT,
                product_type_name TEXT,
                product_group_name TEXT,
                garment_group_name TEXT,
                image_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("dress-1", "Cerise Dress", "Dress", "Garment Upper body", "Dresses", "images/garment.jpg"),
        )
    return database, image_dir


def _service(tmp_path: Path) -> VirtualTryOnService:
    return VirtualTryOnService(
        VirtualTryOnSettings(
            database_path=tmp_path / "tryon" / "jobs.db",
            media_dir=tmp_path / "tryon" / "media",
            provider_url="https://provider.example.test/v1/generate",
            provider_api_key="",
            provider_timeout_seconds=5,
            result_signing_secret="result-test-secret",
            result_ttl_hours=24,
            max_concurrent_jobs=1,
            rate_limit_count=10,
            rate_limit_window_seconds=600,
        ),
        provider=_FakeProvider(),  # type: ignore[arg-type]
    )


def test_try_on_job_is_authorized_idempotent_and_ephemeral(tmp_path: Path, monkeypatch) -> None:
    database, image_dir = _catalog(tmp_path)
    service = _service(tmp_path)
    monkeypatch.setenv("CATALOG_DB_PATH", str(database))
    monkeypatch.setenv("CATALOG_IMAGE_DIR", str(image_dir))
    monkeypatch.setenv("AGENT_CONTEXT_TOKEN", "trusted-test-token")
    monkeypatch.setattr(try_on, "get_try_on_service", lambda: service)
    headers = {
        "X-Trusted-User-Id": "user-1",
        "X-Agent-Context-Token": "trusted-test-token",
        "Idempotency-Key": "try-on-idempotency-0001",
    }
    files = {"person_image": ("person.jpg", _jpeg(), "image/jpeg")}
    data = {"product_id": "dress-1", "consent": "true"}

    with TestClient(app) as client:
        denied = client.post("/api/try-on/jobs", files=files, data=data)
        assert denied.status_code == 401

        created = client.post("/api/try-on/jobs", headers=headers, files=files, data=data)
        assert created.status_code == 202
        job_id = created.json()["id"]
        assert created.json()["category"] == "dress"

        repeated = client.post("/api/try-on/jobs", headers=headers, files=files, data=data)
        assert repeated.status_code == 200
        assert repeated.json()["id"] == job_id

        payload = created.json()
        for _ in range(30):
            time.sleep(0.02)
            payload = client.get(f"/api/try-on/jobs/{job_id}", headers=headers).json()
            if payload["status"] == "SUCCEEDED":
                break
        assert payload["status"] == "SUCCEEDED"
        assert payload["result"]["url"].startswith(f"/api/try-on/jobs/{job_id}/result?")
        image_response = client.get(payload["result"]["url"])
        assert image_response.status_code == 200
        assert image_response.headers["content-type"].startswith("image/jpeg")
        assert list(service.inputs_dir.iterdir()) == []
        assert len(list(service.outputs_dir.glob("*.jpg"))) == 1
