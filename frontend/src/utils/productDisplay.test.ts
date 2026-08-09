import { describe, expect, it } from "vitest";
import { productDisplayCategory, productDisplayDescription, productDisplayName } from "./productDisplay";

describe("productDisplay", () => {
  it("replaces generated Tianchi labels with concise storefront names", () => {
    expect(productDisplayName({ article_id: "0000000945", prod_name: "天池服装 类目165 商品945" })).toBe("时尚单品 0945");
    expect(productDisplayCategory({ product_type_name: "类目165", product_group_name: "天池服装" })).toBe("精选单品");
  });

  it("keeps a source name when it is already customer-facing", () => {
    expect(productDisplayName({ article_id: "1", prod_name: "White Tianchi Office Shirt" })).toBe("White Tianchi Office Shirt");
  });

  it("does not expose raw reference-id lists as a product description", () => {
    expect(productDisplayDescription("21649,174484,117003,123950,27207")).toBe("暂无商品描述。");
    expect(productDisplayDescription("原始标识为分词 ID 序列: 21649,174484,117003,123950,27207")).toBe("暂无商品描述。");
    expect(productDisplayDescription("原始标题为分词 ID 序列: 21649,174484,117003,123950,27207")).toBe("暂无商品描述。");
  });
});
