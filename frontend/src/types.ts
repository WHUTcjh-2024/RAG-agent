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
  text_score?: number;
  image_score?: number;
}

export interface ToolTrace {
  tool: string;
  input: Record<string, unknown>;
  summary: string;
}

export interface AgentErrorPayload {
  request_id: string;
  code: string;
  message: string;
  retryable: boolean;
  stage: string;
  details: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  imagePreview?: string;
}

export interface User {
  id: string;
  email: string;
  displayName: string;
  provider: "LOCAL" | "GITHUB" | "WECHAT" | "ALIPAY";
}

export interface AuthResult {
  user: User;
  accessToken: string;
}

export interface CartItem {
  id: string;
  productId: string;
  productName: string;
  productImageUrl?: string | null;
  unitPrice: number;
  quantity: number;
  selected: boolean;
  createdAt: string;
  updatedAt: string;
}

export type Slots = Record<string, string | number | string[]>;

export interface ProductPage {
  page: number;
  page_size: number;
  total: number;
  items: Product[];
}

export interface ProductFacets {
  categories: string[];
  colors: string[];
  index_groups: string[];
  price_range: [number, number] | null;
}

export interface ProductQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  category?: string;
  color?: string;
  indexGroup?: string;
  maxPrice?: number;
  sort?: "article_id" | "name" | "popular";
}
