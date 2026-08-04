export interface Product {
  article_id: string;
  prod_name: string;
  product_type_name?: string;
  product_group_name?: string;
  colour_group_name?: string;
  garment_group_name?: string;
  detail_desc?: string;
  image_path?: string;
  image_url?: string;
  price?: number | null;
  price_info?: { amount: number; currency: string; source: string } | null;
  sku?: string;
  available_sizes?: string[];
  inventory_status?: "in_stock" | "out_of_stock" | "unknown";
  popularity_score?: number;
  score?: number;
  reason?: string;
}

export type AgentPhase = "understanding" | "constraints" | "retrieval" | "knowledge" | "tool" | "comparison" | "verification" | "generation" | "waiting" | "success" | "failure" | "cancelled" | "retrying";

export interface AgentNodeEvent {
  id: string;
  node: string;
  phase: AgentPhase;
  state: "started" | "completed" | "failed";
  durationMs?: number;
  summary?: string;
  occurredAt: number;
}

export interface DecisionEvidence {
  source_type: string;
  source_id: string;
  field: string;
  value: string;
  observed_at?: string;
}

export interface DecisionCard {
  decision_id: string;
  verdict: "RECOMMEND_BUY" | "BUY_WITH_CAUTION" | "NOT_RECOMMENDED" | "INSUFFICIENT_DATA";
  confidence: number;
  recommended_size?: string | null;
  reasons: string[];
  evidence: DecisionEvidence[];
  missing_fields: string[];
  alternatives: Product[];
}

export interface Message { id: string; role: "user" | "assistant"; content: string; imagePreview?: string }
export interface User { id: string; email: string; displayName: string; provider: "LOCAL" | "GITHUB" | "WECHAT" | "ALIPAY" }
export interface AuthResult { user: User; accessToken: string }
export interface CartItem { id: string; productId: string; productName: string; productImageUrl?: string | null; unitPrice: number; quantity: number; selected: boolean; createdAt: string; updatedAt: string }
export interface WardrobeItem { id: string; sourceProductId?: string | null; name: string; category: string; color?: string | null; imageUrl?: string | null }
export interface WardrobeSnapshot { version: number; items: WardrobeItem[]; observedAt: string }
export interface PendingCartAction { action_id: string; action_type: "ADD_CART_ITEM"; summary: string; expires_at: string; confirmation_token: string; product: Pick<Product, "article_id" | "prod_name" | "price" | "image_url"> }
export interface WardrobePlanItem { item_id: string; source: "WARDROBE" | "CATALOG"; name: string; category: string; image_url?: string | null; price?: number | null; locked: boolean }
export interface WardrobePlan { plan_id: string; wardrobe_version: number; outfits: { outfit_id: string; name: string; items: WardrobePlanItem[]; complete: boolean }[]; missing_categories: string[]; new_item_total: number; fallback?: string | null }
export type Slots = Record<string, string | number | string[]>;
export interface ToolTrace { tool: string; input: Record<string, unknown>; summary: string }
export interface ProductPage { page: number; page_size: number; total: number; items: Product[] }
export interface ProductFacets { categories: string[]; colors: string[]; index_groups: string[]; price_range: [number, number] | null }
export interface ProductQuery { page?: number; pageSize?: number; search?: string; category?: string; color?: string; indexGroup?: string; maxPrice?: number; sort?: "article_id" | "name" | "popular" }
export interface PickedImage { uri: string; name: string; mimeType: string }
