import { fetch } from "expo/fetch";
import * as Crypto from "expo-crypto";
import type { AgentNodeEvent, AgentPhase, AuthResult, CartItem, DecisionCard, DecisionEvidence, PendingCartAction, PickedImage, Product, ProductFacets, ProductPage, ProductQuery, Slots, ToolTrace, User, WardrobePlan, WardrobeSnapshot } from "@/types";
import { apiUrl, assetUrl } from "@/config/environment";

const REQUEST_ID_HEADER = "X-Request-Id";
const nodePhases: Record<string, AgentPhase> = {
  validate_input: "understanding", understand_request: "constraints", load_context: "knowledge", plan_tools: "tool",
  retrieve_candidates: "retrieval", verify_constraints: "verification", build_evidence: "verification",
  generate_answer: "generation", wait_for_confirmation: "waiting", complete: "success",
};

export class ApiClientError extends Error {
  constructor(message: string, readonly status = 0, readonly retryable = false, readonly requestId?: string) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function ensureOk(response: Response): Promise<Response> {
  if (response.ok) return response;
  let message = `请求失败 (${response.status})`;
  let retryable = response.status >= 500;
  try {
    const payload = await response.json() as { detail?: string | { message?: string }; error?: { message?: string; retryable?: boolean; request_id?: string } };
    message = typeof payload.detail === "string" ? payload.detail : payload.detail?.message || payload.error?.message || message;
    retryable = payload.error?.retryable ?? retryable;
    throw new ApiClientError(message, response.status, retryable, payload.error?.request_id || response.headers.get(REQUEST_ID_HEADER) || undefined);
  } catch (error) {
    if (error instanceof ApiClientError) throw error;
    throw new ApiClientError(message, response.status, retryable, response.headers.get(REQUEST_ID_HEADER) || undefined);
  }
}

function authorized(token: string): Record<string, string> { return { Authorization: `Bearer ${token}` }; }

async function postJson<T>(path: string, body: unknown, token = ""): Promise<T> {
  const response = await ensureOk(await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? authorized(token) : {}) },
    body: JSON.stringify(body),
  }));
  return response.json() as Promise<T>;
}

