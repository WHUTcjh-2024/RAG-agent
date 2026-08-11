import { afterEach, describe, expect, it, vi } from "vitest";
import type { Product, Slots, ToolTrace } from "../types";
import {
  ApiClientError,
  addCart,
  buildProductQuery,
  cancelOrder,
  createVirtualTryOn,
  createOrder,
  deleteVirtualTryOn,
  feedbackVirtualTryOn,
  fetchVirtualTryOn,
  listVirtualTryOns,
  saveVirtualTryOn,
  shareVirtualTryOn,
  updateCartQuantity,
  fetchOrderDetail,
  fetchOrders,
  fetchProducts,
  phaseForNode,
  streamChat
} from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cart APIs", () => {
  it("submits only the product identifier and quantity", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.body).toBe(JSON.stringify({ productId: "prod-1", quantity: 1 }));
      return new Response(JSON.stringify({ id: "cart-item-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await addCart("token-123", {
      article_id: "prod-1",
      prod_name: "Untrusted client name",
      image_url: "https://cdn.example.com/client-image.jpg",
      price: 0.01
    } as Product);

    expect(fetchMock).toHaveBeenCalledWith("/api/cart/items", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ Authorization: "Bearer token-123" })
    }));
  });
});

describe("buildProductQuery", () => {
  it("serializes browsing filters and pagination", () => {
    const query = new URLSearchParams(buildProductQuery({
      page: 3,
      pageSize: 24,
      search: "linen shirt",
      category: "Shirt",
      color: "White",
      indexGroup: "Ladieswear",
      maxPrice: 0.06,
      sort: "name"
    }));
    expect(Object.fromEntries(query)).toEqual({
      page: "3",
      page_size: "24",
      sort: "name",
      search: "linen shirt",
      category: "Shirt",
      color: "White",
      index_group: "Ladieswear",
      max_price: "0.06"
    });
  });

  it("uses stable defaults", () => {
    expect(Object.fromEntries(new URLSearchParams(buildProductQuery()))).toEqual({
      page: "1",
      page_size: "12",
      sort: "popular"
    });
  });

  it("maps backend workflow nodes to stable visual phases", () => {
    expect(phaseForNode("understand_request")).toBe("constraints");
    expect(phaseForNode("retrieve_candidates")).toBe("retrieval");
    expect(phaseForNode("build_evidence")).toBe("verification");
    expect(phaseForNode("complete")).toBe("success");
    expect(phaseForNode("future_node")).toBe("understanding");
  });

  it("dispatches status, node, evidence and completion events", async () => {
    const body = [
      "event: status\ndata: {\"state\":\"processing\",\"request_id\":\"req-1\",\"task_id\":\"task-1\"}",
      "event: node\ndata: {\"node\":\"build_evidence\",\"state\":\"completed\",\"duration_ms\":12.5,\"summary\":\"2 sources\"}",
      "event: evidence\ndata: {\"item\":{\"source_id\":\"catalog:1\",\"source_type\":\"catalog\",\"field\":\"material\",\"value\":\"cotton\"}}",
      "event: done\ndata: {\"ok\":true}",
      ""
    ].join("\n\n");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream", "X-Agent-Task-Id": "task-1" }
    })));
    const onStatus = vi.fn();
    const onNode = vi.fn();
    const onEvidence = vi.fn();
    const onDone = vi.fn();
    const onTaskId = vi.fn();

    await streamChat("推荐棉质衬衫", "session-1", null, "zh", {
      onStatus,
      onNode,
      onEvidence,
      onDone,
      onTaskId,
      onMeta: vi.fn(),
      onTool: vi.fn(),
      onProducts: vi.fn(),
      onComparison: vi.fn(),
      onDecision: vi.fn(),
      onConfirmRequired: vi.fn(),
      onWardrobePlan: vi.fn(),
      onMessage: vi.fn(),
      onError: vi.fn()
    });

    expect(onTaskId).toHaveBeenCalledWith("task-1");
    expect(onStatus).toHaveBeenCalledWith({ state: "processing", requestId: "req-1", taskId: "task-1" });
    expect(onNode).toHaveBeenCalledWith(expect.objectContaining({
      node: "build_evidence", phase: "verification", state: "completed", durationMs: 12.5, summary: "2 sources"
    }));
    expect(onEvidence).toHaveBeenCalledWith(expect.objectContaining({ source_id: "catalog:1", field: "material" }));
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("keeps typed backend errors and request IDs", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      detail: "检索服务暂时不可用",
      error: {
        request_id: "request-error-1",
        code: "RETRIEVAL_UNAVAILABLE",
        message: "检索服务暂时不可用",
        retryable: true,
        stage: "retrieve_candidates",
        details: {}
      }
    }), {
      status: 503,
      headers: {
        "Content-Type": "application/json",
        "X-Request-Id": "request-error-1"
      }
    })));

    const error = await fetchProducts().catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiClientError);
    expect(error).toMatchObject({
      message: "检索服务暂时不可用",
      status: 503,
      code: "RETRIEVAL_UNAVAILABLE",
      requestId: "request-error-1",
      retryable: true
    });
  });

  it("sends a request ID and ignores unknown SSE events", async () => {
    const body = [
      "event: node\ndata: {\"state\":\"started\"}",
      "event: meta\ndata: {\"session_id\":\"session-1\",\"intent\":\"text_recommendation\",\"slots\":{}}",
      "event: decision\ndata: {\"card\":{\"decision_id\":\"decision-1\",\"verdict\":\"RECOMMEND_BUY\",\"confidence\":0.86,\"fit_risks\":[],\"reasons\":[],\"evidence\":[],\"missing_fields\":[],\"alternatives\":[]}}",
      "event: wardrobe_plan\ndata: {\"plan\":{\"plan_id\":\"wardrobe-1\",\"wardrobe_version\":1,\"outfits\":[],\"missing_categories\":[],\"new_item_total\":0}}",
      "event: confirm_required\ndata: {\"action_id\":\"action-1\",\"action_type\":\"ADD_CART_ITEM\",\"summary\":\"加入购物车\",\"expires_at\":\"2026-08-01T00:00:00Z\",\"confirmation_token\":\"token\",\"product\":{\"article_id\":\"1\",\"prod_name\":\"衬衫\",\"price\":10}}",
      "event: message\ndata: {\"delta\":\"推荐结果\"}",
      "event: done\ndata: {\"ok\":true}",
      ""
    ].join("\n\n");
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Request-Id"]).toMatch(/^[0-9a-f-]{36}$/);
      return new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" }
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const onMeta = vi.fn<(payload: { request_id?: string; session_id: string; intent: string; slots: Slots }) => void>();
    const onMessage = vi.fn<(delta: string) => void>();
    const onDecision = vi.fn();
    const onConfirmRequired = vi.fn();
    const onWardrobePlan = vi.fn();
    await streamChat("推荐衬衫", "session-1", null, "zh", {
      onMeta,
      onTool: vi.fn<(trace: ToolTrace) => void>(),
      onProducts: vi.fn(),
      onComparison: vi.fn(),
      onDecision,
      onConfirmRequired,
      onWardrobePlan,
      onMessage,
      onError: vi.fn()
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(onMeta).toHaveBeenCalledOnce();
    expect(onMessage).toHaveBeenCalledWith("推荐结果");
    expect(onDecision).toHaveBeenCalledWith(expect.objectContaining({
      verdict: "RECOMMEND_BUY",
      confidence: 0.86
    }));
    expect(onConfirmRequired).toHaveBeenCalledWith(expect.objectContaining({ action_id: "action-1" }));
    expect(onWardrobePlan).toHaveBeenCalledWith(expect.objectContaining({ plan_id: "wardrobe-1" }));
  });

  it("uses a fallback request ID when the page is served over HTTP", async () => {
    vi.stubGlobal("crypto", {});
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Request-Id"]).toMatch(/^[a-z0-9]+-[a-z0-9]+$/);
      return new Response("", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" }
      });
    }));

    await streamChat("test", "session-1", null, "zh", {
      onMeta: vi.fn(),
      onTool: vi.fn(),
      onProducts: vi.fn(),
      onComparison: vi.fn(),
      onDecision: vi.fn(),
      onConfirmRequired: vi.fn(),
      onWardrobePlan: vi.fn(),
      onMessage: vi.fn(),
      onError: vi.fn()
    });
  });
});

