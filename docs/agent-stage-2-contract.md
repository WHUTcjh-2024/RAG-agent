# Agent 阶段 2：购衣决策卡契约

## 事实边界

- Java 是身体档案、SKU 尺寸、价格、库存和退换规则的唯一事实源。
- Python 仅通过 `AGENT_FACTS_BASE_URL/internal/agent/decision-facts` 读取这些事实；未配置或缺少可信用户上下文时，不回退到本地商品目录伪造事实。
- 网关只在 JWT 校验成功后向 `/api/chat` 与 `/api/chat/stream` 注入 `X-Trusted-User-Id` 和内部上下文令牌。Python 校验 `AGENT_CONTEXT_TOKEN` 后才信任该用户 ID，且不记录身体原始数据到 Trace。

## 新增 SSE 事件

```text
event: evidence
data: {"item": {"source_type":"SKU_MEASUREMENT", "source_id":"sku-1-m", "field":"chestCm", "value":"104.0", "observed_at":"2026-08-01T00:00:00Z"}}

event: decision
data: {"card": {"decision_id":"decision-uuid", "verdict":"RECOMMEND_BUY", "confidence":0.86, "recommended_size":"M", "fit_risks":[], "reasons":[], "evidence":[], "missing_fields":[], "alternatives":[]}}
```

旧客户端必须忽略未知事件；新客户端按结构化字段渲染，不解析回答文本。

## 决策规则

- `RECOMMEND_BUY`：库存可用且商品实测胸围至少比身体胸围大 6 cm。
- `BUY_WITH_CAUTION`：库存可用，但余量小于 6 cm。
- `NOT_RECOMMENDED`：无库存或商品实测胸围小于身体胸围。
- `INSUFFICIENT_DATA`：缺少可信身体档案、SKU 尺寸、价格或库存中的任一关键字段；不输出精确推荐尺码。

每个尺码与风险结论均引用 `BODY_PROFILE` 和 `SKU_MEASUREMENT` 证据。硬约束和结论由程序规则决定；模型分项只参与已通过约束后的置信度合成。

## 本地配置

设置相同的 `AGENT_INTERNAL_TOKEN` 给 Java 与 Python；Python 同时设置 `AGENT_FACTS_BASE_URL`、`AGENT_FACTS_INTERNAL_TOKEN` 和 `AGENT_CONTEXT_TOKEN`。Docker Compose 已使用同一变量连接两个服务。
