# Agent Evals 与 Trace

执行 `python backend/scripts/evaluate_recommendations.py` 会生成版本化的 JSON 报告。它只接受 `labeled_retrieval` 中显式标注的真实目录相关性，不会再把商品自身作为查询和答案，从而避免自检索带来的虚高指标。

每次评测会校验目录快照 SHA-256；索引快照与标注快照不一致时直接以配置错误退出，必须重新审核标签。CI 使用仓库跟踪的 `backend/data/tianchi-demo/articles_sample.csv`，避免依赖未提交的本地目录。报告含检索、意图、槽位以及可执行任务的指标：任务成功率、工具参数正确率、事实引用覆盖率、拒答/注入通过率、任务 P95、预估成本和业务执行正确率。

任务 Trace 仅保存 case ID、输入指纹、断言结果、耗时和成本，不保存用户原文、检索内容或模型输出。业务正确性由真实的购买决策校验器和一次性购物车确认流程执行，而不是由文案匹配替代。

## LLM-as-a-Judge

主观推荐质量可启用独立评委配置，不复用生产模型密钥：

```powershell
$env:EVAL_LLM_JUDGE_API_KEY = "..."
$env:EVAL_LLM_JUDGE_MODEL = "..."
$env:EVAL_LLM_JUDGE_BASE_URL = "https://..." # 可选
python backend/scripts/evaluate_recommendations.py --llm-judge required
```

可通过 `EVAL_LLM_JUDGE_INPUT_USD_PER_1M` 和 `EVAL_LLM_JUDGE_OUTPUT_USD_PER_1M` 注入模型单价，报告将计入评委调用成本。CI 默认使用 `auto`：未配置评委时明确记录为 `not_configured`，不会伪造主观质量分数；发布门禁可改为 `--llm-judge required`。
