# 服装消费决策 Agent Harness

该 Harness 让 Agent 在可控边界内执行多步骤购衣任务，而不是只生成对话文本。

## 运行模型

```text
输入 → Skill 选择 → LangGraph 工作流 → 白名单工具 → 事实校验
     → 证据化结果 → 确认式写入 → Trace / 回放 / 自动评测
```

### 版本化 Skill

| Skill | 风险级别 | 允许工具 |
| --- | --- | --- |
| `catalog_retrieval@v1` | 只读 | 文本、图片、图文检索 |
| `product_comparison@v1` | 只读 | 商品对比 |
| `purchase_decision@v1` | 只读 | 检索、商品详情、Java 决策事实 |
| `wardrobe_planning@v1` | 只读 | 缺失品类检索、版本化衣橱 |
| `purchase_handoff@v1` | 需用户确认 | 商品详情；Java 最终写入购物车 |

Skill 是工具边界和评测单元，不是额外 LLM 路由层。每次任务的 Skill 与版本会写入 LangGraph 检查点、API 响应和 SSE `meta` 事件。

## 任务回放

`POST /api/tasks/{task_id}/replay`，请求体为：

```json
{"session_id":"session-123"}
```

回放返回节点、工具、证据引用、上下文版本和结构化结果，不返回原始提示词、模型回答、上传图片或身体数据。登录任务需要同一可信用户上下文。

## 自动化 Harness 评测

评测覆盖端到端任务成功、Skill 与工具边界、节点 Trace、确认式写入门禁：

```powershell
python backend/scripts/evaluate_agent_harness.py `
  --text-index /tmp/agent-evaluation-index `
  --report /tmp/agent-harness-evaluation.json
```

CI 默认要求：任务成功率 100%、工具策略违规率 0、需确认任务的确认门禁覆盖率 100%。测试样本见 `backend/evaluation/harness_cases.json`，新增业务 Skill 时必须同步增加样本和阈值验证。

## 安全和降级边界

- 工具只能从注册表调用，且必须被当前 Skill 显式允许；
- 价格、库存、SKU 尺寸、身体档案与衣橱由 Java 业务服务提供；
- Python Agent 不直接写购物车或订单；加购必须由用户确认，Java 再复核价格、库存、签名和幂等性；
- 模型规划失败回退到确定性意图和工具选择；检索节点仅有限重试；
- Trace 只记录标识、耗时、节点和工具元数据，用于诊断和评测。
