# MCP + Skill 体系（v1）

服务在 Python AI 进程中以 Streamable HTTP 暴露：`/mcp`。实现采用官方 MCP Python SDK，工具输入由 Pydantic 自动生成 JSON Schema；服务使用无状态 JSON 响应，适合横向扩容。官方文档见 [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/server/)。

## 工具边界

| 工具 | 权威来源 | 访问级别 | 写入边界 |
| --- | --- | --- | --- |
| `catalog_search` / `catalog_get_product` | 目录服务 | READ | 无 |
| `decision_facts_get` | Java 业务服务 | READ | 无 |
| `wardrobe_get_snapshot` / `wardrobe_plan_outfits` | Java 业务服务 | READ | 无 |
| `try_on_create_preview` | 试穿服务 | CONFIRMATION_REQUIRED | 创建异步预览，不含真人照片 |
| `cart_prepare_add` | Java 购物车服务 | CONFIRMATION_REQUIRED | 仅签发确认令牌，绝不写购物车 |

所有工具返回 `api_version`、策略、权威来源和结构化数据；所有调用写入不含 prompt/结果正文的 OTel Trace。MCP 没有订单、支付或直接购物车写工具。最终加购必须由客户端把确认令牌提交给 Java `POST /api/cart/agent-actions/confirm`。

## 认证与部署

`decision_facts_get`、`wardrobe_*`、`try_on_create_preview` 与 `cart_prepare_add` 需要 HTTP 调用方在受信请求头传入：

- `X-Trusted-User-Id`
- `X-Agent-Context-Token`，其值必须等于服务端 `AGENT_CONTEXT_TOKEN`

上述凭据不会作为 MCP 工具参数暴露给模型。生产环境必须通过 Java 网关、mTLS 或 OAuth 将受信用户上下文注入 MCP 调用；不应把内部 MCP 端点直接暴露给浏览器。`AGENT_FACTS_BASE_URL` 与 `AGENT_FACTS_INTERNAL_TOKEN` 用于 Python 读取 Java 权威衣橱事实。

## 可版本化 Skills

Skills 位于 `backend/app/mcp/skills/`，每项含稳定的名称、版本、允许工具和执行约束：

- `purchase-decision`：证据式购买判断、缺失事实处理及 Java 确认链路。
- `wardrobe-planning`：先复用 Java 衣橱，再推荐真实目录商品。
- `try-on-preview`：显式确认、幂等和“预览非合身证明”边界。

对 Skill 做破坏性变更时新建版本目录（例如 `purchase-decision-v2`），在一个发布周期内保留旧版本并记录迁移说明。
