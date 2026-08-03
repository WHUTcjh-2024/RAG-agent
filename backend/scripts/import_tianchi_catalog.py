from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from scripts.data_utils import clean_text, normalize_article_id


SUPPORTED_METADATA_SUFFIXES = {".csv", ".jsonl", ".ndjson", ".json"}
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
REQUIRED_MAPPING_KEYS = {"id", "name", "image"}


def _stringify_row(row: dict[object, object]) -> dict[str, str]:
    return {str(key): "" if value is None else str(value) for key, value in row.items()}


def load_metadata_rows(
    path: Path, *, required_columns: set[str] | None = None
) -> list[dict[str, str]]:
    """Load supported metadata, optionally requiring CSV header columns."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_METADATA_SUFFIXES:
        raise ValueError("Metadata must be .csv, .jsonl, .ndjson, or .json")

    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV metadata must have a header")
            missing_columns = sorted(set(required_columns or ()) - set(reader.fieldnames))
            if missing_columns:
                raise ValueError(
                    "CSV metadata is missing required columns: "
                    + ", ".join(missing_columns)
                )
            return [_stringify_row(row) for row in reader]

    if suffix in {".jsonl", ".ndjson"}:
        rows: list[dict[str, str]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("JSONL metadata rows must be objects")
                rows.append(_stringify_row(value))
        return rows

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError("JSON metadata must be an array of objects")
    return [_stringify_row(row) for row in value]


def _mapped_value(row: dict[str, str], mapping: dict[str, str], name: str) -> str:
    source_key = mapping.get(name, "")
    return clean_text(row.get(source_key, "")) if source_key else ""


def _is_valid_image(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, UnidentifiedImageError):
        return False
    return True


def normalize_products(
    rows: list[dict[str, str]], images_dir: Path, mapping: dict[str, str]
) -> list[dict[str, str]]:
    """Validate source rows and shape them for the catalog import pipeline."""
    if not REQUIRED_MAPPING_KEYS.issubset(mapping):
        missing = ", ".join(sorted(REQUIRED_MAPPING_KEYS - mapping.keys()))
        raise ValueError(f"Mapping is missing required keys: {missing}")

    root = images_dir.resolve()
    products: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_images: set[Path] = set()

    for row in rows:
        article_id = normalize_article_id(_mapped_value(row, mapping, "id"))
        name = _mapped_value(row, mapping, "name")
        image_value = _mapped_value(row, mapping, "image")
        if not article_id or not name or not image_value:
            continue

        source_image = (root / image_value).resolve()
        if not source_image.is_relative_to(root):
            continue
        if source_image.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        if not _is_valid_image(source_image):
            continue
        if article_id in seen_ids or source_image in seen_images:
            continue

        category = _mapped_value(row, mapping, "category") or "未分类"
        color = _mapped_value(row, mapping, "color") or "未知"
        description = _mapped_value(row, mapping, "description") or name
        price = _mapped_value(row, mapping, "price")
        popularity = _mapped_value(row, mapping, "popularity") or "0"
        product = {
            "article_id": article_id,
            "product_code": article_id,
            "prod_name": name,
            "product_type_name": category,
            "product_group_name": "服装",
            "graphical_appearance_name": category,
            "colour_group_name": color,
            "perceived_colour_value_name": color,
            "perceived_colour_master_name": color,
            "department_name": category,
            "index_name": "服装",
            "index_group_name": "服装",
            "section_name": category,
            "garment_group_name": "服装",
            "detail_desc": description,
            "image_path": f"images/{article_id}{source_image.suffix}",
            "price": price,
            "popularity_score": popularity,
            "source_image": str(source_image),
        }
        products.append(product)
        seen_ids.add(article_id)
        seen_images.add(source_image)

    return products
