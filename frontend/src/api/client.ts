import type { AgentErrorPayload, AuthResult, CartItem, DecisionCard, PendingCartAction, Product, ProductFacets, ProductPage, ProductQuery, Slots, ToolTrace, User, WardrobePlan, WardrobeSnapshot } from "../types";

const REQUEST_ID_HEADER = "X-Request-Id";

const STREAM_EVENT = {
  META: "meta",
  TOOL: "tool",
  PRODUCTS: "products",
  COMPARISON: "comparison",
  MESSAGE: "message",
  ERROR: "error",
  DECISION: "decision",
  CONFIRM_REQUIRED: "confirm_required",
  WARDROBE_PLAN: "wardrobe_plan"
} as const;

export class ApiClientError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly requestId?: string;
  readonly retryable: boolean;

  constructor(
    message: string,
    options: {
      status?: number;
      code?: string;
      requestId?: string;
      retryable?: boolean;
    } = {}
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = options.status || 0;
    this.code = options.code;
    this.requestId = options.requestId;
    this.retryable = options.retryable || false;
  }
}

export const productImage = (product: Product): string => {
  if (product.image_url) return product.image_url;
  const path = (product.image_path || "").replaceAll("\\", "/");
  return path ? `/media/${path.replace(/^images\//, "")}` : "";
};

async function ensureOk(response: Response): Promise<Response> {
  if (response.ok) return response;
  let detail = `请求失败 (${response.status})`;
  let error: AgentErrorPayload | undefined;
  try {
    const payload = await response.json() as {
      detail?: string | { message?: string };
      error?: AgentErrorPayload;
    };
    error = payload.error;
    if (typeof payload.detail === "string") detail = payload.detail;
    else if (payload.detail?.message) detail = payload.detail.message;
    else if (error?.message) detail = error.message;
  } catch {
    // Keep the HTTP fallback message.
  }
  throw new ApiClientError(detail, {
    status: response.status,
    code: error?.code,
    requestId: error?.request_id || response.headers.get(REQUEST_ID_HEADER) || undefined,
    retryable: error?.retryable
  });
}

export function buildProductQuery(query: ProductQuery = {}): string {
  const params = new URLSearchParams({
    page: String(query.page || 1),
    page_size: String(query.pageSize || 12),
    sort: query.sort || "popular"
  });
  if (query.search) params.set("search", query.search);
  if (query.category) params.set("category", query.category);
  if (query.color) params.set("color", query.color);
  if (query.indexGroup) params.set("index_group", query.indexGroup);
  if (typeof query.maxPrice === "number") params.set("max_price", String(query.maxPrice));
  return params.toString();
}

export async function fetchProducts(query: ProductQuery = {}): Promise<ProductPage> {
  const params = buildProductQuery(query);
  const response = await ensureOk(await fetch(`/api/products?${params}`));
  return response.json();
}

export async function fetchProduct(id: string): Promise<Product> {
  return (await ensureOk(await fetch(`/api/products/${encodeURIComponent(id)}`))).json();
}

export async function fetchFacets(): Promise<ProductFacets> {
  return (await ensureOk(await fetch("/api/products/facets"))).json();
}

type StreamHandlers = {
  onMeta: (payload: { request_id?: string; session_id: string; task_id: string; intent: string; slots: Slots }) => void;
  onTaskId?: (taskId: string) => void;
  onTool: (payload: ToolTrace) => void;
  onProducts: (products: Product[]) => void;
  onComparison: (products: Product[]) => void;
  onDecision: (card: DecisionCard) => void;
  onConfirmRequired: (action: PendingCartAction) => void;
  onWardrobePlan: (plan: WardrobePlan) => void;
  onMessage: (delta: string) => void;
  onError: (message: string) => void;
};

export async function streamChat(
  message: string,
  sessionId: string,
  image: File | null,
  language: "zh" | "en",
  handlers: StreamHandlers,
  accessToken = "",
  signal?: AbortSignal
): Promise<void> {
  const form = new FormData();
  form.append("message", message);
  form.append("session_id", sessionId);
  form.append("language", language);
  if (image) form.append("file", image);
  const requestId = crypto.randomUUID();
  const response = await ensureOk(
    await fetch("/api/chat/stream", {
      method: "POST",
      headers: { [REQUEST_ID_HEADER]: requestId, ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
      body: form,
      signal
    })
  );
  const taskId = response.headers.get("X-Agent-Task-Id");
  if (taskId) handlers.onTaskId?.(taskId);
  if (!response.body) throw new Error("浏览器不支持流式响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      let event = "message";
      let data = "{}";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      const payload = JSON.parse(data);
      switch (event) {
        case STREAM_EVENT.META:
          handlers.onMeta(payload);
          break;
        case STREAM_EVENT.TOOL:
          handlers.onTool(payload);
          break;
        case STREAM_EVENT.PRODUCTS:
          handlers.onProducts(payload.items);
          break;
        case STREAM_EVENT.COMPARISON:
          handlers.onComparison(payload.items);
          break;
        case STREAM_EVENT.DECISION:
          handlers.onDecision(payload.card);
          break;
        case STREAM_EVENT.CONFIRM_REQUIRED:
          handlers.onConfirmRequired(payload);
          break;
        case STREAM_EVENT.WARDROBE_PLAN:
          handlers.onWardrobePlan(payload.plan);
          break;
        case STREAM_EVENT.MESSAGE:
          handlers.onMessage(payload.delta || "");
          break;
        case STREAM_EVENT.ERROR:
          handlers.onError(payload.message || "处理失败");
          throw new ApiClientError(payload.message || "处理失败", {
            code: payload.code,
            requestId: payload.request_id || requestId,
            retryable: payload.retryable
          });
        default:
          // Forward compatibility: ignore events introduced by newer backends.
          break;
      }
    }
    if (done) break;
  }
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await ensureOk(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
  );
  return response.json();
}

