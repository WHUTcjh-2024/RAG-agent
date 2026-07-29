# Agent 阶段 0 接口契约

> 版本：v1.0
> 日期：2026-07-29
> 状态：已实现

## 1. 范围

本文冻结 Agent 阶段 0 的请求、响应、SSE、错误、Session 和 Request ID 契约。

兼容原则：

- 保留现有接口路径和请求字段；
- 仅增加 `request_id` 和结构化错误；
- 错误中的 `detail` 继续保留字符串，兼容旧前端；
- 前端必须忽略未知 SSE 事件。

## 2. Request ID

请求头：

```text
X-Request-Id
```

约束：

```text
长度：1—128
格式：^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$
```

处理规则：

1. 前端为 Agent 流式请求生成 UUID；
2. Java 验证请求头，合法时透传，不合法或缺失时重新生成；
3. Python 再次验证，合法时沿用，不合法或缺失时重新生成；
4. Java 和 Python 均在响应头返回最终 `X-Request-Id`；
5. Agent 响应、SSE Meta、SSE Error 和日志中返回相同 ID；
6. Request ID 只用于追踪，不作为身份或幂等凭证。

## 3. Session ID

约束：

```text
长度：1—100
格式：^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$
默认 TTL：7 天
环境变量：SESSION_TTL_SECONDS
```

规则：

- Chat 请求不提供 Session ID 时由 Python 生成；
- `/api/session` 必须提供合法 Session ID；
- 过期 Session 在启动或访问时清理；
- Session 保存对话、偏好槽位和最近商品 ID；
- Session 不保存用户、购物车、订单等业务主数据；
- Session ID 不能代替可信用户身份。

## 4. Chat 请求

### 4.1 流式

```text
POST /api/chat/stream
Content-Type: multipart/form-data
```

### 4.2 非流式

```text
POST /api/chat
Content-Type: multipart/form-data
```

字段：

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `message` | string | 否 | 与图片至少提供一个，最大 2000 字符 |
| `session_id` | string | 否 | 遵循 Session ID 约束 |
| `language` | enum | 否 | `zh` 或 `en`，默认 `zh` |
| `file` | image | 否 | 最大 10 MB，必须是有效图片 |

## 5. 非流式响应

```json
{
  "request_id": "request-123",
  "session_id": "web-session-123",
  "intent": "text_recommendation",
  "answer": "根据你的需求，我从真实商品库中筛出了这些候选。",
  "products": [],
  "comparison": [],
  "slots": {
    "color": "Red",
    "category": "Shirt"
  },
  "tool_trace": []
}
```

意图枚举：

| 意图 | 含义 |
|---|---|
| `text_recommendation` | 文本推荐 |
| `image_search` | 图片检索 |
| `hybrid_search` | 图文检索 |
| `compare` | 商品对比 |
| `cart_handoff` | 将购物车操作交给 Java |

## 6. SSE 契约

响应头：

```text
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
X-Request-Id: request-123
```

事件枚举：

| 事件 | 是否可重复 | 含义 |
|---|---:|---|
| `status` | 否 | 开始处理 |
| `meta` | 否 | Session、Intent、Slots |
| `tool` | 是 | 工具 Trace |
| `products` | 否 | 推荐商品 |
| `comparison` | 否 | 对比商品 |
| `message` | 是 | 回答文本片段 |
| `error` | 否 | 结构化错误 |
| `done` | 否 | 正常结束 |

正常顺序：

```text
status
→ meta
→ tool*
→ products | comparison（可选）
→ message*
→ done
```

异常顺序：

```text
status
→ error
```

Meta 示例：

```text
event: meta
data: {"request_id":"request-123","session_id":"web-session-123","intent":"text_recommendation","slots":{}}
```

Done 示例：

```text
event: done
data: {"ok":true,"request_id":"request-123"}
```

## 7. 工具 Trace

```json
{
  "tool": "search_products_by_text",
  "input": {
    "query": "红色衬衫",
    "filters": {
      "color": "Red",
      "category": "Shirt"
    },
    "top_k": 5
  },
  "summary": "returned 5 products"
}
```

约束：

- 图片路径只记录文件名，不记录本地绝对路径；
- 不记录 JWT、模型 Key、服务签名和用户密码；
- 不记录完整身体敏感数据；
- 工具不存在时返回 `TOOL_NOT_FOUND`；
- 参数无效时返回 `INVALID_TOOL_ARGUMENT`；
- 执行异常时返回 `TOOL_EXECUTION_FAILED` 或更具体错误。

## 8. 错误响应

HTTP 错误保留字符串 `detail`，同时增加强类型 `error`：

```json
{
  "detail": "Session ID 格式不合法",
  "error": {
    "request_id": "request-123",
    "code": "INVALID_SESSION_ID",
    "message": "Session ID 格式不合法",
    "retryable": false,
    "stage": "validate_input",
    "details": {}
  }
}
```

SSE Error 的 `data` 直接使用 `error` 对象：

```text
event: error
data: {"request_id":"request-123","code":"RETRIEVAL_UNAVAILABLE","message":"检索失败","retryable":true,"stage":"agent","details":{}}
```

错误码：

| 错误码 | HTTP | 默认可重试 | 含义 |
|---|---:|---:|---|
| `INVALID_INPUT` | 400/413/422 | 否 | 输入、图片或请求字段不合法 |
| `INVALID_SESSION_ID` | 400 | 否 | Session ID 不合法 |
| `INDEX_NOT_READY` | 503 | 是 | 本地索引缺失 |
| `RETRIEVAL_UNAVAILABLE` | 503 | 是 | 检索初始化或执行失败 |
| `TOOL_NOT_FOUND` | 400 | 否 | 工具不存在 |
| `INVALID_TOOL_ARGUMENT` | 400 | 否 | 工具参数不合法 |
| `TOOL_EXECUTION_FAILED` | 500/504 | 视情况 | 工具执行失败 |
| `MODEL_UNAVAILABLE` | 不中断 | 是 | 模型失败，当前流程自动降级 |
| `UPSTREAM_UNAVAILABLE` | 503 | 是 | Java 无法连接 Python |
| `INTERNAL_ERROR` | 500 | 否 | 未分类内部错误 |

模型故障存在可用规则降级时不返回失败响应，而是在日志中记录：

```text
code=MODEL_UNAVAILABLE stage=plan_tools
```

或：

```text
code=MODEL_UNAVAILABLE stage=generate_answer
```

## 9. 完整 Trace 示例

```text
Java:
request_received request_id=request-123 path=/api/chat/stream

Python:
agent_request_started request_id=request-123 session_id=web-session-123 has_image=false
agent_request_completed request_id=request-123 session_id=web-session-123 intent=text_recommendation tools=2 products=5
```

阶段 0 不记录用户完整消息内容，避免敏感需求进入普通业务日志。

## 10. 兼容性验证

- 旧前端仍可读取字符串 `detail`；
- 新前端可读取错误码、Request ID 和可重试标记；
- 新增 SSE 事件不会导致当前前端解析失败；
- `/api/chat`、`/api/chat/stream`、`/api/session` 和 `/api/compare` 路径不变；
- Java 继续作为前端统一入口；
- Python 不包含购物车和订单写入。
