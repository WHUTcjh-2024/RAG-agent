# Agent 阶段 3：检索升级

检索采用硬约束前置的本地多路架构：`Dense`、`BM25` 和（图文请求时）`Image` 独立召回，随后用 RRF 融合前 50 个候选，再使用可配置的重排器排序。

- 默认重排器为确定性的 `lexical`，适用于离线和测试环境。
- 设置 `RERANKER_BACKEND=cross-encoder` 可启用 `RERANKER_MODEL`（默认 `BAAI/bge-reranker-v2-m3`）进行模型重排。
- `build_text_index.py` 会在文本索引内生成 `bm25.json`，并在 `metadata.json` 记录输入文件 SHA-256、稀疏索引版本和构建时间。
- 每项返回商品都包含 `retrieval`：召回来源、每路名次、原始分数、RRF 分数、重排分数和索引版本，供 Agent Trace 与前端排障使用。

离线评测使用 `backend/evaluation/cases.json` 中与商品描述不同的中文需求和相关商品 ID；命令为：

```powershell
python backend/scripts/evaluate_recommendations.py
```

报告包含 Recall@1/@5/@10、MRR@10、NDCG@10 和 P50/P95 延迟。新增标注时只追加 `labeled_retrieval` 用例，不使用商品原始 `text_profile` 作为查询。
