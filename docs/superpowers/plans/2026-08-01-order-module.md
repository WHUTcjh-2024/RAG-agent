# Java 订单模块实现计划

> **供智能开发工具执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行。步骤使用复选框跟踪。

**目标：** 在 Java 后端提供带 JWT 保护、幂等防重复创建和购物车并发保护的订单创建、查询与取消接口。

**架构：** 使用 `orders` 与 `order_items` 保存不可变的商品快照。创建订单时，对当前用户行加数据库悲观锁以串行化同一用户的提交；购物车项使用 JPA 乐观锁检测并发修改；`Idempotency-Key` 与用户组合唯一，重复请求返回同一订单。订单创建、订单明细写入和已结算购物车项删除位于同一事务中。

**技术栈：** Java 17、Spring Boot 3.3、Spring Cloud Gateway、Spring Data JPA、Hibernate、Flyway、H2（开发环境）、JUnit 5、WebTestClient。

## 全局约束

- 继续使用 Java 处理核心交易业务，不能改动 Python RAG 主流程。
- 所有订单接口必须使用现有 `Authorization: Bearer <JWT>` 方式认证。
- 金额使用 `BigDecimal` 和数据库 `DECIMAL(19, 2)`，不得使用 `double` 或 `float`。
- 每个新增行为都必须先运行对应失败测试，再写最小实现。
- 不新增 Redis、消息队列、支付、库存、地址、物流或前端改动；这些属于后续 `production-readiness` 分支。

---

## 文件结构

- 修改：`java-backend/src/main/resources/db/migration/V3__create_orders_and_add_cart_version.sql`，创建订单表并给购物车添加版本字段。
- 修改：`java-backend/src/main/java/com/atelier/gateway/cart/CartItem.java`，增加 JPA 乐观锁版本字段。
- 修改：`java-backend/src/main/java/com/atelier/gateway/cart/CartItemRepository.java`，提供已选购物车项查询。
- 修改：`java-backend/src/main/java/com/atelier/gateway/user/UserRepository.java`，提供锁定当前用户的查询。
- 修改：`java-backend/src/main/java/com/atelier/gateway/common/ApiExceptionHandler.java`，将乐观锁冲突映射为 `409`。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderStatus.java`，订单状态枚举。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/Order.java`，订单主实体。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderItem.java`，订单明细快照实体。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderRepository.java`，订单查询接口。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderItemRepository.java`，订单明细查询接口。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderResponses.java`，订单响应记录类型。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderService.java`，认证、事务、幂等与订单业务。
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderController.java`，HTTP 接口。
- 创建：`java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java`，订单接口集成测试。

## 任务 1：数据库结构与购物车并发版本

**文件：**

- 创建：`java-backend/src/main/resources/db/migration/V3__create_orders_and_add_cart_version.sql`
- 修改：`java-backend/src/main/java/com/atelier/gateway/cart/CartItem.java`
- 修改：`java-backend/src/main/java/com/atelier/gateway/cart/CartItemRepository.java`
- 修改：`java-backend/src/main/java/com/atelier/gateway/user/UserRepository.java`
- 修改：`java-backend/src/main/java/com/atelier/gateway/common/ApiExceptionHandler.java`
- 测试：`java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java`

**接口：**

- `CartItemRepository.findByUserIdAndSelectedTrueOrderByCreatedAtAsc(UUID userId)` 返回当前用户已选购物车项。
- `UserRepository.findByIdForUpdate(UUID userId)` 在订单创建事务中锁定一个用户。
- 乐观锁冲突返回 `409 Cart changed, please retry`。

- [ ] **步骤 1：先写会失败的迁移验证测试**

在 `OrderControllerIntegrationTest` 中加入数据库清理方法，使其先删除 `order_items`、`orders`、`cart_items` 和用户；然后加入测试骨架：

```java
@Test
void createOrderRequiresLogin() {
    webTestClient.post()
        .uri("/api/orders")
        .header("Idempotency-Key", "create-without-login")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

- [ ] **步骤 2：运行失败测试，确认失败原因是订单路由不存在**

运行：`cd D:\727push\java-backend; mvn -q -Dtest=OrderControllerIntegrationTest#createOrderRequiresLogin test`

