# 天池商品数据导入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将天池淘宝服装搭配数据集中的 5,000 件带图商品转换为现有商品目录格式，使现有 `/api/products`、`/media/**`、RAG 检索、Java 购物车和订单接口无需改动即可继续使用。

**Architecture:** 新增一个独立 Python 导入脚本，接受原始元数据文件、图片目录和列映射参数，生成现有 `articles_sample.csv` 与 `images/` 目录。脚本在临时目录中完成图片复制、规范化和校验，再原子替换这两个输出；SQLite 商品库和文本索引仍由现有脚本生成。Python RAG 应用代码、Java 代码和前端代码均不修改。

**Tech Stack:** Python 3.12 标准库、pytest、SQLite、现有 `build_sqlite.py` 与 `build_text_index.py`。

## Global Constraints

- 仅修改 `backend/scripts/`、`backend/tests/`、根目录文档与数据导入文档；不得修改 `backend/app/` 的 RAG 主流程。
- 原始天池数据、商品图片、SQLite 库和向量索引必须继续被 Git 忽略。
- 默认样本数必须为 `5000`，默认随机种子必须为 `42`。
- 只保留带有可读取 JPEG、PNG 或 WebP 主图的商品；导入失败不得破坏现有 `articles_sample.csv` 或 `images/`。
- 不导入、输出或提交用户购买行为明细。

---

### Task 1: 定义天池元数据导入契约并添加失败测试

**Files:**
- Create: `backend/tests/test_tianchi_catalog_import.py`
- Create: `backend/scripts/import_tianchi_catalog.py`

**Interfaces:**
- Consumes: CSV、JSONL 或 JSON 数组格式的商品元数据；本地图片根目录。
- Produces: `load_metadata_rows(path: Path) -> list[dict[str, str]]`、`normalize_products(rows: list[dict[str, str]], images_dir: Path, mapping: dict[str, str]) -> list[dict[str, str]]`、`validate_output(output_dir: Path, expected_count: int) -> dict[str, int]`。

- [ ] **Step 1: 写入最小 CSV/JSONL 与图片夹具测试**

在 `backend/tests/test_tianchi_catalog_import.py` 中创建三个元数据记录：两条完整记录、一条缺少标题记录；使用 Pillow 生成两张有效 PNG，并创建一个零字节图片。测试通过参数映射调用 `normalize_products`：

```python
mapping = {
    "id": "item_id",
    "name": "title",
    "category": "category",
    "color": "color",
    "description": "description",
    "price": "price",
    "popularity": "popularity",
    "image": "image",
}
products = normalize_products(rows, images_dir, mapping)
assert [product["article_id"] for product in products] == ["1001", "1002"]
assert products[0]["prod_name"] == "中文连衣裙"
assert products[0]["image_path"] == "images/1001.png"
```