describe("virtual try-on APIs", () => {
  it("submits a synthetic body profile with an idempotency key and polls with authorization", async () => {
    const bodyProfile = {
      height_cm: 168, weight_kg: 58, chest_cm: 88, waist_cm: 70, hip_cm: 94,
      shoulder_cm: 40, inseam_cm: 76, presentation: "NEUTRAL" as const,
      body_shape: "BALANCED" as const, skin_tone: "MEDIUM" as const, fit_preference: "REGULAR" as const
    };
    const job = {
      id: "try-on-1",
      product_id: "product-1",
      category: "dress",
      status: "QUEUED",
      created_at: "2026-08-10T00:00:00Z",
      updated_at: "2026-08-10T00:00:00Z",
      expires_at: "2026-08-11T00:00:00Z",
      retry_after_seconds: 2,
      attempt_count: 0,
      model: { kind: "SYNTHETIC_ADULT", body_profile: bodyProfile, uses_person_photo: false },
      result: null,
      failure: null,
      saved: false,
      feedback: null
    };
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/try-on/jobs") {
        expect(init?.headers).toEqual({ Authorization: "Bearer token-123", "Content-Type": "application/json", "Idempotency-Key": "try-on-key-123" });
        expect(JSON.parse(String(init?.body))).toEqual({ product_id: "product-1", body_profile: bodyProfile });
      } else {
        expect(url).toBe("/api/try-on/jobs/try-on-1");
        expect(init?.headers).toEqual({ Authorization: "Bearer token-123" });
      }
      return new Response(JSON.stringify(job), { status: 202, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(createVirtualTryOn("token-123", "product-1", bodyProfile, "try-on-key-123")).resolves.toEqual(job);
    await expect(fetchVirtualTryOn("token-123", "try-on-1")).resolves.toEqual(job);
  });

  it("supports recent results, save, share, feedback and delete", async () => {
    const job = { id: "try-on-1", status: "SUCCEEDED", saved: false };
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      expect(init?.headers).toMatchObject({ Authorization: "Bearer token-123" });
      if (url === "/api/try-on/jobs?limit=8") return new Response(JSON.stringify({ items: [job] }), { status: 200 });
      if (url.endsWith("/save")) return new Response(JSON.stringify({ ...job, saved: true }), { status: 200 });
      if (url.endsWith("/share")) return new Response(JSON.stringify({ url: "/api/try-on/shared" }), { status: 200 });
      if (url.endsWith("/feedback")) return new Response(JSON.stringify({ ...job, feedback: { rating: 5, issues: [] } }), { status: 200 });
      expect(init?.method).toBe("DELETE");
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(listVirtualTryOns("token-123", 8)).resolves.toEqual([job]);
    await expect(saveVirtualTryOn("token-123", "try-on-1", true)).resolves.toMatchObject({ saved: true });
    await expect(shareVirtualTryOn("token-123", "try-on-1")).resolves.toBe("/api/try-on/shared");
    await expect(feedbackVirtualTryOn("token-123", "try-on-1", { rating: 5, issues: [] })).resolves.toMatchObject({ feedback: { rating: 5, issues: [] } });
    await expect(deleteVirtualTryOn("token-123", "try-on-1")).resolves.toBeUndefined();
  });
});

describe("order APIs", () => {
  it("creates an order with authorization and idempotency headers", async () => {
    const orderDetail = {
      id: "order-1",
      status: "PENDING_PAYMENT",
      totalAmount: 199.5,
      createdAt: "2026-08-07T10:00:00Z",
      updatedAt: "2026-08-07T10:05:00Z",
      items: [
        {
          id: "item-1",
          productId: "prod-1",
          productName: "Linen Shirt",
          productImageUrl: "https://cdn.example.com/shirt.jpg",
          unitPrice: 99.75,
          quantity: 2,
          subtotal: 199.5,
          createdAt: "2026-08-07T10:00:00Z"
        }
      ]
    };

    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init).toMatchObject({
        method: "POST",
        headers: {
          Authorization: "Bearer token-123",
          "Idempotency-Key": "idem-123"
        }
      });
      expect(init?.body).toBeUndefined();
      return new Response(JSON.stringify(orderDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(createOrder("token-123", "idem-123")).resolves.toEqual(orderDetail);
    expect(fetchMock).toHaveBeenCalledWith("/api/orders", expect.any(Object));
  });

  it("parses order summaries from the list response", async () => {
    const orders = [
      {
        id: "order-1",
        status: "PENDING_PAYMENT",
        totalAmount: 120,
        createdAt: "2026-08-07T10:00:00Z",
        updatedAt: "2026-08-07T10:05:00Z"
      },
      {
        id: "order-2",
        status: "CANCELLED",
        totalAmount: 89,
        createdAt: "2026-08-06T10:00:00Z",
        updatedAt: "2026-08-06T11:00:00Z"
      }
    ];

    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.method).toBeUndefined();
      expect(init?.headers).toEqual({ Authorization: "Bearer token-123" });
      return new Response(JSON.stringify({ orders }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchOrders("token-123")).resolves.toEqual(orders);
    expect(fetchMock).toHaveBeenCalledWith("/api/orders", expect.any(Object));
  });

  it("fetches order detail and cancel responses with encoded order ids", async () => {
    const orderDetail = {
      id: "order/needs encoding",
      status: "PENDING_PAYMENT",
      totalAmount: 199.5,
      createdAt: "2026-08-07T10:00:00Z",
      updatedAt: "2026-08-07T10:05:00Z",
      items: []
    };

    const fetchMock = vi
      .fn<(_url: string, init?: RequestInit) => Promise<Response>>()
      .mockImplementationOnce(async (url, init) => {
        expect(url).toBe("/api/orders/order%2Fneeds%20encoding");
        expect(init).toMatchObject({
          headers: { Authorization: "Bearer token-123" }
        });
        return new Response(JSON.stringify(orderDetail), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      })
      .mockImplementationOnce(async (url, init) => {
        expect(url).toBe("/api/orders/order%2Fneeds%20encoding/cancel");
        expect(init).toMatchObject({
          method: "POST",
          headers: { Authorization: "Bearer token-123" }
        });
        expect(init?.body).toBeUndefined();
        return new Response(JSON.stringify({ ...orderDetail, status: "CANCELLED" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchOrderDetail("token-123", "order/needs encoding")).resolves.toEqual(orderDetail);
    await expect(cancelOrder("token-123", "order/needs encoding")).resolves.toEqual({
      ...orderDetail,
      status: "CANCELLED"
    });
  });

  it("keeps ApiClientError typing for order failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      detail: "order invalid",
      error: {
        request_id: "request-order-400",
        code: "ORDER_INVALID",
        message: "order invalid",
        retryable: false,
        stage: "create_order",
        details: {}
      }
    }), {
      status: 400,
      headers: {
        "Content-Type": "application/json",
        "X-Request-Id": "request-order-400"
      }
    })));

    const error = await createOrder("token-123", "idem-123").catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiClientError);
    expect(error).toMatchObject({
      message: "order invalid",
      status: 400,
      code: "ORDER_INVALID",
      requestId: "request-order-400",
      retryable: false
    });
  });
});

describe("cart APIs", () => {
  it("updates a cart item quantity with authorization", async () => {
    const item = {
      id: "item-1",
      productId: "product-1",
      productName: "Linen Shirt",
      productImageUrl: null,
      unitPrice: 99.5,
      quantity: 2,
      selected: true,
      createdAt: "2026-08-10T00:00:00Z",
      updatedAt: "2026-08-10T00:00:01Z"
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

  it("rejects non-integer quantities before calling fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(updateCartQuantity("token-123", "item-1", 0)).rejects.toThrow("购物袋商品数量必须为大于等于 1 的整数");
    await expect(updateCartQuantity("token-123", "item-1", -1)).rejects.toThrow("购物袋商品数量必须为大于等于 1 的整数");
    await expect(updateCartQuantity("token-123", "item-1", 1.5)).rejects.toThrow("购物袋商品数量必须为大于等于 1 的整数");

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
