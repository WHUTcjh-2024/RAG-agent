# Agent 阶段 4：确认式加购

购物车仍只由 Java 管理。Agent 仅在登录态、且能解析到单一商品时生成十分钟有效的 `confirm_required` 事件；前端明确确认后才调用 Java。

Java 对确认令牌进行 HMAC 校验，并以 Java 的 SKU 事实复核库存和价格。`agent_cart_action_commits` 以 `action_id` 去重，因此网络重试不会重复加购。

Python 只持久化动作状态和最终购物车条目引用，未新增购物车或订单实体。