export function productImage(product: Product): string {
  if (product.image_url) return assetUrl(product.image_url);
  const path = (product.image_path || "").replaceAll("\\", "/").replace(/^images\//, "");
  return path ? apiUrl(`/media/${path}`) : "";
}

export async function fetchProducts(query: ProductQuery = {}): Promise<ProductPage> {
  const params = new URLSearchParams({ page: String(query.page || 1), page_size: String(query.pageSize || 12), sort: query.sort || "popular" });
  if (query.search) params.set("search", query.search);
  if (query.category) params.set("category", query.category);
  if (query.color) params.set("color", query.color);
  if (query.indexGroup) params.set("index_group", query.indexGroup);
  if (typeof query.maxPrice === "number") params.set("max_price", String(query.maxPrice));
  return (await ensureOk(await fetch(apiUrl(`/api/products?${params}`)))).json() as Promise<ProductPage>;
}

export const fetchProduct = async (id: string) => (await ensureOk(await fetch(apiUrl(`/api/products/${encodeURIComponent(id)}`)))).json() as Promise<Product>;
export const fetchFacets = async () => (await ensureOk(await fetch(apiUrl("/api/products/facets")))).json() as Promise<ProductFacets>;
export const compareProducts = (ids: string[]) => postJson<{ products: Product[] }>("/api/compare", { product_ids: ids });
export const fetchSession = (id: string) => postJson<{ session_id: string; slots: Slots; history: { role: "user" | "assistant"; content: string }[] }>("/api/session", { session_id: id });
export const login = (email: string, password: string) => postJson<AuthResult>("/api/auth/login", { email, password });
export const register = (email: string, password: string, displayName: string) => postJson<AuthResult>("/api/auth/register", { email, password, displayName });

export const fetchCurrentUser = async (token: string) => (await ensureOk(await fetch(apiUrl("/api/auth/me"), { headers: authorized(token) }))).json() as Promise<User>;
export async function fetchCart(token: string): Promise<CartItem[]> {
  const payload = await (await ensureOk(await fetch(apiUrl("/api/cart"), { headers: authorized(token) }))).json() as { items: CartItem[] };
  return payload.items;
}
export async function addCart(token: string, product: Product): Promise<CartItem> {
  if (typeof product.price !== "number") throw new ApiClientError("商品缺少数据价格，暂时无法加入购物袋");
  return postJson<CartItem>("/api/cart/items", { productId: product.article_id, productName: product.prod_name, productImageUrl: productImage(product), unitPrice: product.price, quantity: 1, selected: true }, token);
}
export async function removeCart(token: string, id: string): Promise<void> {
  await ensureOk(await fetch(apiUrl(`/api/cart/items/${encodeURIComponent(id)}`), { method: "DELETE", headers: authorized(token) }));
}
export async function clearCart(token: string): Promise<void> {
  await ensureOk(await fetch(apiUrl("/api/cart"), { method: "DELETE", headers: authorized(token) }));
}
export const fetchWardrobe = async (token: string) => (await ensureOk(await fetch(apiUrl("/api/wardrobe"), { headers: authorized(token) }))).json() as Promise<WardrobeSnapshot>;
export const confirmAgentCartAction = (token: string, action: PendingCartAction) => postJson<CartItem>("/api/cart/agent-actions/confirm", { confirmationToken: action.confirmation_token }, token);
export async function cancelAgentTask(token: string, taskId: string, sessionId: string): Promise<void> {
  await postJson(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { session_id: sessionId }, token);
}

export type StreamHandlers = {
  onTaskId?: (id: string) => void;
  onNode?: (event: AgentNodeEvent) => void;
  onMeta?: (slots: Slots) => void;
  onTool?: (trace: ToolTrace) => void;
  onProducts?: (items: Product[]) => void;
  onComparison?: (items: Product[]) => void;
  onEvidence?: (item: DecisionEvidence) => void;
  onDecision?: (card: DecisionCard) => void;
  onConfirm?: (action: PendingCartAction) => void;
  onWardrobePlan?: (plan: WardrobePlan) => void;
  onMessage: (delta: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

export async function streamChat(message: string, sessionId: string, image: PickedImage | null, language: "zh" | "en", handlers: StreamHandlers, token = "", signal?: AbortSignal): Promise<void> {
  const form = new FormData();
  form.append("message", message);
  form.append("session_id", sessionId);
  form.append("language", language);
  if (image) form.append("file", { uri: image.uri, name: image.name, type: image.mimeType } as unknown as Blob);
  const requestId = Crypto.randomUUID();
  const response = await ensureOk(await fetch(apiUrl("/api/chat/stream"), {
    method: "POST",
    headers: { Accept: "text/event-stream", [REQUEST_ID_HEADER]: requestId, ...(token ? authorized(token) : {}) },
    body: form,
    signal,
  }));
  const taskId = response.headers.get("X-Agent-Task-Id");
  if (taskId) handlers.onTaskId?.(taskId);
  if (!response.body) throw new ApiClientError("设备不支持流式响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      let eventName = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      const payload = JSON.parse(data.join("\n"));
      if (eventName === "node") handlers.onNode?.({ id: Crypto.randomUUID(), node: payload.node || "unknown", phase: nodePhases[payload.node] || "understanding", state: payload.state || "started", durationMs: payload.duration_ms, summary: payload.summary, occurredAt: Date.now() });
      else if (eventName === "meta") handlers.onMeta?.(payload.slots || {});
      else if (eventName === "tool") handlers.onTool?.(payload);
      else if (eventName === "products") handlers.onProducts?.(payload.items || []);
      else if (eventName === "comparison") handlers.onComparison?.(payload.items || []);
      else if (eventName === "evidence") handlers.onEvidence?.(payload.item);
      else if (eventName === "decision") handlers.onDecision?.(payload.card);
      else if (eventName === "confirm_required") handlers.onConfirm?.(payload);
      else if (eventName === "wardrobe_plan") handlers.onWardrobePlan?.(payload.plan);
      else if (eventName === "message") handlers.onMessage(payload.delta || "");
      else if (eventName === "done") handlers.onDone?.();
      else if (eventName === "error") { handlers.onError?.(payload.message || "处理失败"); throw new ApiClientError(payload.message || "处理失败", 0, payload.retryable, payload.request_id || requestId); }
    }
    if (done) break;
  }
}