export const compareProducts = (productIds: string[]) =>
  postJson<{ products: Product[] }>("/api/compare", { product_ids: productIds });

export const fetchSession = (sessionId: string) =>
  postJson<{ session_id: string; slots: Slots; history: { role: "user" | "assistant"; content: string }[] }>("/api/session", {
    session_id: sessionId
  });

export async function cancelAgentTask(token: string, taskId: string, sessionId: string): Promise<boolean> {
  const response = await ensureOk(await fetch(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
    headers: { ...authorized(token), "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  }));
  return (await response.json()).ok === true;
}

function authorized(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export const register = (email: string, password: string, displayName: string) =>
  postJson<AuthResult>("/api/auth/register", { email, password, displayName });

export const login = (email: string, password: string) =>
  postJson<AuthResult>("/api/auth/login", { email, password });

export async function fetchCurrentUser(token: string): Promise<User> {
  return (await ensureOk(await fetch("/api/auth/me", {
    headers: authorized(token)
  }))).json();
}

export async function fetchCart(token: string): Promise<CartItem[]> {
  const response = await ensureOk(await fetch("/api/cart", {
    headers: authorized(token)
  }));
  return (await response.json()).items;
}

export async function addCart(token: string, product: Product): Promise<CartItem> {
  if (typeof product.price !== "number") {
    throw new Error("商品缺少数据价格，暂时无法加入购物袋");
  }
  const response = await ensureOk(await fetch("/api/cart/items", {
    method: "POST",
    headers: { ...authorized(token), "Content-Type": "application/json" },
    body: JSON.stringify({
      productId: product.article_id,
      productName: product.prod_name,
      productImageUrl: productImage(product),
      unitPrice: product.price,
      quantity: 1,
      selected: true
    })
  }));
  return response.json();
}

export async function confirmAgentCartAction(token: string, action: PendingCartAction): Promise<CartItem> {
  const response = await ensureOk(await fetch("/api/cart/agent-actions/confirm", {
    method: "POST",
    headers: { ...authorized(token), "Content-Type": "application/json" },
    body: JSON.stringify({ confirmationToken: action.confirmation_token })
  }));
  return response.json();
}

export async function recordAgentActionCompletion(token: string, actionId: string, cartItemId: string): Promise<void> {
  await ensureOk(await fetch(`/api/actions/${encodeURIComponent(actionId)}/completed`, {
    method: "POST",
    headers: { ...authorized(token), "Content-Type": "application/json" },
    body: JSON.stringify({ cart_item_id: cartItemId })
  }));
}

export async function removeCart(token: string, itemId: string): Promise<void> {
  await ensureOk(await fetch(`/api/cart/items/${encodeURIComponent(itemId)}`, {
    method: "DELETE",
    headers: authorized(token)
  }));
}

export async function clearCart(token: string): Promise<void> {
  await ensureOk(await fetch("/api/cart", {
    method: "DELETE",
    headers: authorized(token)
  }));
}

export async function fetchWardrobe(token: string): Promise<WardrobeSnapshot> {
  return (await ensureOk(await fetch("/api/wardrobe", { headers: authorized(token) }))).json();
}

export async function replanWardrobe(
  token: string,
  taskId: string,
  plan: WardrobePlan,
  operation: Record<string, unknown>
): Promise<WardrobePlan> {
  const response = await ensureOk(await fetch("/api/agent/wardrobe/plans/replan", {
    method: "POST",
    headers: { ...authorized(token), "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, plan, operation })
  }));
  return response.json();
}

export async function recordWardrobeFeedback(
  token: string,
  feedback: { taskId?: string; planRef?: string; itemRef?: string; outcome: "ADOPTED" | "PURCHASED" | "KEPT" | "RETURNED"; fitFeedback?: "TOO_SMALL" | "TOO_LARGE" | "GOOD_FIT" }
): Promise<void> {
  await ensureOk(await fetch("/api/wardrobe/feedback", {
    method: "POST",
    headers: { ...authorized(token), "Content-Type": "application/json" },
    body: JSON.stringify(feedback)
  }));
}
