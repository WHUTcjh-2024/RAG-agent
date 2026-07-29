import { afterEach, describe, expect, it, vi } from "vitest";
import type { Slots, ToolTrace } from "../types";
import { ApiClientError, buildProductQuery, fetchProducts, streamChat } from "./client";

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
    await streamChat("推荐衬衫", "session-1", null, "zh", {
      onMeta,
      onTool: vi.fn<(trace: ToolTrace) => void>(),
      onProducts: vi.fn(),
      onComparison: vi.fn(),
      onMessage,
      onError: vi.fn()
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(onMeta).toHaveBeenCalledOnce();
    expect(onMessage).toHaveBeenCalledWith("推荐结果");
  });
});
