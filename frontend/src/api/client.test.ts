import { afterEach, describe, expect, it, vi } from "vitest";
import type { Slots, ToolTrace } from "../types";
import {
  ApiClientError,
  buildProductQuery,
  cancelOrder,
  createOrder,
  fetchOrderDetail,
  fetchOrders,
  fetchProducts,
  phaseForNode,
  streamChat
} from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
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
