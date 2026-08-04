from __future__ import annotations

from pathlib import Path

from PIL import Image

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
