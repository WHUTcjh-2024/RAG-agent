# 订单结算体验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 FitMe 的 Agent/商品推荐、Java 购物车与 Java 订单服务连成可在移动端完成并回看订单的真实闭环。

**Architecture:** 前端继续从 Python 商品目录和 Agent 获取商品、推荐与解释，从 Java 获取身份、购物车和订单。订单列表先获取 Java 的摘要响应，再并行获取每个订单详情以展示商品快照；下单请求使用一次性幂等键，提交完成后刷新购物车与订单状态。

**Tech Stack:** React 19、TypeScript、Zustand、Vite、Vitest、Playwright、Java Spring WebFlux 订单 API。

## Global Constraints

- 不修改 `backend/app` 中 Python RAG、Agent、检索或模型调用逻辑。
- 不修改 Java 订单领域规则、数据库结构或既有订单接口路径。
- 仅复用 `POST /api/orders`、`GET /api/orders`、`GET /api/orders/{orderId}`、`POST /api/orders/{orderId}/cancel`。
- 下单必须传递 `Idempotency-Key`，请求中禁用重复点击，失败时不得清空购物车。
- 保持现有中英文切换、移动端底部导航、减少动态效果偏好和 API 错误处理模式。

---

## 文件结构

- 修改 `frontend/src/types.ts`：定义 Java 订单摘要、详情、商品快照和状态类型。
- 修改 `frontend/src/api/client.ts`：增加创建、读取、取消订单的认证请求函数。
- 修改 `frontend/src/api/client.test.ts`：覆盖订单请求头、响应解析与失败传递。
- 修改 `frontend/src/components/CommerceOverlays.tsx`：在购物车抽屉中增加结算按钮和提交中状态。
- 新增 `frontend/src/components/OrdersScreen.tsx`：渲染订单列表、订单商品快照、取消和空状态。
- 修改 `frontend/src/App.tsx`：维护订单加载/结算状态，增加 `/orders` 路由和刷新逻辑。
- 修改 `frontend/src/components/ProfileScreen.tsx` 与 `frontend/src/components/MobileShell.tsx`：加入订单入口和页面标题。
- 修改 `frontend/src/i18n.ts` 与 `frontend/src/styles.css`：补充中英文文案和移动端样式。
- 修改 `frontend/e2e/shopping.spec.ts`：模拟 Java 订单 API，验证完整结算和取消流程。

## Task 1: 订单类型与 Java API 客户端

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: `authorized(token)`、`ensureOk(response)`、Java `OrderResponses` 的 camelCase JSON 字段。
- Produces: `OrderStatus`、`OrderSummary`、`OrderDetail`、`createOrder(token, idempotencyKey)`、`fetchOrders(token)`、`fetchOrderDetail(token, orderId)`、`cancelOrder(token, orderId)`。

- [ ] **Step 1: 写入失败的订单客户端测试**

在 `frontend/src/api/client.test.ts` 增加以下导入和测试；保持现有 `afterEach` 的全局 fetch 清理方式。

```ts
import { ApiClientError, cancelOrder, createOrder, fetchOrderDetail, fetchOrders } from "./client";

const orderDetail = {
  id: "00000000-0000-0000-0000-000000000201",
  status: "PENDING_PAYMENT",
  totalAmount: 0.13,
  items: [{
    id: "00000000-0000-0000-0000-000000000202",
    productId: "0000000001",
    productName: "White Office Shirt",
    productImageUrl: "/media/one.jpg",
    unitPrice: 0.05,
    quantity: 2,
    subtotal: 0.10,
    createdAt: "2026-08-07T00:00:00Z"
  }],
  createdAt: "2026-08-07T00:00:00Z",
  updatedAt: "2026-08-07T00:00:00Z"
};

it("creates an order with authentication and an idempotency key", async () => {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({
      Authorization: "Bearer token-1",
      "Idempotency-Key": "checkout-1"
    });
    return new Response(JSON.stringify(orderDetail), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);

  await expect(createOrder("token-1", "checkout-1")).resolves.toMatchObject(orderDetail);
});

it("reads order summaries, details and cancellation responses", async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.endsWith("/api/orders")) {
      return new Response(JSON.stringify({ orders: [{ ...orderDetail, items: undefined }] }), { status: 200 });
    }
    return new Response(JSON.stringify(orderDetail), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);

  await expect(fetchOrders("token-1")).resolves.toHaveLength(1);
  await expect(fetchOrderDetail("token-1", orderDetail.id)).resolves.toMatchObject(orderDetail);
  await expect(cancelOrder("token-1", orderDetail.id)).resolves.toMatchObject({ status: "PENDING_PAYMENT" });
});

it("keeps typed API failures when order creation fails", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "No selected cart items" }), { status: 400 })));
  await expect(createOrder("token-1", "checkout-2")).rejects.toBeInstanceOf(ApiClientError);
});
```

