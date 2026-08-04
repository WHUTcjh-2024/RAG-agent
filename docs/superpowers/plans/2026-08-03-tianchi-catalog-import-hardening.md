# 天池商品导入安全加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复天池商品导入器在路径安全、异常中断恢复、数值数据契约和部署替换方面的风险。

**Architecture:** 导入前将商品 ID 限制为安全文件名片段，并在规格化阶段校验价格和热度为有限数值。目录发布使用持久化事务记录：下次导入会先恢复未提交事务，已提交事务只清理备份。真实数据默认写入被 Git 忽略的运行目录；部署通过先暂存、停服务、备份切换和失败恢复完成。

**Tech Stack:** Python 3.12、pytest、Pillow、CSV、SQLite、Docker Compose、Bash。

## 全局约束

- 不修改 `backend/app/` 中的 Python RAG 主流程。
- 不修改 Java 服务和前端。
- 天池原始数据、图片、SQLite 文件和文本索引不得提交 Git。
- 所有新增行为先写失败测试，再写最小实现。

---

### Task 1: 输入与数值契约

**Files:**
- Modify: `backend/scripts/import_tianchi_catalog.py`
- Test: `backend/tests/test_tianchi_catalog_import.py`

**Interfaces:**
- Produces: `normalize_products(rows, images_dir, mapping)` 仅返回安全 ID、有限价格和有限热度的商品。

- [ ] **Step 1: 写入失败测试**

```python
def test_normalize_products_rejects_path_like_article_id(...):
    assert normalize_products([... {"id": "../../escape"} ...], images_dir, mapping) == []

def test_normalize_products_rejects_non_numeric_price(...):
    assert normalize_products([... {"price": "N/A"} ...], images_dir, mapping) == []
```

- [ ] **Step 2: 运行失败测试**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_tianchi_catalog_import.py -q`
Expected: 新测试失败，因为当前实现会保留非法 ID 与价格。

- [ ] **Step 3: 写入最小实现**

```python
def _is_safe_article_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value))
```

在 `normalize_products` 中跳过不安全 ID 与不能转换为有限十进制数的价格或热度。

- [ ] **Step 4: 运行测试验证通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_tianchi_catalog_import.py -q`
Expected: PASS。

### Task 2: 可恢复目录发布

**Files:**
- Modify: `backend/scripts/import_tianchi_catalog.py`
- Test: `backend/tests/test_tianchi_catalog_import.py`

**Interfaces:**
- Produces: `write_catalog(...)` 在中断后由下一次调用先恢复旧目录；发布完成后不遗留事务记录。

- [ ] **Step 1: 写入失败测试**

```python
def test_write_catalog_recovers_after_keyboard_interrupt(...):
    with pytest.raises(KeyboardInterrupt):
        write_catalog(...)
    write_catalog(...)
    assert previous_catalog_is_not_partially_mixed(...)
```

- [ ] **Step 2: 运行失败测试**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_tianchi_catalog_import.py -q`
Expected: FAIL，因为 `KeyboardInterrupt` 不会触发当前 `except Exception` 回滚。

- [ ] **Step 3: 写入最小实现**

```python
def recover_catalog_transaction(output_dir: Path) -> None:
    # 对未提交事务恢复备份；对已提交事务只清理备份。
```

在每次目标移动前把原始存在状态和备份路径以原子方式记录到事务文件；开始写入时先执行恢复。

- [ ] **Step 4: 运行测试验证通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_tianchi_catalog_import.py -q`
Expected: PASS。

### Task 3: 运行目录与部署文档

**Files:**
- Modify: `.gitignore`
- Modify: `backend/scripts/import_tianchi_catalog.py`
- Modify: `docs/tianchi-catalog-import.md`
- Test: `backend/tests/test_tianchi_catalog_import.py`

**Interfaces:**
- Produces: 默认运行目录 `backend/data/tianchi-catalog/`，本地构建 SQLite 使用该目录，虚拟机通过受控切换将四类产物发布到运行目录。

- [ ] **Step 1: 写入失败测试**

```python
def test_default_output_directory_is_ignored_runtime_catalog():
    assert parse_args([...]).out_dir == BACKEND_DIR / "data" / "tianchi-catalog"
```

- [ ] **Step 2: 运行失败测试**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_tianchi_catalog_import.py -q`
Expected: FAIL，因为默认仍为受 Git 跟踪的 `data/sample`。

- [ ] **Step 3: 写入最小实现和文档**

```python
parser.add_argument("--out-dir", type=Path, default=BACKEND_DIR / "data" / "tianchi-catalog")
```

在 `.gitignore` 忽略运行目录；文档明确先上传到 VM 临时发布目录，再停 `backend`、移动旧数据到时间戳备份目录、切换新 CSV/图片/清单/SQLite，构建失败时恢复并启动旧容器。

- [ ] **Step 4: 运行测试验证通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_tianchi_catalog_import.py -q`
Expected: PASS。

### Task 4: 提交前验证与复审

**Files:**
- Test: `backend/tests/test_tianchi_catalog_import.py`
- Test: `backend/tests/`

- [ ] **Step 1: 运行专项测试**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_tianchi_catalog_import.py -q --basetemp .test-tmp -p no:cacheprovider`
Expected: PASS。

- [ ] **Step 2: 运行完整后端测试和差异检查**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests -q --basetemp .test-tmp -p no:cacheprovider; git diff --check main...HEAD`
Expected: PASS，允许已有第三方弃用警告。

- [ ] **Step 3: 请求最终只读代码审查**

审查输入路径安全、事务恢复、Git 忽略规则、数值契约和部署回滚；Critical 与 Important 必须在创建 PR 前解决。
