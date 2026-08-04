# 天池原始服装数据适配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将天池淘宝穿衣搭配数据集的原始商品文本和图片目录安全转换为现有商品目录。

**Architecture:** 新脚本只解析天池特有的 `dim_items.txt`，递归关联图片文件，生成带类目和演示展示字段的商品记录。它直接复用 `import_tianchi_catalog.py` 中已验证的抽样、原子发布和输出校验逻辑。

**Tech Stack:** Python 3.12、Pillow、pytest。

## Global Constraints

- 不修改 `backend/app/` 中的 Python RAG 服务。
- 不提交天池压缩包、原始文本、图片、SQLite 数据库或生成目录。
- 演示价格必须确定性生成，并在文档中明确不是天池原始售价。
- 默认抽样 5,000 条，种子为 42，输出为 `backend/data/tianchi-catalog/`。

---

### Task 1: 原始数据解析与商品记录构建

**Files:**
- Create: `backend/scripts/import_tianchi_fashion_collection.py`
- Create: `backend/tests/test_tianchi_fashion_collection_import.py`

**Interfaces:**
- Consumes: `items_path: Path`、`images_dir: Path`。
- Produces: `parse_tianchi_item_line(line: str) -> tuple[str, str, str] | None`、`build_tianchi_products(items_path: Path, images_dir: Path) -> list[dict[str, str]]`。

- [ ] **Step 1: Write the failing test**

```python
def test_build_tianchi_products_matches_nested_images_and_generates_demo_fields(tmp_path: Path) -> None:
    images_dir = tmp_path / "images" / "nested"
    create_image(images_dir / "1000004.jpg")
    items_path = tmp_path / "dim_items.txt"
    items_path.write_text("1000004 155 12,34,56\n", encoding="utf-8")

    products = build_tianchi_products(items_path, tmp_path / "images")

    assert products[0]["article_id"] == "0001000004"
    assert products[0]["prod_name"] == "天池服装 类目155 商品1000004"
    assert products[0]["product_group_name"] == "天池类目155"
    assert products[0]["price"] == "103"
    assert products[0]["source_image"] == str(images_dir / "1000004.jpg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\727push\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_fashion_collection_import.py -q`

Expected: FAIL because `import_tianchi_fashion_collection` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def parse_tianchi_item_line(line: str) -> tuple[str, str, str] | None:
    parts = line.strip().split(" ", 2)
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return parts[0], parts[1], parts[2] if len(parts) == 3 else ""


def demo_price(item_id: str) -> str:
    return str(99 + int(item_id) % 400)
```

递归索引图片文件名；跳过不支持、损坏、缺失和重复 ID 图片。构建 `PRODUCT_FIELDS` 记录并保留源图片路径。

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\727push\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_fashion_collection_import.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/scripts/import_tianchi_fashion_collection.py backend/tests/test_tianchi_fashion_collection_import.py
git commit -m "feat: 支持天池原始服装数据导入"
```

### Task 2: CLI 发布与异常边界

**Files:**
- Modify: `backend/scripts/import_tianchi_fashion_collection.py`
- Modify: `backend/tests/test_tianchi_fashion_collection_import.py`

**Interfaces:**
- Consumes: `main(argv: list[str] | None = None) -> int`。
- Produces: 成功时打印 `SUCCESS: Tianchi fashion catalog products=<n> images=<n>` 的 CLI。

- [ ] **Step 1: Write the failing tests**

```python
def test_cli_writes_valid_catalog(tmp_path: Path) -> None:
    create_image(tmp_path / "images" / "1000004.jpg")
    create_image(tmp_path / "images" / "1000012.jpg")
    (tmp_path / "dim_items.txt").write_text(
        "1000004 155 12,34\n1000012 228 56,78\n", encoding="utf-8"
    )

    result = main([
        "--items", str(tmp_path / "dim_items.txt"),
        "--images-dir", str(tmp_path / "images"),
        "--sample-size", "2", "--out-dir", str(tmp_path / "out"),
    ])

    assert result == 0
    assert validate_output(tmp_path / "out", expected_count=2) == {"products": 2, "images": 2}


def test_cli_keeps_existing_output_when_valid_products_are_insufficient(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "articles_sample.csv").write_text("legacy", encoding="utf-8")
    (tmp_path / "dim_items.txt").write_text("1000004 155 12\n", encoding="utf-8")

    assert main(["--items", str(tmp_path / "dim_items.txt"), "--images-dir", str(tmp_path), "--sample-size", "2", "--out-dir", str(output)]) == 1
    assert (output / "articles_sample.csv").read_text(encoding="utf-8") == "legacy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `D:\727push\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_fashion_collection_import.py -q`

Expected: FAIL because the CLI and error handling are absent.

- [ ] **Step 3: Write minimal implementation**

```python
parser.add_argument("--items", type=Path, required=True)
parser.add_argument("--images-dir", type=Path, required=True)
parser.add_argument("--sample-size", type=int, default=5000)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--out-dir", type=Path, default=BACKEND_DIR / "data" / "tianchi-catalog")
```

Call `sample_products` before `write_catalog`, print `ERROR:` to stderr for expected failures, and never invoke `write_catalog` when there are too few valid products.

- [ ] **Step 4: Run tests to verify they pass**

Run: `D:\727push\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_fashion_collection_import.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/scripts/import_tianchi_fashion_collection.py backend/tests/test_tianchi_fashion_collection_import.py
git commit -m "test: 覆盖天池原始数据导入边界"
```

### Task 3: 中文操作说明与全量验证

**Files:**
- Modify: `docs/tianchi-catalog-import.md`

**Interfaces:**
- Consumes: `backend/data/raw/tianchi/dim_items.txt` 和 `backend/data/raw/tianchi/images/`。
- Produces: 解压、导入、构建 SQLite 和 VMware 发布的中文步骤。

- [ ] **Step 1: Add the raw dataset instructions**

````markdown
## 导入天池原始服装数据

Windows PowerShell 的 `Expand-Archive` 可能无法处理该大型天池压缩包；使用 `tar -xf` 解压。

```powershell
tar -xf backend\data\raw\tianchi\archive\tianchi_fm_img3_1.zip -C backend\data\raw\tianchi\images
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_fashion_collection.py --items backend\data\raw\tianchi\dim_items.txt --images-dir backend\data\raw\tianchi\images --sample-size 5000 --seed 42
```

天池未提供原始售价；目录中的价格为系统生成的演示价格，仅用于购物车和订单流程。
````

- [ ] **Step 2: Run focused and regression tests**

Run: `D:\727push\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_fashion_collection_import.py backend\tests\test_tianchi_catalog_import.py -q`

Expected: PASS.

- [ ] **Step 3: Validate code formatting and review the changes**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only the script, tests and Chinese documentation are modified.

- [ ] **Step 4: Commit**

```powershell
git add docs/tianchi-catalog-import.md
git commit -m "docs: 补充天池原始数据导入步骤"
```
