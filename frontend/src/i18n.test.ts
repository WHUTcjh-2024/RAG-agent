import { describe, expect, it } from "vitest";
import { chineseCopy } from "./i18n";

describe("Chinese interface copy", () => {
  it("does not contain replacement characters or common UTF-8 mojibake pairs", () => {
    const text = Object.values(chineseCopy).join("\n");
    expect(text).not.toContain("\uFFFD");
    expect(text).not.toMatch(/[\u00C0-\u00F4][\u0080-\u00BF]/);
  });

  it("keeps the primary navigation in Chinese", () => {
    expect(chineseCopy.agent).toBe("图片找同款");
    expect(chineseCopy.discover).toBe("商品");
    expect(chineseCopy.wardrobe).toBe("我的收藏");
  });

  it("does not expose internal product-design jargon in storefront copy", () => {
    const text = Object.values(chineseCopy).join("\n");
    ["实时商品目录", "为当前上下文重新编排", "真实工作流事件", "商品档案", "回到购买决定"].forEach((phrase) => {
      expect(text).not.toContain(phrase);
    });
  });

  it("keeps visible storefront copy in Chinese", () => {
    const visibleText = Object.values(chineseCopy).join("\n").replace(/\{[a-z]+\}/g, "");
    expect(visibleText).not.toMatch(/[A-Za-z]/);
  });
});
