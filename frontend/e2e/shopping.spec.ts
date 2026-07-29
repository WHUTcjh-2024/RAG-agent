import { expect, test, type Page } from "@playwright/test";

const products = [
  {
    article_id: "0000000001", sku: "0000000001", prod_name: "White Office Shirt",
    product_type_name: "Shirt", colour_group_name: "White", garment_group_name: "Blouses",
    detail_desc: "Cotton shirt for office wear.", image_url: "/media/one.jpg", price: 0.05,
    price_info: { amount: 0.05, currency: "H&M_DATASET_NORMALIZED", source: "transactions_train.mean" },
    available_sizes: [], inventory_status: "unknown", popularity_score: 1
  },
  {
    article_id: "0000000002", sku: "0000000002", prod_name: "Black Evening Dress",
    product_type_name: "Dress", colour_group_name: "Black", garment_group_name: "Dresses",
    detail_desc: "Simple evening dress.", image_url: "/media/two.jpg", price: 0.08,
    price_info: { amount: 0.08, currency: "H&M_DATASET_NORMALIZED", source: "transactions_train.mean" },
    available_sizes: ["S", "M"], inventory_status: "in_stock", popularity_score: 0.8
  }
];

const user = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "e2e@example.com",
  displayName: "E2E User",
  provider: "LOCAL"
};

const cartItem = {
  id: "00000000-0000-0000-0000-000000000101",
  productId: products[0].article_id,
  productName: products[0].prod_name,
  productImageUrl: products[0].image_url,
  unitPrice: products[0].price,
  quantity: 1,
  selected: true,
  createdAt: "2026-07-29T00:00:00Z",
  updatedAt: "2026-07-29T00:00:00Z"
};

async function mockApi(page: Page, restoredCart: typeof products = []) {
  let javaCart = restoredCart.length ? [cartItem] : [];
  await page.route("**/media/**", route => route.fulfill({
    contentType: "image/svg+xml",
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="40"><rect width="30" height="40" fill="#ddd"/></svg>'
  }));
  await page.route("**/api/products/facets", route => route.fulfill({ json: {
    categories: ["Dress", "Shirt"], colors: ["Black", "White"],
    index_groups: ["Ladieswear"], price_range: [0.05, 0.08]
  }}));
  await page.route("**/api/session", route => route.fulfill({ json: {
    session_id: "e2e", slots: {}, history: []
  }}));
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }));
  await page.route("**/api/cart/items", route => {
    javaCart = [cartItem];
    route.fulfill({ json: cartItem });
  });
  await page.route("**/api/cart/items/*", route => {
    javaCart = [];
    route.fulfill({ status: 204 });
  });
  await page.route("**/api/cart", route => {
    if (route.request().method() === "DELETE") {
      javaCart = [];
      route.fulfill({ status: 204 });
    } else {
      route.fulfill({ json: { items: javaCart } });
    }
  });
  await page.route(/\/api\/products\?.*/, route => route.fulfill({ json: {
    page: Number(new URL(route.request().url()).searchParams.get("page") || 1),
    page_size: 12, total: 24, items: products
  }}));
  await page.route(/\/api\/products\/\d+$/, route => {
    const id = route.request().url().split("/").at(-1);
    route.fulfill({ json: products.find(item => item.article_id === id) });
  });
}

test("browse, filter, paginate and inspect honest commerce fields", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByText("White Office Shirt").first()).toBeVisible();
  await page.getByPlaceholder("搜索商品名称或描述").fill("office");
  await page.getByLabel("分类").selectOption("Shirt");
  await page.getByLabel("颜色").selectOption("White");
  await expect.poll(() => page.url()).toContain("127.0.0.1");
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page.getByText("第 2 / 2 页")).toBeVisible();
  await page.getByRole("button", { name: "查看 White Office Shirt 详情" }).click();
  await expect(page.getByText("商品详情")).toBeVisible();
  await expect(page.getByText(/^0\.050000 H&M_DATASET_NORMALIZED$/)).toBeVisible();
  await expect(page.getByText("数据源未提供").first()).toBeVisible();
});

test("compare, add to Java cart and clear it", async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem("atelier-access-token", "e2e-token"));
  await page.route("**/api/compare", route => route.fulfill({ json: { products } }));
  await page.goto("/");
  await page.getByLabel("加入对比").nth(0).click();
  await page.getByLabel("加入对比").nth(1).click();
  await page.getByRole("button", { name: "开始对比" }).click();
  await expect(page.getByText("单品对比")).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();
  await page.getByLabel("加入购物袋").first().click();
  await page.getByLabel("打开购物袋").click();
  await expect(page.getByText("White Office Shirt").last()).toBeVisible();
  await page.getByRole("button", { name: "清空购物袋" }).click();
  await expect(page.getByText("购物袋还是空的")).toBeVisible();
});

test("restores persisted cart after reload", async ({ page }) => {
  await mockApi(page, [products[0]]);
  await page.addInitScript(() => localStorage.setItem("atelier-access-token", "e2e-token"));
  await page.goto("/");
  await page.getByLabel("打开购物袋").click();
  await expect(page.getByText("White Office Shirt").last()).toBeVisible();
});

test("uploads an image and renders streamed grounded recommendations", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/chat/stream", route => route.fulfill({
    contentType: "text/event-stream",
    body: [
      'event: meta\ndata: {"session_id":"e2e","intent":"hybrid_search","slots":{"color":"White"}}\n\n',
      `event: products\ndata: ${JSON.stringify({ items: [products[0]] })}\n\n`,
      'event: message\ndata: {"delta":"已找到真实目录中的相似商品。"}\n\n',
      'event: done\ndata: {"ok":true}\n\n'
    ].join("")
  }));
  await page.goto("/");
  await page.getByLabel("打开私人顾问").click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "reference.png", mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64")
  });
  await page.getByLabel("导购需求").fill("找白色通勤款");
  await page.getByLabel("发送").click();
  await expect(page.getByText("已找到真实目录中的相似商品。")).toBeVisible();
});

test("switches the complete interface to English and persists the choice", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByLabel("Language").click();
  await expect(page.getByPlaceholder("Search names or descriptions")).toBeVisible();
  await expect(page.getByRole("button", { name: "Consult the stylist" })).toBeVisible();
  await page.reload();
  await expect(page.getByPlaceholder("Search names or descriptions")).toBeVisible();
  await page.getByLabel("Open personal stylist").click();
  await expect(page.getByText("What are you dressing for?")).toBeVisible();
});

test("logs in before using the Java cart", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/auth/login", route => route.fulfill({ json: {
    user,
    accessToken: "e2e-token"
  }}));
  await page.goto("/");
  await page.getByLabel("登录").click();
  await page.getByLabel("邮箱").fill("e2e@example.com");
  await page.getByLabel("密码").fill("password123");
  await page.locator("form").getByRole("button", { name: "登录" }).click();
  await expect(page.getByLabel("退出登录")).toBeVisible();
});