- [ ] **Step 2: 运行测试，确认因缺少导出而失败**

Run: `cd D:\727push\frontend; npm test -- --run src/api/client.test.ts`

Expected: FAIL，提示 `createOrder`、`fetchOrders`、`fetchOrderDetail` 或 `cancelOrder` 尚未导出。

- [ ] **Step 3: 定义订单类型和最小请求封装**

在 `frontend/src/types.ts` 的 `CartItem` 后增加：

```ts
export type OrderStatus = "PENDING_PAYMENT" | "CANCELLED";

export interface OrderSummary {
  id: string;
  status: OrderStatus;
  totalAmount: number;
  createdAt: string;
  updatedAt: string;
}

export interface OrderItem {
  id: string;
  productId: string;
  productName: string;
  productImageUrl?: string | null;
  unitPrice: number;
  quantity: number;
  subtotal: number;
  createdAt: string;
}

export interface OrderDetail extends OrderSummary {
  items: OrderItem[];
}
```

在 `frontend/src/api/client.ts` 的购物车函数后增加：

```ts
export async function createOrder(token: string, idempotencyKey: string): Promise<OrderDetail> {
  return (await ensureOk(await fetch("/api/orders", {
    method: "POST",
    headers: { ...authorized(token), "Idempotency-Key": idempotencyKey }
  }))).json();
}

export async function fetchOrders(token: string): Promise<OrderSummary[]> {
  const response = await ensureOk(await fetch("/api/orders", { headers: authorized(token) }));
  return (await response.json()).orders;
}

export async function fetchOrderDetail(token: string, orderId: string): Promise<OrderDetail> {
  return (await ensureOk(await fetch(`/api/orders/${encodeURIComponent(orderId)}`, {
    headers: authorized(token)
  }))).json();
}

export async function cancelOrder(token: string, orderId: string): Promise<OrderDetail> {
  return (await ensureOk(await fetch(`/api/orders/${encodeURIComponent(orderId)}/cancel`, {
    method: "POST",
    headers: authorized(token)
  }))).json();
}
```

- [ ] **Step 4: 修正测试中的摘要响应并验证通过**

将 Task 1 的摘要 mock 改为只包含 Java `OrderSummaryView` 支持的字段：

```ts
{ orders: [{
  id: orderDetail.id,
  status: orderDetail.status,
  totalAmount: orderDetail.totalAmount,
  createdAt: orderDetail.createdAt,
  updatedAt: orderDetail.updatedAt
}] }
```

Run: `cd D:\727push\frontend; npm test -- --run src/api/client.test.ts`

Expected: PASS，新增三个订单测试与现有客户端测试全部通过。

- [ ] **Step 5: 提交接口层变更**

```powershell
git add frontend/src/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat: 增加前端订单接口封装"
```

## Task 2: 购物车结算动作

**Files:**
- Modify: `frontend/src/components/CommerceOverlays.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/i18n.ts`

**Interfaces:**
- Consumes: `createOrder(token, idempotencyKey)`、`fetchCart(token)`、`transitionNavigate(path)` 与 `CartItem[]`。
- Produces: `CartDrawer` 的 `onCheckout`、`checkoutBusy` 属性，以及提交后统一的购物车刷新行为。

- [ ] **Step 1: 在端到端测试中先断言结算入口**

在 `frontend/e2e/shopping.spec.ts` 的 `compare, add to Java cart and clear it` 测试中，在购物车商品可见后增加：

```ts
await expect(page.getByRole("button", { name: "提交订单" })).toBeVisible();
```

