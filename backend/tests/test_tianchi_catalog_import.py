from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.data_utils import PRODUCT_FIELDS
from scripts.import_tianchi_catalog import load_metadata_rows, normalize_products


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
