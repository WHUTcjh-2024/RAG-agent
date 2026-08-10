# 购物袋数量控制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让已登录用户可以在购物袋中安全地增减商品数量，并使金额、角标和下单流程与服务器端购物车保持一致。

**Architecture:** 前端 API 客户端新增一个只提交 `quantity` 的 PATCH 函数。`App.tsx` 保存单个购物车项的更新中状态，成功后重新获取完整购物车；`CartDrawer` 只渲染步进器并根据父组件状态禁用交互。Java 既有 JWT 购物车接口不修改。

**Tech Stack:** React 19、TypeScript、Vite、Vitest、Lucide React、Java Spring Boot 现有购物车 API。

## Global Constraints

- 只修改前端购物袋，不修改 Python RAG、推荐、向量索引或数据导入流程。
- 数量最小为 `1`；数量为 `1` 时减号禁用，删除保持独立操作。
- 使用既有 `PATCH /api/cart/items/{itemId}` 和 Bearer Token；请求体仅包含 `quantity`。
- 数量请求未完成时禁用当前商品的加减和移除，并禁用结算及清空购物袋。
- 不新增第三方依赖；使用已有 Lucide 图标和 Vitest。
- 所有新增可见或可访问文案提供中文和英文版本。

---

## 文件结构

- `frontend/src/api/client.ts`：封装购物车项数量 PATCH 请求。
- `frontend/src/api/client.test.ts`：验证 PATCH 路径、认证头、JSON 请求体与响应解析。
- `frontend/src/App.tsx`：管理更新中状态，刷新购物车并将回调传给购物袋组件。
- `frontend/src/components/CommerceOverlays.tsx`：渲染加减图标按钮、数量与禁用状态。
- `frontend/src/i18n.ts`：提供数量控件和更新失败提示的中英文文本。
- `frontend/src/styles.css`：提供不改变现有移动端布局的步进器与移除按钮样式。

### Task 1: 购物车数量 PATCH API

**Files:**
- Modify: `frontend/src/api/client.ts:288-370`
- Modify: `frontend/src/api/client.test.ts:1-15` and append a cart API test suite

**Interfaces:**
- Consumes: `authorized(token): { Authorization: string }`、`ensureOk(response): Promise<Response>`、`CartItem`。
- Produces: `updateCartQuantity(token: string, itemId: string, quantity: number): Promise<CartItem>`。

- [ ] **Step 1: 写入失败测试并导入待实现函数**

在 `frontend/src/api/client.test.ts` 的 client 导入列表中增加 `updateCartQuantity`，并追加：