Run: `cd D:\727push\frontend; npm run test:e2e -- shopping.spec.ts --grep "compare, add"`

Expected: FAIL，找不到“提交订单”按钮。

- [ ] **Step 2: 为购物车抽屉添加结算契约和按钮**

将 `CartProps` 扩展为：

```ts
onCheckout: () => Promise<void>;
checkoutBusy: boolean;
```

将 `CartDrawer` 参数扩展为 `onCheckout, checkoutBusy`，并把 footer 改为：

```tsx
<footer className="cart-footer">
  <div><span>{t("cartTotal")}</span><strong>{total.toFixed(4)}</strong></div>
  <button type="button" className="cart-checkout" disabled={checkoutBusy || cart.length === 0} onClick={() => void onCheckout()}>
    {checkoutBusy ? t("submittingOrder") : t("submitOrder")}
  </button>
  <button type="button" className="cart-clear" disabled={checkoutBusy} onClick={onClear}>{t("clearCart")}</button>
</footer>
```

在 `frontend/src/i18n.ts` 的中英文文案对象中分别新增：

```ts
cartTotal: "合计", submitOrder: "提交订单", submittingOrder: "正在提交订单…",
orderCreated: "订单已创建", orderCreateFailed: "提交订单失败",
```

```ts
cartTotal: "Total", submitOrder: "Place order", submittingOrder: "Placing order…",
orderCreated: "Order created", orderCreateFailed: "Could not place order",
```

- [ ] **Step 3: 在 App 中实现幂等结算和失败保留购物车**

从 `./api/client` 导入 `createOrder`，新增状态：

```ts
const [checkoutBusy, setCheckoutBusy] = useState(false);
```

在 `emptyCart` 后增加：

```ts
const checkout = async () => {
  if (!store.accessToken || store.cart.length === 0 || checkoutBusy) return;
  setCheckoutBusy(true);
  try {
    await createOrder(store.accessToken, `checkout-${createClientId()}`);
    store.setCart(await fetchCart(store.accessToken));
    setCartOpen(false);
    setNotice(t("orderCreated"));
    transitionNavigate("/orders");
  } catch (error) {
    setNotice(error instanceof Error ? error.message : t("orderCreateFailed"));
  } finally {
    setCheckoutBusy(false);
  }
};
```

向 `CartDrawer` 传入 `onCheckout={checkout}` 与 `checkoutBusy={checkoutBusy}`。不要在 catch 中调用 `clearCart` 或修改 `store.cart`。

- [ ] **Step 4: 更新端到端 mock 并验证结算成功路径**

在 `mockApi` 中增加状态和路由：

```ts
let orders = [] as typeof orderDetails;
await page.route("**/api/orders", route => {
  if (route.request().method() === "POST") {
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    javaCart = [];
    orders = [orderDetails];
    return route.fulfill({ json: orderDetails });
  }
  return route.fulfill({ json: { orders: orders.map(({ items, ...summary }) => summary) } });
});
await page.route("**/api/orders/*", route => route.fulfill({ json: orderDetails }));
```

在测试中点击结算并断言跳转：

```ts
await page.getByRole("button", { name: "提交订单" }).click();
await expect(page).toHaveURL(/\/orders$/);
```

Run: `cd D:\727push\frontend; npm run test:e2e -- shopping.spec.ts --grep "compare, add"`

Expected: FAIL，直到 Task 3 添加 `/orders` 页面；此时确认结算请求已被 mock 捕获。

- [ ] **Step 5: 提交结算动作**

```powershell
git add frontend/src/components/CommerceOverlays.tsx frontend/src/App.tsx frontend/src/i18n.ts frontend/e2e/shopping.spec.ts
git commit -m "feat: 支持购物车提交订单"
```

## Task 3: 移动端订单列表、详情快照与取消操作

**Files:**
- Create: `frontend/src/components/OrdersScreen.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ProfileScreen.tsx`
- Modify: `frontend/src/components/MobileShell.tsx`
- Modify: `frontend/src/i18n.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/e2e/shopping.spec.ts`

