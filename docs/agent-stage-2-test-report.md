# Agent 阶段 2 测试报告

> 日期：2026-08-01
> 分支：`codex/decision-card-mvp`

## 自动化结果

| 范围 | 命令 | 结果 |
|---|---|---:|
| Python 全量测试 | `python -m pytest backend/tests -q` | 43 passed |
| 前端单元测试 | `cd frontend; npm test -- --run` | 4 passed |
| 前端生产构建 | `cd frontend; npm run build` | 通过 |
| Compose 配置 | `$env:AGENT_INTERNAL_TOKEN='config-validation-only'; docker compose config --quiet` | 通过 |
| Java 单元与集成测试 | `cd java-backend; mvn -B test` | 本机缺少 Maven；Docker Hub OAuth 超时，未执行 |

## 覆盖内容

- 四类决策结论：推荐购买、谨慎购买、不推荐、数据不足；
- 缺少 SKU 尺寸时不输出精确尺码；
- 尺码与风险结论带身体档案和 SKU 实测证据；
- Java 内部事实接口的认证、用户身体档案和 SKU 事实字段；
- 决策 SSE 事件由前端按结构化卡片消费；
- 不依赖真实 LLM 的工作流决策卡集成测试。

## 已知限制

- Java 测试需要在具备 Maven 或可访问 Docker Hub 的环境复跑；本机 Docker 在拉取 `eclipse-temurin:17-jre` 的 OAuth 阶段超时。
- Java 的 `product_sku_facts` 表需由后续商品主数据同步写入；没有事实记录时系统按设计返回 `INSUFFICIENT_DATA`。
