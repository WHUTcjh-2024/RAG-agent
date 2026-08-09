import { describe, expect, it } from "vitest";
import { formatCatalogPrice } from "./formatters";

describe("formatCatalogPrice", () => {
  it("renders Tianchi prices as readable RMB amounts", () => {
    expect(formatCatalogPrice(299, "CNY")).toBe("¥299");
    expect(formatCatalogPrice(299.5, "CNY")).toBe("¥299.50");
  });

  it("keeps an explicit non-RMB currency without long floating-point tails", () => {
    expect(formatCatalogPrice(12.3456, "USD")).toBe("12.35 USD");
  });
});
