# Java 订单模块设计

## 目标

在 Java 后端提供已登录用户的订单创建、查询和取消能力。订单从当前用户已选中的购物车项生成，并保存独立商品快照，为后续接入支付、库存和物流做好准备。

## 范围

本期包含：

- 从已选购物车项创建订单。
- 查询当前用户的订单列表和订单详情。
- 取消待支付订单。
- JWT 身份校验与用户级数据隔离。

本期不包含真实支付、库存校验或扣减、优惠、收货地址、物流和前端页面改造。

## 数据模型

使用两张表：

- `orders`：包含 `id`、`user_id`、`status`、`total_amount`、`created_at`、`updated_at`。
- `order_items`：包含 `id`、`order_id`、`product_id`、`product_name`、`product_image_url`、`unit_price`、`quantity`、`subtotal`、`created_at`。

新订单状态为 `PENDING_PAYMENT`，取消后的状态为 `CANCELLED`。金额统一使用 `DECIMAL(19, 2)`；订单总额等于全部订单明细小计之和。

## 接口

- `POST /api/orders`：从已选购物车项创建订单；无请求体。
- `GET /api/orders`：查询当前用户的订单列表，按创建时间倒序。
- `GET /api/orders/{orderId}`：查询当前用户的一笔订单及其明细。
- `POST /api/orders/{orderId}/cancel`：取消当前用户处于待支付状态的订单。

所有接口均沿用现有 `Authorization: Bearer <JWT>` 认证方式。

## 创建流程

1. 从 JWT 解析并校验当前用户。
2. 查询该用户所有 `selected = true` 的购物车项。
3. 没有已选商品时，返回 `400 No selected cart items`。
4. 创建订单，并将每个购物车项复制为订单明细快照。
5. 基于购物车快照计算每项小计和订单总额。
6. 仅删除本次进入订单的购物车项。

订单写入和购物车删除必须处于同一个数据库事务中；任何一步失败都整体回滚。

## 权限与错误处理

- 缺少、无效或用户不存在的 JWT：`401 Login required`。
- 查询到其他用户的订单，或订单不存在：`404 Order not found`。
- 取消非待支付状态的订单：`400 Order cannot be cancelled`。
- 没有选中购物车项时创建订单：`400 No selected cart items`。

实现继续使用现有 `ApiException` 和统一错误响应格式。

## 测试

集成测试覆盖以下行为：

- 创建订单必须登录。
- 创建订单会复制商品快照、正确计算金额，并保留未选中的购物车项。
- 没有已选商品时返回错误。
- 用户不能读取其他用户的订单或订单详情。
- 待支付订单可以取消。
- 已取消订单不能再次取消。

每项行为先编写失败测试，再补充最小实现；最终执行 `mvn test` 完成验证。