```ts
describe("cart APIs", () => {
  it("updates a cart item quantity with authorization", async () => {
    const item = {
      id: "item-1", productId: "product-1", productName: "Linen Shirt",
      productImageUrl: null, unitPrice: 99.5, quantity: 2, selected: true,
      createdAt: "2026-08-10T00:00:00Z", updatedAt: "2026-08-10T00:00:01Z"
    };
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/cart/items/item%2Fneeds%20encoding");
      expect(init).toMatchObject({
        method: "PATCH",
        headers: { Authorization: "Bearer token-123", "Content-Type": "application/json" },
        body: JSON.stringify({ quantity: 2 })
      });
      return new Response(JSON.stringify(item), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(updateCartQuantity("token-123", "item/needs encoding", 2)).resolves.toEqual(item);
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: 运行单测，确认失败原因是函数尚未导出**

Run: `cd frontend; npx vitest run src/api/client.test.ts`

Expected: FAIL，提示 `updateCartQuantity` 未从 `./client` 导出或未定义。

- [ ] **Step 3: 以最小实现通过测试**

在 `frontend/src/api/client.ts` 中、`removeCart` 前增加：

```ts
export async function updateCartQuantity(token: string, itemId: string, quantity: number): Promise<CartItem> {
  const response = await ensureOk(await fetch(`/api/cart/items/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    headers: { ...authorized(token), "Content-Type": "application/json" },
    body: JSON.stringify({ quantity })
  }));
  return response.json();
}
```

- [ ] **Step 4: 重新运行定向测试**

Run: `cd frontend; npx vitest run src/api/client.test.ts`

Expected: PASS，新增 `cart APIs > updates a cart item quantity with authorization` 通过。

- [ ] **Step 5: 提交 API 与单测**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat: 增加购物袋数量更新接口"
```

### Task 2: 移动端数量步进器与请求保护

**Files:**
- Modify: `frontend/src/App.tsx:5-30, 56-64, 284-324, 379`
- Modify: `frontend/src/components/CommerceOverlays.tsx:1-63`
- Modify: `frontend/src/i18n.ts:89-94, 160-161`
- Modify: `frontend/src/styles.css:402-412`

**Interfaces:**
- Consumes: `updateCartQuantity(token, itemId, quantity)` from Task 1; `CartItem` values in Zustand store.
- Produces: `CartDrawer` props `onChangeQuantity(id: string, quantity: number): Promise<void>` and `updatingItemId: string | null`.

- [ ] **Step 1: 添加中英文可访问名称与失败提示**

在中文 `cart` 文案附近增加：

```ts
decreaseQuantity: "减少数量",
increaseQuantity: "增加数量",
quantityUpdateFailed: "更新商品数量失败",
```

在英文对应区域增加：

```ts
decreaseQuantity: "Decrease quantity",
increaseQuantity: "Increase quantity",
quantityUpdateFailed: "Could not update item quantity",
```

- [ ] **Step 2: 修改 `CartDrawer` 接口并实现步进器**

从 `lucide-react` 额外导入 `Plus`。将 props 扩展为：

```ts
onChangeQuantity: (id: string, quantity: number) => Promise<void>;
updatingItemId: string | null;
```

在每个商品的价格行后渲染以下结构；`busy` 为 `item.id === updatingItemId`：

```tsx
<div className="cart-item-actions">
  <div className="quantity-stepper" aria-label={t("cart")}>
    <button type="button" aria-label={t("decreaseQuantity")} disabled={busy || item.quantity <= 1}
      onClick={() => void onChangeQuantity(item.id, item.quantity - 1)}>
      <Minus size={12} />
    </button>
    <span aria-live="polite">{item.quantity}</span>
    <button type="button" aria-label={t("increaseQuantity")} disabled={busy}
      onClick={() => void onChangeQuantity(item.id, item.quantity + 1)}>
      <Plus size={12} />
    </button>
  </div>
  <button className="cart-remove" type="button" disabled={busy} onClick={() => onRemove(item.id)}>
    <Minus size={12} />{t("remove")}
  </button>
</div>
```

设定 `const cartBusy = checkoutBusy || updatingItemId !== null;`，用它禁用结算和清空按钮。这样正在更新数量时不会以旧数量下单。

- [ ] **Step 3: 在 `App.tsx` 管理单项更新与完整刷新**

在 `checkoutBusy` 状态后新增：

```ts
const [updatingCartItemId, setUpdatingCartItemId] = useState<string | null>(null);
```

从 `./api/client` 导入 `updateCartQuantity`，并在 `emptyCart` 前增加：

```ts
const changeCartQuantity = async (itemId: string, quantity: number) => {
  if (!store.accessToken || updatingCartItemId) return;
  setUpdatingCartItemId(itemId);
  try {
    await updateCartQuantity(store.accessToken, itemId, quantity);
    store.setCart(await fetchCart(store.accessToken));
  } catch (error) {
    setNotice(error instanceof Error ? error.message : t("quantityUpdateFailed"));
  } finally {
    setUpdatingCartItemId(null);
  }
};
```

同时让 `emptyCart` 与 `checkout` 在 `updatingCartItemId` 存在时直接返回。将 `CartDrawer` 调用改为传入：

```tsx
onChangeQuantity={changeCartQuantity}
updatingItemId={updatingCartItemId}
```

- [ ] **Step 4: 按现有移动端风格补齐局部样式**

替换原来的 `.cart-items button` 通用规则，使用：

```css
.cart-item-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 11px; }
.quantity-stepper { display: inline-grid; grid-template-columns: 24px 26px 24px; align-items: center; min-height: 24px; border: 1px solid var(--line); border-radius: 12px; }
.quantity-stepper button { display: grid; place-items: center; width: 24px; height: 24px; color: var(--ink); }
.quantity-stepper button:disabled { color: var(--muted); opacity: 0.45; }
.quantity-stepper span { text-align: center; font-size: 9px; font-variant-numeric: tabular-nums; }
.cart-remove { display: flex; gap: 5px; align-items: center; color: var(--error); font-size: 7px; }
.cart-remove:disabled { opacity: 0.45; }
```

保留已有 `.cart-items article`、图片、标题和价格样式；不改动页面级布局。

- [ ] **Step 5: 运行完整前端验证**

Run: `cd frontend; npm test; npm run build`

Expected: Vitest 全部通过，TypeScript 编译成功，Vite 输出生产构建产物。

- [ ] **Step 6: 在虚拟机进行回归验收**

在虚拟机已运行的环境中重新构建并启动前端服务，然后以已登录测试账号执行：

1. 加号使数量和总价增加，顶部购物袋角标同步增加。
2. 减号使数量和总价减少；数量为 1 时减号不可点击。
3. 数量请求未完成时，同一商品加减与移除按钮、结算与清空按钮均不可点击。
4. 点击移除仍只移除该商品。
5. 数量变化后创建订单，订单详情中的数量与购物袋最终数量一致。

- [ ] **Step 7: 提交 UI 与状态管理改动**

```bash
git add frontend/src/App.tsx frontend/src/components/CommerceOverlays.tsx frontend/src/i18n.ts frontend/src/styles.css
git commit -m "feat: 支持购物袋商品数量调整"
```

### Task 3: 合并前验证与中文 PR

**Files:**
- Modify: none unless Task 1 或 Task 2 验证发现问题。

**Interfaces:**
- Consumes: Tasks 1-2 的所有提交。
- Produces: 可审查的 `feature/cart-quantity-controls` 分支和中文 PR 描述。

- [ ] **Step 1: 检查工作区与提交差异**

Run: `git status --short; git log --oneline main..HEAD; git diff --check main...HEAD`

Expected: 工作区无未提交文件；只包含设计、API 单测、数量控件、状态管理及样式变更；无空白错误。

- [ ] **Step 2: 再次运行前端自动化验证**

Run: `cd frontend; npm test; npm run build`

Expected: 两条命令均以退出码 0 完成。

- [ ] **Step 3: 创建中文 PR**

PR 标题：`feat: 支持购物袋商品数量调整`

PR 描述：

```markdown
## 修改内容

- 增加购物袋商品数量的加减控件，数量为 1 时禁止继续减少。
- 复用 Java JWT 购物车 PATCH 接口，并在成功后刷新完整购物车。
- 请求期间锁定商品操作、结算和清空，避免旧数量下单。
- 补充数量更新 API 单元测试和中英文可访问文案。

## 验证结果

- `npm test`
- `npm run build`
- 虚拟机已登录场景：加减数量、移除、总价与角标刷新、数量变化后下单。

## 范围说明

- 未修改 Python RAG、推荐、向量索引或数据集导入流程。
```
