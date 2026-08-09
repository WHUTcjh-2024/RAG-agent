from __future__ import annotations

import csv
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_DIR = BACKEND_DIR / "data" / "tianchi-catalog"
DEMO_CATALOG_DIR = BACKEND_DIR / "data" / "tianchi-demo"

PRODUCT_FIELDS = (
    "article_id",
    "product_code",
    "prod_name",
    "product_type_name",
    "product_group_name",
    "graphical_appearance_name",
    "colour_group_name",
    "perceived_colour_value_name",
    "perceived_colour_master_name",
    "department_name",
    "index_name",
    "index_group_name",
    "section_name",
    "garment_group_name",
    "detail_desc",
    "image_path",
    "price",
    "popularity_score",
)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_article_id(value: str | None) -> str:
    article_id = clean_text(value)
    return article_id.zfill(10) if article_id.isdigit() else article_id


def resolve_image_path(image_root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    path = (image_root / Path(*parts)).resolve()
    root = image_root.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Image path escapes image root: {relative}")
    return path


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise RuntimeError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def resolve_catalog_csv(path: Path) -> Path:
    """Use the local Tianchi catalog, with a tracked CI-safe demo fallback."""
    resolved = path.expanduser().resolve()
    default = (DEFAULT_CATALOG_DIR / "articles_sample.csv").resolve()
    if resolved == default and not resolved.is_file():
        demo = (DEMO_CATALOG_DIR / "articles_sample.csv").resolve()
        if demo.is_file():
            return demo
    return resolved