预期：失败，原因是 `POST /api/orders` 尚未实现；不要为了通过本步骤添加控制器。

- [ ] **步骤 3：新增 Flyway 迁移与并发基础设施**

创建迁移文件，内容如下：

```sql
ALTER TABLE cart_items ADD COLUMN version BIGINT NOT NULL DEFAULT 0;

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount DECIMAL(19, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uk_orders_user_idempotency UNIQUE (user_id, idempotency_key),
    CONSTRAINT ck_orders_total_non_negative CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    product_id VARCHAR(128) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    product_image_url VARCHAR(1024),
    unit_price DECIMAL(19, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    subtotal DECIMAL(19, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT ck_order_items_quantity_positive CHECK (quantity >= 1),
    CONSTRAINT ck_order_items_price_non_negative CHECK (unit_price >= 0),
    CONSTRAINT ck_order_items_subtotal_non_negative CHECK (subtotal >= 0)
);

CREATE INDEX idx_orders_user_created_at ON orders(user_id, created_at);
CREATE INDEX idx_order_items_order_created_at ON order_items(order_id, created_at);
```

在 `CartItem` 的 `updatedAt` 字段后添加：

```java
@Version
@Column(nullable = false)
private long version;
```

并加入 `jakarta.persistence.Version` 导入。为 `CartItemRepository` 添加：

```java
List<CartItem> findByUserIdAndSelectedTrueOrderByCreatedAtAsc(UUID userId);
```

为 `UserRepository` 添加：

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select user from UserAccount user where user.id = :userId")
Optional<UserAccount> findByIdForUpdate(@Param("userId") UUID userId);
```

并添加所需的 `Lock`、`LockModeType`、`Query`、`Param` 与 `Optional` 导入。最后为 `ApiExceptionHandler` 添加：

```java
@ExceptionHandler(ObjectOptimisticLockingFailureException.class)
public ResponseEntity<ApiError> handleOptimisticLock(ObjectOptimisticLockingFailureException ex) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
        .body(new ApiError("Cart changed, please retry"));
}
```

- [ ] **步骤 4：运行迁移相关测试**

运行：`cd D:\727push\java-backend; mvn -q -Dtest=CartControllerIntegrationTest test`

预期：通过，Flyway 能创建新表，既有购物车测试不回归。

- [ ] **步骤 5：提交数据库与并发基础设施**

```powershell
cd D:\727push
git add java-backend/src/main/resources/db/migration/V3__create_orders_and_add_cart_version.sql java-backend/src/main/java/com/atelier/gateway/cart/CartItem.java java-backend/src/main/java/com/atelier/gateway/cart/CartItemRepository.java java-backend/src/main/java/com/atelier/gateway/user/UserRepository.java java-backend/src/main/java/com/atelier/gateway/common/ApiExceptionHandler.java
git commit -m "feat: 添加订单数据表和购物车并发保护"
```

## 任务 2：创建订单与幂等返回

**文件：**

- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderStatus.java`
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/Order.java`
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderItem.java`
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderRepository.java`
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderItemRepository.java`
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderResponses.java`
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderService.java`
- 创建：`java-backend/src/main/java/com/atelier/gateway/order/OrderController.java`
- 修改：`java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java`

**接口：**

- `OrderService.createOrder(String authorizationHeader, String idempotencyKey)` 返回 `OrderDetailView`。
- `POST /api/orders` 读取 `Authorization` 和必填的 `Idempotency-Key`，在 `boundedElastic` 调度器执行。
- `OrderDetailView` 返回订单、商品快照、总金额和状态。

- [ ] **步骤 1：写创建订单、保留未选商品与幂等的失败测试**

在 `OrderControllerIntegrationTest` 中新增测试：先注册用户，加入一件 `selected=true` 商品与一件 `selected=false` 商品，然后发起请求：

```java
webTestClient.post()
    .uri("/api/orders")
    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
    .header("Idempotency-Key", "checkout-001")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.status").isEqualTo("PENDING_PAYMENT")
    .jsonPath("$.totalAmount").isEqualTo(259.98)
    .jsonPath("$.items.length()").isEqualTo(1)
    .jsonPath("$.items[0].subtotal").isEqualTo(259.98);
```

