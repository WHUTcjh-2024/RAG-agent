from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import sys
import tempfile
import uuid

from PIL import Image, UnidentifiedImageError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.data_utils import (
    PRODUCT_FIELDS,
    clean_text,
    normalize_article_id,
    resolve_image_path,
    write_csv,
    write_json,
)


SUPPORTED_METADATA_SUFFIXES = {".csv", ".jsonl", ".ndjson", ".json"}
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
REQUIRED_MAPPING_KEYS = {"id", "name", "image"}
SAFE_ARTICLE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


class CatalogArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


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


def _is_safe_article_id(article_id: str) -> bool:
    return bool(SAFE_ARTICLE_ID_PATTERN.fullmatch(article_id))


def _finite_number(value: str) -> str | None:
    if not value:
        return ""
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return format(parsed, "f")


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
        if (
            not article_id
            or not _is_safe_article_id(article_id)
            or not name
            or not image_value
        ):
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
        price = _finite_number(_mapped_value(row, mapping, "price"))
        popularity = _finite_number(_mapped_value(row, mapping, "popularity") or "0")
        if price is None or popularity is None:
            continue
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


def sample_products(
    products: list[dict[str, str]], sample_size: int, seed: int
) -> list[dict[str, str]]:
    """Return a deterministic, product-group-balanced sample."""
    if sample_size <= 0:
        raise ValueError("sample_size must be greater than zero")
    if len(products) < sample_size:
        raise ValueError(f"Only {len(products)} valid products; need {sample_size}")

    buckets: dict[str, list[dict[str, str]]] = {}
    for product in products:
        buckets.setdefault(product.get("product_group_name", ""), []).append(product)

    randomizer = random.Random(seed)
    groups = sorted(buckets)
    for group in groups:
        buckets[group] = sorted(buckets[group], key=lambda product: product["article_id"])
        randomizer.shuffle(buckets[group])

    selected: list[dict[str, str]] = []
    while len(selected) < sample_size:
        for group in groups:
            if buckets[group]:
                selected.append(buckets[group].pop())
                if len(selected) == sample_size:
                    break

    return sorted(selected, key=lambda product: product["article_id"])


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _transaction_path(output_dir: Path) -> Path:
    return output_dir / ".tianchi_catalog_transaction.json"


