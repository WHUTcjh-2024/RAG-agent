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
from app.core.virtual_try_on import SyntheticBodyProfile, VirtualTryOnService, VirtualTryOnSettings
from app.main import app


def _jpeg(width: int = 900, height: int = 1200) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color=(168, 127, 147)).save(output, format="JPEG")
    return output.getvalue()


class _FakeProvider:
    configured = True

    def __init__(self) -> None:
        self.profile: SyntheticBodyProfile | None = None

    async def render(self, **values: object) -> bytes:
        self.profile = values["body_profile"]  # type: ignore[assignment]
        assert "person" not in values
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
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)",
            ("dress-1", "Cerise Dress", "连衣裙", "服装", "连衣裙", "images/garment.jpg"),
        )
    return database, image_dir


def _service(tmp_path: Path, provider: _FakeProvider) -> VirtualTryOnService:
    return VirtualTryOnService(
        VirtualTryOnSettings(
            database_path=tmp_path / "tryon" / "jobs.db",
            media_dir=tmp_path / "tryon" / "media",
            provider_url="https://provider.example.test/v1/generate",
            provider_api_key="",
            provider_timeout_seconds=5,
            result_signing_secret="result-test-secret",
            result_ttl_hours=24,
            saved_result_ttl_hours=168,
            max_concurrent_jobs=1,
            rate_limit_count=10,
            rate_limit_window_seconds=600,
        ),
        provider=provider,  # type: ignore[arg-type]
    )


def _payload() -> dict[str, object]:
    return {
        "product_id": "dress-1",
        "body_profile": {
            "height_cm": 168,
            "weight_kg": 58,
            "chest_cm": 88,
            "waist_cm": 70,
            "hip_cm": 94,
            "shoulder_cm": 40,
            "inseam_cm": 76,
            "presentation": "NEUTRAL",
            "body_shape": "BALANCED",
            "skin_tone": "MEDIUM",
            "fit_preference": "REGULAR",
        },
    }


def test_synthetic_try_on_is_authorized_idempotent_and_controllable(tmp_path: Path, monkeypatch) -> None:
    database, image_dir = _catalog(tmp_path)
    provider = _FakeProvider()
    service = _service(tmp_path, provider)
    monkeypatch.setenv("CATALOG_DB_PATH", str(database))
    monkeypatch.setenv("CATALOG_IMAGE_DIR", str(image_dir))
    monkeypatch.setenv("AGENT_CONTEXT_TOKEN", "trusted-test-token")
    monkeypatch.setattr(try_on, "get_try_on_service", lambda: service)
    headers = {
        "X-Trusted-User-Id": "user-1",
        "X-Agent-Context-Token": "trusted-test-token",
        "Idempotency-Key": "try-on-idempotency-0001",
    }

    with TestClient(app) as client:
        denied = client.post("/api/try-on/jobs", json=_payload())
        assert denied.status_code == 401

        created = client.post("/api/try-on/jobs", headers=headers, json=_payload())
        assert created.status_code == 202
        job_id = created.json()["id"]
        assert created.json()["category"] == "dress"
        assert created.json()["model"]["uses_person_photo"] is False
        assert "photo_quality" not in created.json()

        repeated = client.post("/api/try-on/jobs", headers=headers, json=_payload())
        assert repeated.status_code == 200
        assert repeated.json()["id"] == job_id

        result = created.json()
        for _ in range(30):
            time.sleep(0.02)
            result = client.get(f"/api/try-on/jobs/{job_id}", headers=headers).json()
            if result["status"] == "SUCCEEDED":
                break
        assert result["status"] == "SUCCEEDED"
        assert provider.profile is not None and provider.profile.height_cm == 168

        image = client.get(result["result"]["url"])
        assert image.status_code == 200
        assert image.headers["x-ai-generated"] == "synthetic-virtual-model"

        recent = client.get("/api/try-on/jobs", headers=headers).json()["items"]
        assert [item["id"] for item in recent] == [job_id]

        saved = client.post(f"/api/try-on/jobs/{job_id}/save", headers=headers, json={"saved": True})
        assert saved.status_code == 200
        assert saved.json()["saved"] is True

        feedback = client.post(
            f"/api/try-on/jobs/{job_id}/feedback",
            headers=headers,
            json={"rating": 5, "issues": []},
        )
        assert feedback.status_code == 200
        assert feedback.json()["feedback"] == {"rating": 5, "issues": []}

        share = client.post(f"/api/try-on/jobs/{job_id}/share", headers=headers)
        assert share.status_code == 200
        assert share.json()["url"].startswith(f"/api/try-on/jobs/{job_id}/result?")

        deleted = client.delete(f"/api/try-on/jobs/{job_id}", headers=headers)
        assert deleted.status_code == 204
        assert client.get(f"/api/try-on/jobs/{job_id}", headers=headers).status_code == 404


def test_body_profile_rejects_impossible_values(tmp_path: Path, monkeypatch) -> None:
    database, image_dir = _catalog(tmp_path)
    service = _service(tmp_path, _FakeProvider())
    monkeypatch.setenv("CATALOG_DB_PATH", str(database))
    monkeypatch.setenv("CATALOG_IMAGE_DIR", str(image_dir))
    monkeypatch.setenv("AGENT_CONTEXT_TOKEN", "trusted-test-token")
    monkeypatch.setattr(try_on, "get_try_on_service", lambda: service)
    payload = _payload()
    payload["body_profile"] = {**payload["body_profile"], "height_cm": 80}  # type: ignore[dict-item]
    headers = {"X-Trusted-User-Id": "user-1", "X-Agent-Context-Token": "trusted-test-token"}

    with TestClient(app) as client:
        response = client.post("/api/try-on/jobs", headers=headers, json=payload)
    assert response.status_code == 422
