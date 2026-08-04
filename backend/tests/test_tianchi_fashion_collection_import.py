from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest
from PIL import Image

import scripts.import_tianchi_fashion_collection as tianchi_fashion
from scripts.data_utils import PRODUCT_FIELDS
from scripts.import_tianchi_fashion_collection import (
    build_tianchi_products,
    parse_tianchi_item_line,
)


def create_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2, 2), color="blue").save(path)


def test_parse_tianchi_item_line_parses_expected_columns() -> None:
    assert parse_tianchi_item_line("200 7 11 22 33") == {
        "item_id": "200",
        "category_id": "7",
        "title_token_ids": "11 22 33",
    }


def test_parse_tianchi_item_line_rejects_missing_or_nonnumeric_ids() -> None:
    assert parse_tianchi_item_line("") is None
    assert parse_tianchi_item_line("200") is None
    assert parse_tianchi_item_line("shirt 7 11 22") is None
    assert parse_tianchi_item_line("200 coat 11 22") is None


def test_build_tianchi_products_filters_invalid_lines_and_images(tmp_path: Path) -> None:
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text(
        "\n".join(
            [
                "invalid",
                "shirt 7 11 22",
                "100 4 8 9",
                "200 7 11 22 33",
                "300 8 44 55",
                "400 9 66 77",
            ]
        ),
        encoding="utf-8",
    )
    images_dir = tmp_path / "images"
    create_image(images_dir / "nested" / "200.jpg")
    create_image(images_dir / "duplicates" / "100.jpg")
    create_image(images_dir / "more-duplicates" / "100.png")
    (images_dir / "broken" / "300.jpg").parent.mkdir(parents=True, exist_ok=True)
    (images_dir / "broken" / "300.jpg").write_bytes(b"not an image")

    products = build_tianchi_products(items_path, images_dir)

    assert len(products) == 1
    assert products[0] == {
        "article_id": "0000000200",
        "product_code": "0000000200",
        "prod_name": "天池服装 类目7 商品200",
        "product_type_name": "类目7",
        "product_group_name": "天池类目7",
        "graphical_appearance_name": "类目7",
        "colour_group_name": "未知",
        "perceived_colour_value_name": "未知",
        "perceived_colour_master_name": "未知",
        "department_name": "类目7",
        "index_name": "天池服装",
        "index_group_name": "天池服装",
        "section_name": "类目7",
        "garment_group_name": "天池服装",
        "detail_desc": "原始标题为分词 ID 序列: 11 22 33",
        "image_path": "images/0000000200.jpg",
        "price": "299",
        "popularity_score": "0",
        "source_image": str((images_dir / "nested" / "200.jpg").resolve()),
    }
    assert set(products[0]).issuperset(PRODUCT_FIELDS)


def test_build_tianchi_products_skips_duplicate_item_images(tmp_path: Path) -> None:
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text("100 4 8 9\n", encoding="utf-8")
    images_dir = tmp_path / "images"
    create_image(images_dir / "a" / "100.jpg")
    create_image(images_dir / "b" / "100.webp")

    assert build_tianchi_products(items_path, images_dir) == []


def test_build_tianchi_products_skips_item_when_duplicate_candidates_include_broken_image(
    tmp_path: Path,
) -> None:
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text("100 4 8 9\n", encoding="utf-8")
    images_dir = tmp_path / "images"
    create_image(images_dir / "valid" / "100.jpg")
    broken_path = images_dir / "broken" / "100.png"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_bytes(b"not an image")

    assert build_tianchi_products(items_path, images_dir) == []


def test_build_tianchi_products_skips_symlinked_images_resolving_outside_directory(
    tmp_path: Path,
) -> None:
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text("100 4 8 9\n", encoding="utf-8")
    images_dir = tmp_path / "images"
    external_image = tmp_path / "external" / "100.jpg"
    create_image(external_image)
    symlink_path = images_dir / "nested" / "100.jpg"
    symlink_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        symlink_path.symlink_to(external_image)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable on this Windows environment: {error}")

    assert build_tianchi_products(items_path, images_dir) == []


def test_build_tianchi_products_streams_items_file_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text("100 4 8 9\n", encoding="utf-8")
    images_dir = tmp_path / "images"
    create_image(images_dir / "100.jpg")

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError("build_tianchi_products should stream lines via Path.open()")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    products = build_tianchi_products(items_path, images_dir)

    assert len(products) == 1
    assert products[0]["article_id"] == "0000000100"


def test_cli_publishes_catalog_from_temp_items_and_images(tmp_path: Path) -> None:
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text("100 4 8 9\n200 7 11 22 33\n", encoding="utf-8")
    images_dir = tmp_path / "images"
    create_image(images_dir / "nested" / "100.jpg")
    create_image(images_dir / "nested" / "200.png")
    output_dir = tmp_path / "output"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_tianchi_fashion_collection.py"

    with tempfile.TemporaryDirectory() as external_cwd:
        completed = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--items",
                str(items_path),
                "--images-dir",
                str(images_dir),
                "--sample-size",
                "2",
                "--seed",
                "19",
                "--out-dir",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            cwd=external_cwd,
        )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "SUCCESS: Tianchi fashion catalog products=2 images=2" in completed.stdout
    with (output_dir / "articles_sample.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    manifest = json.loads((output_dir / "catalog_manifest.json").read_text("utf-8"))
    assert manifest["source"] == "tianchi-fashion-collection"
    assert manifest["seed"] == 19
    assert manifest["product_count"] == 2
    assert manifest["image_count"] == 2


def test_main_does_not_publish_or_modify_legacy_output_when_products_are_insufficient(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text("100 4 8 9\n", encoding="utf-8")
    images_dir = tmp_path / "images"
    create_image(images_dir / "100.jpg")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    legacy_csv = output_dir / "articles_sample.csv"
    legacy_csv.write_text("legacy csv", encoding="utf-8")
    legacy_image = output_dir / "images" / "legacy.png"
    legacy_image.parent.mkdir()
    legacy_image.write_bytes(b"legacy image")
    legacy_manifest = output_dir / "catalog_manifest.json"
    legacy_manifest.write_text("legacy manifest", encoding="utf-8")

    result = tianchi_fashion.main(
        [
            "--items",
            str(items_path),
            "--images-dir",
            str(images_dir),
            "--sample-size",
            "2",
            "--out-dir",
            str(output_dir),
        ]
    )

    assert result == 1
    assert "ERROR: Only 1 valid products; need 2" in capsys.readouterr().err
    assert legacy_csv.read_text(encoding="utf-8") == "legacy csv"
    assert legacy_image.read_bytes() == b"legacy image"
    assert legacy_manifest.read_text(encoding="utf-8") == "legacy manifest"
