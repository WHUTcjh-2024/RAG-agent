# Agent 阶段 6：生产化联调记录

## 已交付

- OpenTelemetry 兼容的脱敏任务与节点追踪；记录任务、节点、失败类型和耗时，不记录提示词、图片路径或检索正文。
- Java 业务事实与衣橱读取使用超时和熔断；模型规划仍保持一次重试与确定性回退，检索节点使用三次有限重试。
- 任务取消、会话主动删除、会话 TTL（默认 7 天）和检查点 TTL（默认 24 小时）。取消在每个工作流节点前生效，已完成任务继续保持幂等返回。
- 提示注入关键词不会进入 LLM 工具选择；工具调用仍受注册表白名单限制。
- 固定离线评测已加入 CI：样本数据先构建可复现的哈希索引，再对检索、意图和槽位执行阈值门禁。

## 联调与故障演练

| 场景 | 结果 |
| --- | --- |
| Python Agent 全量回归 | 58 passed |
| 固定离线评测 | 32 用例通过；本地模型索引：Recall@5 0.90，Recall@10 0.90，NDCG@10 0.712；CI 哈希索引门禁：NDCG@10 不低于 0.64 |
| 前端单测和生产构建 | Vitest 4 passed；Vite build passed |
| 前端端到端回归 | Playwright 6 passed |
| Java 模块 | 本机缺少 Maven，未执行；PR CI 的 `java-test` 会执行 Maven 测试 |
| Java 上游故障 | 熔断器连续 3 次依赖失败后快速返回可重试的 `UPSTREAM_UNAVAILABLE`，避免级联超时 |
| 取消和重复写 | 取消任务在下一节点前返回 `TASK_CANCELLED`；现有 `agent_task_commits` 继续保证同一 task 只提交一次记忆写入 |

## 运行配置

- `SESSION_TTL_SECONDS`：会话保留时长，默认 604800。
- `CHECKPOINT_TTL_SECONDS`：工作流检查点保留时长，默认 86400。
- `AGENT_TELEMETRY_CAPACITY`：本地脱敏追踪环形缓冲区容量，默认 300。