**Interfaces:**
- Consumes: `fetchOrders(token)`、`fetchOrderDetail(token, id)`、`cancelOrder(token, id)`、`OrderDetail[]`、`transitionNavigate(path)`。
- Produces: `/orders` 路由、`OrdersScreen` 和个人页“订单”入口。

- [ ] **Step 1: 写入订单页端到端断言**

在结算测试的跳转断言后增加：

```ts
await expect(page.getByRole("heading", { name: "我的订单" })).toBeVisible();
await expect(page.getByText("White Office Shirt")).toBeVisible();
await expect(page.getByRole("button", { name: "取消订单" })).toBeVisible();
```

Run: `cd D:\727push\frontend; npm run test:e2e -- shopping.spec.ts --grep "compare, add"`

Expected: FAIL，因为 `/orders` 尚未渲染订单页。

- [ ] **Step 2: 创建只负责展示的 OrdersScreen**

创建 `frontend/src/components/OrdersScreen.tsx`，使用以下组件契约：

```tsx
export function OrdersScreen({
  authenticated, orders, loading, busyOrderId, error, onLogin, onDiscover, onCancel
}: {
  authenticated: boolean;
  orders: OrderDetail[];
  loading: boolean;
  busyOrderId: string | null;
  error: string;
  onLogin: () => void;
  onDiscover: () => void;
  onCancel: (orderId: string) => Promise<void>;
}) {
  // 未登录：显示登录入口；加载中：显示现有 page-loading；空列表：显示发现入口。
  // 每张订单卡显示订单 id、状态、totalAmount、createdAt 和每个 OrderItem 的图片、名称、数量、subtotal。
  // 仅 status === "PENDING_PAYMENT" 时渲染取消按钮，且 busyOrderId === order.id 时禁用并显示处理中。
}
```

格式化金额使用 `amount.toFixed(4)`，格式化时间使用 `new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))`。商品图片为空时渲染无图片占位容器，不使用外部图片。

- [ ] **Step 3: 在 App 中加载详情、取消并注册路由**

从客户端导入 `cancelOrder`、`fetchOrderDetail`、`fetchOrders`，从 types 导入 `OrderDetail`；新增：

```ts
const [orders, setOrders] = useState<OrderDetail[]>([]);
const [ordersLoading, setOrdersLoading] = useState(false);
const [ordersError, setOrdersError] = useState("");
const [cancellingOrderId, setCancellingOrderId] = useState<string | null>(null);

const refreshOrders = async () => {
  if (!store.accessToken) return;
  setOrdersLoading(true); setOrdersError("");
  try {
    const summaries = await fetchOrders(store.accessToken);
    setOrders(await Promise.all(summaries.map((order) => fetchOrderDetail(store.accessToken, order.id))));
  } catch (error) {
    setOrdersError(error instanceof Error ? error.message : t("ordersLoadFailed"));
  } finally {
    setOrdersLoading(false);
  }
};

const cancelExistingOrder = async (orderId: string) => {
  if (!store.accessToken) return;
  setCancellingOrderId(orderId);
  try {
    await cancelOrder(store.accessToken, orderId);
    await refreshOrders();
  } catch (error) {
    setOrdersError(error instanceof Error ? error.message : t("orderCancelFailed"));
  } finally {
    setCancellingOrderId(null);
  }
};
```

在 `pathname === "/orders"` 分支渲染 `OrdersScreen`。当路由变为 `/orders` 且存在 token 时调用 `void refreshOrders()`；不要在每次渲染中调用。将 `/orders` 加入 `rootScreen`，并在个人页传入 `onOrders={() => transitionNavigate("/orders")}`。

- [ ] **Step 4: 添加个人入口、标题、文案与样式**

在 `ProfileScreen` props 中新增 `onOrders: () => void`，在 `profile-list` 顶部增加按钮：

```tsx
<button onClick={user ? onOrders : onAuth}>
  <span><ReceiptText size={17} />{zh ? "我的订单" : "Orders"}</span><ChevronRight size={15} />
</button>
```

从 `lucide-react` 导入 `ReceiptText`。在 `MobileShell.tsx` 的 `titles` 中增加：

```ts
"/orders": ["我的订单", "Orders"]
```

