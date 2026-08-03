from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest
from PIL import Image

from scripts.data_utils import PRODUCT_FIELDS
from scripts.import_tianchi_catalog import (
    load_metadata_rows,
    normalize_products,
    sample_products,
    validate_output,
    write_catalog,
)


def create_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2, 2), color="red").save(path)


def test_load_metadata_rows_reads_csv_and_jsonl(tmp_path: Path) -> None:
    csv_path = tmp_path / "catalog.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name"])
        writer.writeheader()
        writer.writerow({"id": "1", "name": "棉质衬衫"})

    jsonl_path = tmp_path / "catalog.jsonl"
    jsonl_path.write_text(
        '{"id": 2, "name": null}\n\n{"id": "3", "name": "外套"}\n',
        encoding="utf-8",
    )

    assert load_metadata_rows(csv_path) == [{"id": "1", "name": "棉质衬衫"}]
    assert load_metadata_rows(jsonl_path) == [
        {"id": "2", "name": ""},
        {"id": "3", "name": "外套"},
    ]


def test_load_metadata_rows_reads_json_object_array(tmp_path: Path) -> None:
    json_path = tmp_path / "catalog.json"
    json_path.write_text(
        json.dumps([{"id": 4, "name": "连衣裙"}, {"id": "5", "name": None}]),
        encoding="utf-8",
    )

    assert load_metadata_rows(json_path) == [
        {"id": "4", "name": "连衣裙"},
        {"id": "5", "name": ""},
    ]