def _write_catalog_transaction(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _read_catalog_transaction(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unable to read catalog transaction: {path}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid catalog transaction: {path}")
    return payload


def _transaction_entries(payload: dict[str, object]) -> list[dict[str, object]]:
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != 3:
        raise RuntimeError("Invalid catalog transaction entries")
    expected_names = {"images", "articles_sample.csv", "catalog_manifest.json"}
    names: set[str] = set()
    validated: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Invalid catalog transaction entry")
        name = entry.get("name")
        backup = entry.get("backup")
        existed = entry.get("existed")
        if (
            not isinstance(name, str)
            or not isinstance(backup, str)
            or not isinstance(existed, bool)
            or name not in expected_names
            or Path(name).name != name
            or Path(backup).name != backup
            or not backup.startswith(".tianchi_catalog_backup_")
        ):
            raise RuntimeError("Invalid catalog transaction entry")
        names.add(name)
        validated.append({"name": name, "backup": backup, "existed": existed})
    if names != expected_names:
        raise RuntimeError("Invalid catalog transaction entries")
    return validated


def _recover_catalog_transaction(output_dir: Path) -> None:
    """Restore an interrupted publication or finish committed backup cleanup."""
    path = _transaction_path(output_dir)
    if not _path_exists(path):
        return
    payload = _read_catalog_transaction(path)
    state = payload.get("state")
    if state not in {"publishing", "committed"}:
        raise RuntimeError("Invalid catalog transaction state")
    entries = _transaction_entries(payload)

    if state == "committed":
        for entry in entries:
            backup = output_dir / str(entry["backup"])
            if _path_exists(backup):
                _remove_path(backup)
        path.unlink()
        return

    for entry in entries:
        target = output_dir / str(entry["name"])
        backup = output_dir / str(entry["backup"])
        if _path_exists(backup):
            if _path_exists(target):
                _remove_path(target)
            backup.rename(target)
        elif not entry["existed"] and _path_exists(target):
            _remove_path(target)
    path.unlink()


def _validate_or_raise(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_output(output_dir: Path, expected_count: int) -> dict[str, int]:
    """Validate the CSV/image output contract before or after publication."""
    csv_path = output_dir / "articles_sample.csv"
    images_dir = output_dir / "images"
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            _validate_or_raise(reader.fieldnames is not None, "CSV has no header")
            rows = list(reader)
    except (OSError, csv.Error) as error:
        raise RuntimeError(f"Unable to read catalog CSV: {csv_path}") from error

    _validate_or_raise(
        len(rows) == expected_count,
        f"Expected {expected_count} CSV rows; found {len(rows)}",
    )
    article_ids = [row.get("article_id", "") for row in rows]
    _validate_or_raise(
        len(article_ids) == len(set(article_ids)), "CSV contains duplicate article_id values"
    )

    for row in rows:
        image_path = row.get("image_path", "")
        _validate_or_raise(
            image_path.startswith("images/"),
            f"Image path must start with images/: {image_path}",
        )
        try:
            image_file = resolve_image_path(output_dir, image_path)
        except ValueError as error:
            raise RuntimeError(f"Invalid image path: {image_path}") from error
        _validate_or_raise(
            image_file.is_file() and image_file.stat().st_size > 0,
            f"Missing or empty image: {image_path}",
        )

    image_files = [path for path in images_dir.rglob("*") if path.is_file()]
    _validate_or_raise(
        len(image_files) == expected_count,
        f"Expected {expected_count} image files; found {len(image_files)}",
    )
    return {"products": expected_count, "images": expected_count}


def write_catalog(
    selected: list[dict[str, str]], output_dir: Path, source_name: str, seed: int
) -> dict[str, int]:
    """Write a verified catalog through a temporary directory and reversible swap."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    _recover_catalog_transaction(output_dir)
    temporary_dir = Path(
        tempfile.mkdtemp(prefix=".tianchi_catalog_", dir=output_dir.parent)
    )
    temporary_csv = temporary_dir / "articles_sample.csv"
    temporary_images = temporary_dir / "images"
    temporary_manifest = temporary_dir / "catalog_manifest.json"
    expected_count = len(selected)

    try:
        temporary_images.mkdir()
        rows: list[dict[str, str]] = []
        for product in selected:
            source_image = Path(product["source_image"])
            image_name = f"{product['article_id']}{source_image.suffix}"
            shutil.copy2(source_image, temporary_images / image_name)
            rows.append(
                {
                    **product,
                    "image_path": f"images/{image_name}",
                }
            )

        write_csv(temporary_csv, rows, list(PRODUCT_FIELDS))
        write_json(
            temporary_manifest,
            {
                "source": source_name,
                "seed": seed,
                "product_count": expected_count,
                "image_count": expected_count,
                "articles_sha256": hashlib.sha256(
                    temporary_csv.read_bytes()
                ).hexdigest(),
            },
        )
        validate_output(temporary_dir, expected_count)

        backup_token = uuid.uuid4().hex
        targets = (
            (output_dir / "images", temporary_images),
            (output_dir / "articles_sample.csv", temporary_csv),
            (output_dir / "catalog_manifest.json", temporary_manifest),
        )
        transaction_path = _transaction_path(output_dir)
        transaction = {
            "state": "publishing",
            "entries": [
                {
                    "name": target.name,
                    "backup": f".tianchi_catalog_backup_{backup_token}_{target.name}",
                    "existed": _path_exists(target),
                }
                for target, _ in targets
            ],
        }
        try:
            _write_catalog_transaction(transaction_path, transaction)
            entries = _transaction_entries(transaction)
            for (target, _), entry in zip(targets, entries, strict=True):
                if entry["existed"]:
                    target.rename(output_dir / str(entry["backup"]))
            for target, temporary in targets:
                temporary.rename(target)
            validate_output(output_dir, expected_count)
            transaction["state"] = "committed"
            _write_catalog_transaction(transaction_path, transaction)
            _recover_catalog_transaction(output_dir)
        except Exception:
            _recover_catalog_transaction(output_dir)
            raise

        return {"products": expected_count, "images": expected_count}
    finally:
        _remove_path(temporary_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = CatalogArgumentParser(description="Import a Tianchi product catalog.")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--id-column", required=True)
    parser.add_argument("--name-column", required=True)
    parser.add_argument("--image-column", required=True)
    parser.add_argument("--category-column")
    parser.add_argument("--color-column")
    parser.add_argument("--description-column")
    parser.add_argument("--price-column")
    parser.add_argument("--popularity-column")
    parser.add_argument("--sample-size", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out-dir", type=Path, default=BACKEND_DIR / "data" / "tianchi-catalog"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        mapping = {
            "id": args.id_column,
            "name": args.name_column,
            "image": args.image_column,
        }
        for mapping_key, column_name in (
            ("category", args.category_column),
            ("color", args.color_column),
            ("description", args.description_column),
            ("price", args.price_column),
            ("popularity", args.popularity_column),
        ):
            if column_name:
                mapping[mapping_key] = column_name

        rows = load_metadata_rows(
            args.metadata, required_columns=set(mapping.values())
        )
        products = normalize_products(rows, args.images_dir, mapping)
        selected = sample_products(products, args.sample_size, args.seed)
        result = write_catalog(
            selected,
            args.out_dir,
            source_name="tianchi-fashion-collection",
            seed=args.seed,
        )
    except SystemExit as error:
        return 0 if error.code == 0 else 1
    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        OSError,
        csv.Error,
        json.JSONDecodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "SUCCESS: Tianchi catalog "
        f"products={result['products']} images={result['images']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