- [ ] **Step 2: 运行测试，确认当前缺少模块而失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_catalog_import.py -q`

Expected: FAIL，提示无法导入 `import_tianchi_catalog`。

- [ ] **Step 3: 创建导入模块骨架与输入读取函数**

在 `backend/scripts/import_tianchi_catalog.py` 中实现：

```python
def load_metadata_rows(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError(f"Metadata CSV has no header: {path}")
            return [
                {key: "" if value is None else str(value) for key, value in row.items()}
                for row in reader
            ]
    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError(f"Metadata line {line_number} is not an object")
                rows.append({key: "" if value is None else str(value) for key, value in payload.items()})
        return rows
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ValueError("Metadata JSON must contain an array of objects")
        return [{key: "" if value is None else str(value) for key, value in row.items()} for row in payload]
    raise ValueError("Metadata must be .csv, .jsonl, .ndjson, or .json")
```

将 `backend/scripts` 加入测试导入路径，确保不读取实际数据目录。

- [ ] **Step 4: 实现规范化与图片候选筛选**

实现 `normalize_products(rows, images_dir, mapping)`：

```python
def normalize_products(
    rows: list[dict[str, str]],
    images_dir: Path,
    mapping: dict[str, str],
) -> list[dict[str, str]]:
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    root = images_dir.resolve()
    seen_ids, seen_sources, products = set(), set(), []
    for row in rows:
        article_id = (row.get(mapping["id"]) or "").strip()
        name = (row.get(mapping["name"]) or "").strip()
        raw_image = (row.get(mapping["image"]) or "").replace("\\", "/").lstrip("/")
        source = (root / Path(*PurePosixPath(raw_image).parts)).resolve()
        if not article_id or not name or not source.is_relative_to(root):
            continue
        if source.suffix.lower() not in allowed_suffixes or not source.is_file() or source.stat().st_size == 0:
            continue
        try:
            with Image.open(source) as image:
                image.verify()
        except (OSError, UnidentifiedImageError):
            continue
        if article_id in seen_ids or source in seen_sources:
            continue
        products.append({
            "article_id": article_id, "product_code": article_id, "prod_name": name,
            "product_type_name": (row.get(mapping.get("category", "")) or "未分类").strip() or "未分类",
            "product_group_name": (row.get(mapping.get("category", "")) or "服装").strip() or "服装",
            "graphical_appearance_name": "", "colour_group_name": (row.get(mapping.get("color", "")) or "未知").strip() or "未知",
            "perceived_colour_value_name": "", "perceived_colour_master_name": "", "department_name": "",
            "index_name": "", "index_group_name": "", "section_name": "", "garment_group_name": "",
            "detail_desc": (row.get(mapping.get("description", "")) or name).strip() or name,
            "image_path": f"images/{article_id}{source.suffix.lower()}",
            "price": (row.get(mapping.get("price", "")) or "").strip(),
            "popularity_score": (row.get(mapping.get("popularity", "")) or "0").strip() or "0",
            "source_image": str(source),
        })
        seen_ids.add(article_id)
        seen_sources.add(source)
    return products
```

使用 `Path.resolve()` 加 `is_relative_to(images_dir.resolve())` 拒绝 `../` 路径；只接受 `.jpg`、`.jpeg`、`.png`、`.webp`，并以 `PIL.Image.verify()` 验证非损坏图片。

- [ ] **Step 5: 运行 Task 1 测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_catalog_import.py -q`

Expected: PASS，夹具中的两条合格商品均被标准化，坏记录均被排除。

- [ ] **Step 6: 提交契约与规范化逻辑**

```powershell
git add backend/scripts/import_tianchi_catalog.py backend/tests/test_tianchi_catalog_import.py
git commit -m "feat: 添加天池商品数据规范化导入器"
```

### Task 2: 实现确定性抽样、原子输出与清单校验

**Files:**
- Modify: `backend/scripts/import_tianchi_catalog.py`
- Modify: `backend/tests/test_tianchi_catalog_import.py`

**Interfaces:**
- Consumes: Task 1 的规范化商品列表和命令行参数。
- Produces: `sample_products(products, sample_size, seed)`、`write_catalog(selected, output_dir, source_name, seed)`、`validate_output(output_dir, expected_count)`。

- [ ] **Step 1: 写入固定种子和失败不覆盖旧数据的测试**

创建 6 条规范化夹具商品，其中三条属于“上装”、三条属于“下装”。运行两次：

```python
first = sample_products(products, sample_size=4, seed=42)
second = sample_products(products, sample_size=4, seed=42)
assert first == second
```

再在 `out_dir/articles_sample.csv` 写入文本 `old-catalog`，以 `sample_size=7` 调用写入流程，并断言抛出 `ValueError` 后文件内容仍为 `old-catalog`。

- [ ] **Step 2: 运行测试，确认抽样与原子输出尚未实现**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_catalog_import.py -q`

Expected: FAIL，提示 `sample_products` 或 `write_catalog` 不存在。

- [ ] **Step 3: 实现稳定抽样**

实现：

```python
def sample_products(
    products: list[dict[str, str]], sample_size: int, seed: int
) -> list[dict[str, str]]:
    if sample_size <= 0:
        raise ValueError("sample_size must be greater than zero")
    if len(products) < sample_size:
        raise ValueError(f"Only {len(products)} valid products; need {sample_size}")
    buckets: dict[str, list[dict[str, str]]] = {}
    for product in sorted(products, key=lambda item: item["article_id"]):
        buckets.setdefault(product["product_group_name"], []).append(product)
    rng = random.Random(seed)
    selected: list[dict[str, str]] = []
    for group in sorted(buckets):
        rng.shuffle(buckets[group])
    while len(selected) < sample_size:
        progressed = False
        for group in sorted(buckets):
            if buckets[group] and len(selected) < sample_size:
                selected.append(buckets[group].pop())
                progressed = True
        if not progressed:
            break
    return sorted(selected, key=lambda item: item["article_id"])
```

不依赖输入文件的行顺序；候选 ID 与组名相同的情况必须得到相同结果。

- [ ] **Step 4: 实现临时目录写入和清单**

`write_catalog` 必须在 `output_dir.parent` 下创建 `tempfile.mkdtemp(prefix=".tianchi_catalog_")`，写入：

```text
articles_sample.csv
images/<article_id>.<extension>
catalog_manifest.json
```

使用 `data_utils.write_csv` 写出 `PRODUCT_FIELDS`，复制图片使用 `shutil.copy2`。`catalog_manifest.json` 包含：

```json
{
  "source": "tianchi-fashion-collection",
  "seed": 42,
  "product_count": 5000,
  "image_count": 5000,
  "articles_sha256": "由输出 articles_sample.csv 实际计算得到的 SHA-256"
}
```

只在 `validate_output` 返回的 `products == images == expected_count` 后，依次用 `os.replace` 替换 `articles_sample.csv` 与 `images/`；写入失败时删除临时目录但不触碰正式输出。

- [ ] **Step 5: 实现输出校验**

`validate_output` 读取 CSV，验证每条记录的 `image_path` 都以 `images/` 开头、无重复 `article_id`、能由 `resolve_image_path(output_dir, image_path)` 找到文件且文件长度大于零；失败时抛出 `RuntimeError`。成功时返回：

```python
{"products": expected_count, "images": expected_count}
```

- [ ] **Step 6: 运行 Task 2 测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_catalog_import.py -q`

Expected: PASS，固定种子稳定，失败不会覆盖旧目录，成功会得到 CSV、图片和清单。

- [ ] **Step 7: 提交原子导入能力**

```powershell
git add backend/scripts/import_tianchi_catalog.py backend/tests/test_tianchi_catalog_import.py
git commit -m "feat: 支持天池商品目录原子导入"
```

### Task 3: 增加命令行入口、端到端小样本测试和运行文档

**Files:**
- Modify: `backend/scripts/import_tianchi_catalog.py`
- Modify: `backend/tests/test_tianchi_catalog_import.py`
- Create: `docs/tianchi-catalog-import.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `--metadata`、`--images-dir`、字段参数及可选 `--sample-size`、`--seed`、`--out-dir`。
- Produces: 可重复运行的导入命令、导入清单和部署步骤。

- [ ] **Step 1: 编写 CLI 端到端测试**

从测试夹具启动子进程：

```python
command = [
    sys.executable, str(SCRIPTS_DIR / "import_tianchi_catalog.py"),
    "--metadata", str(metadata_path),
    "--images-dir", str(images_dir),
    "--id-column", "item_id",
    "--name-column", "title",
    "--image-column", "image",
    "--sample-size", "2",
    "--out-dir", str(out_dir),
]
completed = subprocess.run(command, capture_output=True, text=True)
assert completed.returncode == 0, completed.stdout + completed.stderr
assert json.loads((out_dir / "catalog_manifest.json").read_text())["product_count"] == 2
```

- [ ] **Step 2: 运行 CLI 测试，确认命令行参数尚未生效**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_catalog_import.py -q`

Expected: FAIL，参数解析或出口码断言失败。

- [ ] **Step 3: 实现 argparse 入口**

实现以下参数并在 `main()` 中按顺序调用读取、规范化、抽样、写入：

```text
--metadata PATH          必填，CSV/JSONL/JSON 商品元数据
--images-dir PATH        必填，天池图片根目录
--id-column NAME         必填
--name-column NAME       必填
--image-column NAME      必填，值必须是图片相对路径
--category-column NAME   可选
--color-column NAME      可选
--description-column NAME 可选
--price-column NAME      可选
--popularity-column NAME 可选
--sample-size INTEGER    默认 5000
--seed INTEGER           默认 42
--out-dir PATH           默认 backend/data/sample
```

所有异常都在 `if __name__ == "__main__"` 中打印 `ERROR: <message>` 并返回退出码 `1`。成功时打印 `SUCCESS: Tianchi catalog products=5000 images=5000`。

- [ ] **Step 4: 补充中文运行和部署文档**

创建 `docs/tianchi-catalog-import.md`，写明：

1. 天池数据包下载后放入 `backend/data/raw/`，不得提交。
2. 先运行 `--help` 和实际文件的字段检查，再根据字段名执行导入命令。
3. 导入后执行：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\build_sqlite.py
backend\.venv\Scripts\python.exe backend\scripts\build_text_index.py --backend hashing --force
backend\.venv\Scripts\python.exe backend\scripts\inspect_data.py
```

4. 上传 `articles_sample.csv`、`images/`、`catalog_manifest.json`、`app.db` 和 `vector_store/text/` 到虚拟机后，只重建 `backend`：

```bash
cd /root/RAG-agent
docker compose build backend
docker compose up -d backend
curl --fail http://127.0.0.1:8080/api/products?page=1\&page_size=1
```

5. 通过浏览器访问 `http://192.168.100.128:5173`，确认随机商品图片成功显示。

在根 `README.md` 的部署说明下添加该文档链接，并标明不提交原始数据与图片。

- [ ] **Step 5: 运行全套相关验证**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_tianchi_catalog_import.py -q
git diff --check
```

Expected: 全部 pytest 通过；`git diff --check` 无输出。

- [ ] **Step 6: 提交 CLI 与文档**

```powershell
git add backend/scripts/import_tianchi_catalog.py backend/tests/test_tianchi_catalog_import.py docs/tianchi-catalog-import.md README.md
git commit -m "docs: 补充天池商品数据导入说明"
```

### Task 4: 使用真实天池包执行一次受控导入并准备 PR

**Files:**
- Modify: `docs/tianchi-catalog-import.md`（仅在实际字段名与样例命令确定后补充）

**Interfaces:**
- Consumes: 用户合法下载且本地保存的天池原始包。
- Produces: 已校验的本地运行数据；代码与文档 PR，不包含原始数据。

- [ ] **Step 1: 将天池原始包放入受忽略目录并查看字段**

将文件放入 `backend/data/raw/`，解压后执行：

```powershell
Get-ChildItem backend\data\raw -Recurse -File | Select-Object FullName,Length
```

从商品元数据文件选择真实列名，且确认图片根目录中的图片数至少为 5,000。

- [ ] **Step 2: 使用真实字段参数导入 5,000 条商品**

执行 Task 3 文档中的命令，将 `<metadata-file>`、`<images-dir>` 与列名替换为实际值。命令完成后验证：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\inspect_data.py
```

Expected: `images=5000/5000 (100.00%)`，`empty=0`。

- [ ] **Step 3: 构建商品库和文本索引**

Run:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\build_sqlite.py
backend\.venv\Scripts\python.exe backend\scripts\build_text_index.py --backend hashing --force
```

Expected: SQLite 输出 `rows=5,000`；文本索引输出 `indexable products: 5,000`。

- [ ] **Step 4: 确认运行数据不被 Git 跟踪**

Run:

```powershell
git status --short
git check-ignore backend/data/sample/images backend/data/sqlite/app.db backend/data/vector_store/text
```

Expected: `git status` 中只出现源码、测试和文档；三条运行数据路径均被忽略。

- [ ] **Step 5: 提交实际字段示例与发起中文 PR**

仅提交脚本、测试和文档，不提交 `backend/data/` 中的原始包、图片、数据库或索引：

```powershell
git add backend/scripts/import_tianchi_catalog.py backend/tests/test_tianchi_catalog_import.py docs/tianchi-catalog-import.md README.md
git commit -m "feat: 支持天池服装商品数据导入"
git push -u origin feature/tianchi-catalog-import
```

PR 标题：`feat: 支持天池服装商品数据导入`

PR 描述应说明：导入器支持 5,000 件带图商品、保持既有业务接口不变、原始数据与图片未提交、已完成测试与实际数据校验。