在 `i18n.ts` 的两个语言对象中新增 `orders`、`ordersEmpty`、`ordersEmptyAction`、`orderPendingPayment`、`orderCancelled`、`cancelOrder`、`cancellingOrder`、`ordersLoadFailed`、`orderCancelFailed` 的中英文文案。

在 `styles.css` 追加以 `.orders-screen` 为根的规则：订单列表为单列；订单卡保留现有 `app-card` 的直角/圆角系统；订单商品使用固定 `48px` 图块；金额、状态、取消按钮在窄屏不溢出；`@media (max-width: 560px)` 下保持页面无横向滚动。

- [ ] **Step 5: 完成取消订单 mock 并验证订单闭环**

将 `**/api/orders/*` mock 按请求方法分支：

```ts
if (route.request().method() === "POST" && route.request().url().endsWith("/cancel")) {
  orderDetails = { ...orderDetails, status: "CANCELLED" };
}
return route.fulfill({ json: orderDetails });
```

在测试中增加：

```ts
await page.getByRole("button", { name: "取消订单" }).click();
await expect(page.getByText("已取消")).toBeVisible();
```

Run: `cd D:\727push\frontend; npm run test:e2e -- shopping.spec.ts --grep "compare, add"`

Expected: PASS，覆盖商品加入购物车、结算、订单快照和取消订单。

- [ ] **Step 6: 提交订单页面**

```powershell
git add frontend/src/components/OrdersScreen.tsx frontend/src/App.tsx frontend/src/components/ProfileScreen.tsx frontend/src/components/MobileShell.tsx frontend/src/i18n.ts frontend/src/styles.css frontend/e2e/shopping.spec.ts
git commit -m "feat: 增加移动端订单管理页面"
```

## Task 4: 回归验证与交付说明

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-07-order-checkout-experience.md`

**Interfaces:**
- Consumes: 完成后的前端构建、Vitest、Playwright mock e2e、既有 Java 订单集成测试。
- Produces: 可复现的验收路径和提交前验证证据。

- [ ] **Step 1: 补充 README 的用户闭环说明**

在 `README.md` 的前端或功能说明部分增加一段中文说明：

```md
### 订单结算闭环

登录用户可从商品目录或 Agent 推荐加入购物车，提交订单后在“我的订单”查看商品快照与状态；待支付订单可取消。订单请求由 Java 服务处理，并通过 `Idempotency-Key` 防止重复提交。
```

- [ ] **Step 2: 执行前端单元测试与构建**

Run: `cd D:\727push\frontend; npm test`

Expected: PASS，所有 Vitest 用例通过。

Run: `cd D:\727push\frontend; npm run build`

Expected: PASS，TypeScript 与 Vite 构建完成。

- [ ] **Step 3: 执行模拟端到端回归**

Run: `cd D:\727push\frontend; npm run test:e2e`

Expected: PASS，包含订单结算与取消流程；移动端断言仍无横向溢出。

- [ ] **Step 4: 执行 Java 订单回归**

Run: `cd D:\727push\java-backend; mvn test`

Expected: PASS，既有订单、购物车、鉴权和衣橱集成测试通过。

- [ ] **Step 5: 手工验收与提交**

在本地或 Docker 环境依次验证：

```text
注册/登录 -> 从发现页或 Agent 推荐加入商品 -> 打开购物车 -> 提交订单 -> 进入订单页 -> 取消待支付订单
```

确认请求失败时购物车不消失、双击提交不生成重复订单后执行：

```powershell
git add README.md docs/superpowers/plans/2026-08-07-order-checkout-experience.md
git commit -m "docs: 补充订单结算使用说明"
```

## 自检

- 规格覆盖：Task 1 覆盖 Java 订单 API 与幂等键；Task 2 覆盖结算与失败保留购物车；Task 3 覆盖订单列表、商品快照、取消和个人入口；Task 4 覆盖验证和文档。
- 范围控制：没有新增 Python API、数据库迁移、支付、库存或 Java 订单规则。
- 类型一致：所有 `OrderDetail` 均来自 `fetchOrderDetail`、`createOrder` 或 `cancelOrder`；订单摘要只用于获取详情 ID。
- 无占位项：每个任务给出具体文件、接口、测试命令和提交信息。
