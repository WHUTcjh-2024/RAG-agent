from __future__ import annotations

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_DIR = BACKEND_DIR / "data" / "tianchi-catalog"
DEFAULT_CATALOG_IMAGE_DIR = DEFAULT_CATALOG_DIR / "images"
DEFAULT_TEXT_INDEX_DIR = BACKEND_DIR / "data" / "vector_store" / "text"
DEFAULT_IMAGE_INDEX_DIR = BACKEND_DIR / "data" / "vector_store" / "image"


def configured_path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value).expanduser().resolve() if value else default.resolve()


def get_catalog_dir() -> Path:
    return configured_path("CATALOG_DIR", DEFAULT_CATALOG_DIR)


def get_catalog_image_dir() -> Path:
    return configured_path("CATALOG_IMAGE_DIR", get_catalog_dir() / "images")


def get_text_index_dir() -> Path:
    return configured_path("TEXT_INDEX_DIR", DEFAULT_TEXT_INDEX_DIR)


def get_image_index_dir() -> Path:
    return configured_path("IMAGE_INDEX_DIR", DEFAULT_IMAGE_INDEX_DIR)