def test_load_metadata_rows_rejects_headerless_csv_with_required_columns(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "headerless.csv"
    csv_path.write_text("1,棉质衬衫\n2,羊毛外套\n", encoding="utf-8")

    with pytest.raises(ValueError, match="CSV metadata is missing required columns: id, name"):
        load_metadata_rows(csv_path, required_columns={"id", "name"})


def test_load_metadata_rows_rejects_invalid_formats(tmp_path: Path) -> None:
    unsupported = tmp_path / "catalog.txt"
    unsupported.write_text("id,name\n1,shirt\n", encoding="utf-8")
    object_json = tmp_path / "catalog.json"
    object_json.write_text('{"id": "1"}', encoding="utf-8")
    invalid_jsonl = tmp_path / "catalog.ndjson"
    invalid_jsonl.write_text('["not an object"]\n', encoding="utf-8")

    with pytest.raises(
        ValueError, match="Metadata must be .csv, .jsonl, .ndjson, or .json"
    ):
        load_metadata_rows(unsupported)
    with pytest.raises(ValueError, match="JSON metadata must be an array of objects"):
        load_metadata_rows(object_json)
    with pytest.raises(ValueError, match="JSONL metadata rows must be objects"):
        load_metadata_rows(invalid_jsonl)


def test_normalize_products_keeps_only_valid_records(tmp_path: Path) -> None:
    images_dir = tmp_path / "images"
    create_image(images_dir / "shirt.JPG")
    (images_dir / "empty.png").write_bytes(b"")
    create_image(tmp_path / "outside.jpg")

    rows = [
        {
            "source_id": "7",
            "source_name": "中文上衣",
            "source_image": "shirt.JPG",
            "source_price": "129.50",
        },
        {
            "source_id": "8",
            "source_name": "",
            "source_image": "shirt.JPG",
        },
        {
            "source_id": "9",
            "source_name": "空图片",
            "source_image": "empty.png",
        },
        {
            "source_id": "7",
            "source_name": "重复 ID",
            "source_image": "shirt.JPG",
        },
        {
            "source_id": "11",
            "source_name": "重复源图片",
            "source_image": "shirt.JPG",
        },
        {
            "source_id": "10",
            "source_name": "越界图片",
            "source_image": "../outside.jpg",
        },
    ]
    mapping = {
        "id": "source_id",
        "name": "source_name",
        "image": "source_image",
        "price": "source_price",
    }

    products = normalize_products(rows, images_dir, mapping)

    assert products == [
        {
            "article_id": "0000000007",
            "product_code": "0000000007",
            "prod_name": "中文上衣",
            "product_type_name": "未分类",
            "product_group_name": "服装",
            "graphical_appearance_name": "未分类",
            "colour_group_name": "未知",
            "perceived_colour_value_name": "未知",
            "perceived_colour_master_name": "未知",
            "department_name": "未分类",
            "index_name": "服装",
            "index_group_name": "服装",
            "section_name": "未分类",
            "garment_group_name": "服装",
            "detail_desc": "中文上衣",
            "image_path": "images/0000000007.JPG",
            "price": "129.50",
            "popularity_score": "0",
            "source_image": str((images_dir / "shirt.JPG").resolve()),
        }
    ]
    assert set(products[0]).issuperset(PRODUCT_FIELDS)
    assert "0000000011" not in {product["article_id"] for product in products}


def test_sample_products_is_deterministic_and_independent_of_input_order() -> None:
    products = [
        {"article_id": f"000000000{index}", "product_group_name": group}
        for group, index in (
            ("tops", 1),
            ("tops", 2),
            ("tops", 3),
            ("bottoms", 4),
            ("bottoms", 5),
            ("bottoms", 6),
        )
    ]

    selected = sample_products(products, sample_size=4, seed=19)

    assert selected == sample_products(list(reversed(products)), sample_size=4, seed=19)
    assert [product["article_id"] for product in selected] == sorted(
        product["article_id"] for product in selected
    )
    assert sum(product["product_group_name"] == "tops" for product in selected) == 2
    assert sum(product["product_group_name"] == "bottoms" for product in selected) == 2


def test_sample_products_seed_zero_is_independent_of_group_insertion_order() -> None:
    products = [
        {"article_id": f"000000000{index}", "product_group_name": group}
        for group, index in (
            ("tops", 1),
            ("tops", 2),
            ("tops", 3),
            ("bottoms", 4),
            ("bottoms", 5),
            ("bottoms", 6),
        )
    ]

    selected_ids = [
        product["article_id"]
        for product in sample_products(products, sample_size=4, seed=0)
    ]

    assert selected_ids == [
        product["article_id"]
        for product in sample_products(list(reversed(products)), sample_size=4, seed=0)
    ]


@pytest.mark.parametrize(
    ("sample_size", "message"),
    [
        (0, "sample_size must be greater than zero"),
        (3, "Only 2 valid products; need 3"),
    ],
)
def test_sample_products_rejects_invalid_requested_size(
    sample_size: int, message: str
) -> None:
    products = [
        {"article_id": "0000000001", "product_group_name": "tops"},
        {"article_id": "0000000002", "product_group_name": "tops"},
    ]

    with pytest.raises(ValueError, match=message):
        sample_products(products, sample_size=sample_size, seed=19)


def test_sample_failure_does_not_modify_existing_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    legacy_csv = output_dir / "articles_sample.csv"
    legacy_csv.write_text("legacy csv", encoding="utf-8")
    legacy_image = output_dir / "images" / "legacy.png"
    legacy_image.parent.mkdir()
    legacy_image.write_bytes(b"legacy image")
    products = [{"article_id": "0000000001", "product_group_name": "tops"}]

    with pytest.raises(ValueError, match="Only 1 valid products; need 2"):
        sample_products(products, sample_size=2, seed=19)

    assert legacy_csv.read_text(encoding="utf-8") == "legacy csv"
    assert legacy_image.read_bytes() == b"legacy image"


def test_write_catalog_creates_valid_catalog_and_manifest(tmp_path: Path) -> None:
    first_source = tmp_path / "source" / "shirt.png"
    second_source = tmp_path / "source" / "trousers.jpg"
    create_image(first_source)
    create_image(second_source)
    selected = [
        {
            **{field: "" for field in PRODUCT_FIELDS},
            "article_id": "0000000001",
            "product_code": "0000000001",
            "prod_name": "shirt",
            "product_group_name": "tops",
            "image_path": "images/0000000001.png",
            "source_image": str(first_source),
        },
        {
            **{field: "" for field in PRODUCT_FIELDS},
            "article_id": "0000000002",
            "product_code": "0000000002",
            "prod_name": "trousers",
            "product_group_name": "bottoms",
            "image_path": "images/0000000002.jpg",
            "source_image": str(second_source),
        },
    ]
    output_dir = tmp_path / "output"

    assert write_catalog(selected, output_dir, source_name="tianchi", seed=19) == {
        "products": 2,
        "images": 2,
    }
    assert validate_output(output_dir, expected_count=2) == {
        "products": 2,
        "images": 2,
    }
    with (output_dir / "articles_sample.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        assert csv.DictReader(handle).fieldnames == list(PRODUCT_FIELDS)
    manifest = json.loads((output_dir / "catalog_manifest.json").read_text("utf-8"))
    assert manifest["source"] == "tianchi"
    assert manifest["seed"] == 19
    assert manifest["product_count"] == 2
    assert manifest["image_count"] == 2
    assert len(manifest["articles_sha256"]) == 64
    assert set(manifest["articles_sha256"]) <= set("0123456789abcdef")


def test_validate_output_rejects_csv_with_missing_image(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    row = {field: "" for field in PRODUCT_FIELDS}
    row.update({"article_id": "0000000001", "image_path": "images/missing.png"})
    with (output_dir / "articles_sample.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=PRODUCT_FIELDS)
        writer.writeheader()
        writer.writerow(row)

    with pytest.raises(RuntimeError):
        validate_output(output_dir, expected_count=1)


def test_load_metadata_rows_accepts_final_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "catalog.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item_id", "title", "image"])
        writer.writeheader()
        writer.writerow({"item_id": "1", "title": "shirt", "image": "shirt.png"})

    assert load_metadata_rows(
        csv_path, required_columns={"item_id", "title", "image"}
    ) == [{"item_id": "1", "title": "shirt", "image": "shirt.png"}]


def test_write_catalog_restores_existing_output_when_promotion_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_image = tmp_path / "source" / "shirt.png"
    create_image(source_image)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    legacy_csv = output_dir / "articles_sample.csv"
    legacy_csv.write_text("legacy csv", encoding="utf-8")
    legacy_image = output_dir / "images" / "legacy.png"
    legacy_image.parent.mkdir()
    legacy_image.write_bytes(b"legacy image")
    legacy_manifest = output_dir / "catalog_manifest.json"
    legacy_manifest.write_text("legacy manifest", encoding="utf-8")
    selected = [
        {
            **{field: "" for field in PRODUCT_FIELDS},
            "article_id": "0000000001",
            "image_path": "images/0000000001.png",
            "source_image": str(source_image),
        }
    ]
    original_rename = Path.rename

    def fail_manifest_promotion(path: Path, target: Path) -> Path:
        if target == output_dir / "catalog_manifest.json" and path.parent != output_dir:
            raise OSError("simulated promotion failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_manifest_promotion)

    with pytest.raises(OSError, match="simulated promotion failure"):
        write_catalog(selected, output_dir, source_name="tianchi", seed=19)

    assert legacy_csv.read_text(encoding="utf-8") == "legacy csv"
    assert legacy_image.read_bytes() == b"legacy image"
    assert legacy_manifest.read_text(encoding="utf-8") == "legacy manifest"


def test_cli_imports_chinese_catalog_and_reports_invalid_columns(tmp_path: Path) -> None:
    metadata_path = tmp_path / "catalog.csv"
    images_dir = tmp_path / "images"
    output_dir = tmp_path / "output"
    create_image(images_dir / "dress.png")
    create_image(images_dir / "coat.jpg")
    with metadata_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item_id", "title", "image"])
        writer.writeheader()
        writer.writerows(
            [
                {"item_id": "101", "title": "中文连衣裙", "image": "dress.png"},
                {"item_id": "102", "title": "中文大衣", "image": "coat.jpg"},
            ]
        )

    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "import_tianchi_catalog.py"),
        "--metadata",
        str(metadata_path),
        "--images-dir",
        str(images_dir),
        "--id-column",
        "item_id",
        "--name-column",
        "title",
        "--image-column",
        "image",
        "--sample-size",
        "2",
        "--out-dir",
        str(output_dir),
    ]

    completed = subprocess.run(command, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "SUCCESS: Tianchi catalog products=2 images=2" in completed.stdout
    manifest = json.loads((output_dir / "catalog_manifest.json").read_text("utf-8"))
    assert manifest["product_count"] == 2

    invalid_column = subprocess.run(
        [*command[:7], "missing", *command[8:]], capture_output=True, text=True
    )

    assert invalid_column.returncode == 1
    assert "ERROR:" in invalid_column.stderr
