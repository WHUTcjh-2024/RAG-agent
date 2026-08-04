# 天池商品数据导入说明

## 天池原始数据说明

请在遵守天池“淘宝服装搭配数据集”许可、下载资格和署名要求的前提下使用数据。天池原始文件放在 `backend/data/raw/tianchi/`，其中 `dim_items.txt` 是空格分隔的原始文本，图片文件在 `images/` 目录里，文件名通常就是商品 ID。

如果天池提供的是大型图片 ZIP，请用 `tar -xf` 解压，不要用 PowerShell 的 `Expand-Archive`，因为它对这类 ZIP 不兼容。解压后的文本、图片和后续导入产物都应保留在 Git 忽略目录中。

天池未提供原始售价，目录里的价格只是给购物车和订单流程使用的确定性演示价格，不代表原始商品价格。

## 导入命令

运行下面的 PowerShell 命令，把 `dim_items.txt` 和图片目录导入为本地商品目录：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_tianchi_fashion_collection.py `
  --items backend\data\raw\tianchi\dim_items.txt `
  --images-dir backend\data\raw\tianchi\images `
  --sample-size 5000 `
  --seed 42
```

默认导入结果写入受 Git 忽略的 `backend/data/tianchi-catalog/`。导入过程中会跳过无效记录、缺失图片、重复图片、路径越界图片和非法数值；如果有效商品不足，原有运行目录不会被替换。

## 本地准备与边界

导入前先确认原始文本、图片目录和实际字段名。`dim_items.txt` 的内容用于原始商品 ID 和类目 ID；导入器会把它转换成现有商品目录所需的展示字段。这个流程只负责数据落地，不改动 Python RAG 服务，也不要求把原始天池数据、图片、SQLite 数据库或生成目录提交到 Git。

```powershell
Get-Content backend\data\raw\tianchi\dim_items.txt -TotalCount 3
Get-ChildItem backend\data\raw\tianchi\images -File -Recurse | Measure-Object
```

## 构建与发布

生成的目录后续仍然可以按照现有发布流程使用。`backend/data/tianchi-catalog/` 中应只保留用于发布的运行数据，其他临时文件、原始压缩包和中间产物都不要提交。
