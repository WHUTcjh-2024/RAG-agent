from __future__ import annotations

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.data_utils import PRODUCT_FIELDS, normalize_article_id
from scripts.import_tianchi_catalog import _is_valid_image


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def parse_tianchi_item_line(line: str) -> dict[str, str] | None:
    parts = line.strip().split()
    if len(parts) < 3:
        return None
    item_id, category_id, *title_token_ids = parts
    if not item_id.isdigit() or not category_id.isdigit():
        return None
    return {
        "item_id": item_id,
        "category_id": category_id,
        "title_token_ids": " ".join(title_token_ids),
    }


def _collect_valid_images(images_dir: Path) -> dict[str, Path | None]:
    image_paths: dict[str, list[Path]] = {}
    for path in images_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        item_id = path.stem.strip()
        if not item_id.isdigit() or not _is_valid_image(path):
            continue
        image_paths.setdefault(item_id, []).append(path.resolve())

    resolved: dict[str, Path | None] = {}
    for item_id, paths in image_paths.items():
        resolved[item_id] = paths[0] if len(paths) == 1 else None
    return resolved


def build_tianchi_products(items_path: Path, images_dir: Path) -> list[dict[str, str]]:
    image_lookup = _collect_valid_images(images_dir)
    products: list[dict[str, str]] = []

    for raw_line in items_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_tianchi_item_line(raw_line)
        if parsed is None:
            continue

        source_image = image_lookup.get(parsed["item_id"])
        if source_image is None:
            continue

        article_id = normalize_article_id(parsed["item_id"])
        category_name = f"类目{parsed['category_id']}"
        products.append(
            {
                "article_id": article_id,
                "product_code": article_id,
                "prod_name": f"天池服装 {category_name} 商品{parsed['item_id']}",
                "product_type_name": category_name,
                "product_group_name": f"天池类目{parsed['category_id']}",
                "graphical_appearance_name": category_name,
                "colour_group_name": "未知",
                "perceived_colour_value_name": "未知",
                "perceived_colour_master_name": "未知",
                "department_name": category_name,
                "index_name": "天池服装",
                "index_group_name": "天池服装",
                "section_name": category_name,
                "garment_group_name": "天池服装",
                "detail_desc": f"原始标题为分词 ID 序列: {parsed['title_token_ids']}",
                "image_path": f"images/{article_id}{source_image.suffix.lower()}",
                "price": str(99 + int(parsed["item_id"]) % 400),
                "popularity_score": "0",
                "source_image": str(source_image),
            }
        )

    return [
        product
        for product in products
        if set(PRODUCT_FIELDS).issubset(product)
    ]
