import type { Product } from "../types";

const generatedTianchiName = /^天池服装\s+类目\d+\s+商品\d+$/u;
const numericReferenceList = /^(?:\d{2,},){4,}\d{2,}$/u;
const labelledReferenceList = /^原始(?:标题|标识)为分词\s*ID\s*序列[:：](?:\d{2,},){4,}\d{2,}$/u;

export function productDisplayName(product: Pick<Product, "article_id" | "prod_name">): string {
  const name = product.prod_name?.trim();
  if (!name || generatedTianchiName.test(name)) return `时尚单品 ${product.article_id.slice(-4)}`;
  return name;
}

export function productDisplayCategory(product: Pick<Product, "product_type_name" | "product_group_name">): string {
  const category = product.product_type_name || product.product_group_name;
  return category && !/^类目\d+$/u.test(category) ? category : "精选单品";
}

export function productDisplayDescription(description?: string): string {
  const value = description?.trim();
  const compactValue = value?.replaceAll(/\s+/gu, "") || "";
  if (!value || numericReferenceList.test(compactValue) || labelledReferenceList.test(compactValue)) return "暂无商品描述。";
  return value;
}
