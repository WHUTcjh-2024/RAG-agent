# 天池原始服装数据适配设计

## 目标

让项目可直接使用天池“淘宝穿衣搭配数据集”的 `dim_items` 原始文本和解压后的图片目录，稳定生成现有商品导入流程可用的 5,000 条本地商品目录。

## 已确认的原始数据结构

- `dim_items.txt` 每行由空格分隔：商品 ID、类目 ID、分词后的标题 ID 序列。
- 图片文件名为商品 ID，例如 `1000004.jpg`；图片可能位于天池压缩包自带的嵌套目录中。
- 原始数据不包含可直接显示的中文标题或售价。

## 方案

新增独立脚本 `backend/scripts/import_tianchi_fashion_collection.py`，只处理天池这套原始格式：

1. 递归索引图片目录中的 JPG、JPEG、PNG、WEBP 文件，以文件名中的商品 ID 建立映射。
2. 流式读取 `dim_items.txt`，只保留同时存在有效图片的商品，读取商品 ID 与类目 ID。
3. 为保留商品生成可读展示字段：商品名为“天池服装 类目{类目 ID} 商品{商品 ID}”，描述明确说明标题为原始分词 ID 序列，类目使用天池原始类目 ID。
4. 生成确定性的演示价格，范围为 99 至 498 元，仅用于现有购物车和订单流程；文档明确该价格不是天池原始售价。
5. 复用现有 `sample_products`、`write_catalog` 和 `validate_output`，继续获得确定性抽样、图片校验、原子发布和中断恢复能力。

## 命令行接口

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_fashion_collection.py `
  --items backend\data\raw\tianchi\dim_items.txt `
  --images-dir backend\data\raw\tianchi\images `
  --sample-size 5000 `
  --seed 42
```

默认输出仍为受 Git 忽略的 `backend/data/tianchi-catalog/`。

## 边界与失败处理

- 原始行格式不合法、商品 ID 或类目 ID 非数字时跳过该行。
- 不存在图片、图片格式不受支持、图片损坏或同一商品 ID 对应多张图片时跳过该商品。
- 有效商品少于请求数量时失败，且不替换已有目录。
- 不提交原始天池文本、压缩包、图片、SQLite 数据库或生成目录。
- 不改动 `backend/app/` 下的 Python RAG 服务逻辑。

## 测试

- 验证原始行解析、嵌套图片目录匹配、可读字段与确定性演示价格。
- 验证重复图片 ID、损坏图片、无效原始行和商品数量不足时的行为。
- 通过 CLI 生成小型目录，并复用现有目录校验检查 CSV、图片和清单。