随后再次使用相同幂等键请求，并断言返回的 `id` 与首次相同；调用 `GET /api/cart`，断言只剩未选商品。

- [ ] **步骤 2：运行测试，确认失败原因是订单实现不存在**

运行：`cd D:\727push\java-backend; mvn -q -Dtest=OrderControllerIntegrationTest#createOrderCopiesSelectedItemsAndIsIdempotent test`

预期：失败，原因是控制器、实体与服务尚不存在。

- [ ] **步骤 3：实现最小订单实体、仓储、服务与控制器**

`OrderStatus.java`：

```java
public enum OrderStatus {
    PENDING_PAYMENT,
    CANCELLED
}
```

`OrderRepository.java`：

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {
    Optional<Order> findByUserIdAndIdempotencyKey(UUID userId, String idempotencyKey);
    List<Order> findByUserIdOrderByCreatedAtDesc(UUID userId);
    Optional<Order> findByIdAndUserId(UUID id, UUID userId);
}
```

`OrderItemRepository.java`：

```java
public interface OrderItemRepository extends JpaRepository<OrderItem, UUID> {
    List<OrderItem> findByOrderIdOrderByCreatedAtAsc(UUID orderId);
}
```

`OrderService.createOrder` 必须使用以下顺序：

```java
UUID userId = currentUserId(authorizationHeader);
String key = requireIdempotencyKey(idempotencyKey);
userRepository.findByIdForUpdate(userId).orElseThrow(this::loginRequired);
return orderRepository.findByUserIdAndIdempotencyKey(userId, key)
    .map(this::detailView)
    .orElseGet(() -> createNewOrder(userId, key));
```

`createNewOrder` 查询 `findByUserIdAndSelectedTrueOrderByCreatedAtAsc`；为空时抛出 `new ApiException(HttpStatus.BAD_REQUEST, "No selected cart items")`。它以购物车的 `unitPrice.multiply(BigDecimal.valueOf(quantity))` 计算小计，保存订单和明细，最后调用 `cartItemRepository.deleteAll(selectedItems)`。整个 `createOrder` 方法标注 `@Transactional`。

控制器采用项目既有模式：

```java
@PostMapping
public Mono<OrderDetailView> createOrder(
    @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
    @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey
) {
    return Mono.fromCallable(() -> orderService.createOrder(authorization, idempotencyKey))
        .subscribeOn(Schedulers.boundedElastic());
}
```

- [ ] **步骤 4：运行创建订单测试**

运行：`cd D:\727push\java-backend; mvn -q -Dtest=OrderControllerIntegrationTest#createOrderCopiesSelectedItemsAndIsIdempotent test`

预期：通过；同一幂等键的两次请求返回相同订单标识，未选购物车项仍存在。

- [ ] **步骤 5：为缺少幂等键和空选择写失败测试并实现错误返回**

分别断言：缺少 `Idempotency-Key` 时返回 `400` 和 `Idempotency key is required`；购物车没有选中项时返回 `400` 和 `No selected cart items`。`requireIdempotencyKey` 必须拒绝空白键和长度超过 128 的键：

```java
private String requireIdempotencyKey(String value) {
    if (value == null || value.isBlank() || value.trim().length() > 128) {
        throw new ApiException(HttpStatus.BAD_REQUEST, "Idempotency key is required");
    }
    return value.trim();
}
```

运行：`cd D:\727push\java-backend; mvn -q -Dtest=OrderControllerIntegrationTest test`

预期：通过。

- [ ] **步骤 6：提交订单创建能力**

```powershell
cd D:\727push
git add java-backend/src/main/java/com/atelier/gateway/order java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java
git commit -m "feat: 支持从购物车创建幂等订单"
```

## 任务 3：订单列表、详情与取消

**文件：**

