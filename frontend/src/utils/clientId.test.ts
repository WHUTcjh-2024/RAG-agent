import { afterEach, describe, expect, it, vi } from "vitest";
import { createClientId } from "./clientId";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("createClientId", () => {
  it("uses the native UUID implementation when available", () => {
    const randomUUID = vi.fn(() => "native-id");
    vi.stubGlobal("crypto", { randomUUID });

    expect(createClientId()).toBe("native-id");
    expect(randomUUID).toHaveBeenCalledOnce();
  });

  it("creates a nonempty fallback ID when native UUID is unavailable", () => {
    vi.stubGlobal("crypto", {});
    vi.spyOn(Date, "now").mockReturnValue(1_700_000_000_000);
    vi.spyOn(Math, "random").mockReturnValue(0.5);

    expect(createClientId()).toMatch(/^[a-z0-9]+-[a-z0-9]+$/);
  });
});