- 修改：`java-backend/src/main/java/com/atelier/gateway/order/OrderService.java`
- 修改：`java-backend/src/main/java/com/atelier/gateway/order/OrderController.java`
- 修改：`java-backend/src/main/java/com/atelier/gateway/order/Order.java`
- 修改：`java-backend/src/main/java/com/atelier/gateway/order/OrderResponses.java`
- 修改：`java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java`

**接口：**

- `OrderService.currentOrders(String authorizationHeader)` 返回 `List<OrderSummaryView>`。
- `OrderService.orderDetail(String authorizationHeader, UUID orderId)` 返回 `OrderDetailView`。
- `OrderService.cancelOrder(String authorizationHeader, UUID orderId)` 返回 `OrderDetailView`。

- [ ] **步骤 1：为列表、详情、越权和取消写失败测试**

创建订单后验证：

```java
webTestClient.get()
    .uri("/api/orders")
    .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.orders.length()").isEqualTo(1)
    .jsonPath("$.orders[0].status").isEqualTo("PENDING_PAYMENT");

webTestClient.post()
    .uri("/api/orders/{orderId}/cancel", orderId)
    .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.status").isEqualTo("CANCELLED");
```

使用另一用户令牌请求订单详情，断言 `404 Order not found`；第二次取消，断言 `400 Order cannot be cancelled`。

- [ ] **步骤 2：运行失败测试**

运行：`cd D:\727push\java-backend; mvn -q -Dtest=OrderControllerIntegrationTest#usersCanListViewAndCancelOnlyTheirOwnOrders test`

预期：失败，原因是列表、详情与取消路由尚未实现。

- [ ] **步骤 3：实现查询与取消最小逻辑**

在 `Order` 增加状态变更方法：

```java
public void cancel() {
    if (status != OrderStatus.PENDING_PAYMENT) {
        throw new ApiException(HttpStatus.BAD_REQUEST, "Order cannot be cancelled");
    }
    status = OrderStatus.CANCELLED;
    updatedAt = Instant.now();
}
```

服务层查询订单时必须使用 `findByIdAndUserId`，找不到时抛出：

```java
throw new ApiException(HttpStatus.NOT_FOUND, "Order not found");
```

控制器新增：

```java
@GetMapping
public Mono<OrderListView> currentOrders(...)

@GetMapping("/{orderId}")
public Mono<OrderDetailView> orderDetail(..., @PathVariable UUID orderId)

@PostMapping("/{orderId}/cancel")
public Mono<OrderDetailView> cancelOrder(..., @PathVariable UUID orderId)
```

三个方法都按现有控制器模式以 `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` 调用服务。

- [ ] **步骤 4：运行订单集成测试**

运行：`cd D:\727push\java-backend; mvn -q -Dtest=OrderControllerIntegrationTest test`

预期：通过，覆盖列表、详情、用户隔离、取消和重复取消。

- [ ] **步骤 5：提交订单查询与取消能力**

```powershell
cd D:\727push
git add java-backend/src/main/java/com/atelier/gateway/order java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java
git commit -m "feat: 支持订单查询和取消"
```

## 任务 4：完整验证与交付说明

**文件：**

- 修改：`README.md`，仅在已有 Java 后端说明区域补充订单接口和 `Idempotency-Key` 使用要求。
- 测试：全部 `java-backend` 测试。

- [ ] **步骤 1：补充 README 订单接口说明**

添加以下内容，并明确 `POST /api/orders` 必须携带不重复的 `Idempotency-Key`：

```text
POST /api/orders
GET /api/orders
GET /api/orders/{orderId}
POST /api/orders/{orderId}/cancel
```

- [ ] **步骤 2：运行完整 Java 测试套件**

运行：`cd D:\727push\java-backend; mvn test`

预期：全部通过；任何失败先修复后再继续，不允许跳过失败测试。

- [ ] **步骤 3：检查改动范围**

运行：`cd D:\727push; git diff main...HEAD --check; git status --short`

预期：没有空白错误，且仅包含订单、必要购物车并发保护、设计文档和 README 改动。

- [ ] **步骤 4：提交文档与最终验证结果**

```powershell
cd D:\727push
git add README.md
git commit -m "docs: 补充订单接口说明"
```

提交后记录 `mvn test` 的实际结果，供中文 PR 描述引用。
