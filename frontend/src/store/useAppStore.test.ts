import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("useAppStore", () => {
  it("initializes a session when native UUID is unavailable", async () => {
    const localStorage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn()
    };
    vi.stubGlobal("crypto", {});
    vi.stubGlobal("localStorage", localStorage);

    const { useAppStore } = await import("./useAppStore");

    expect(useAppStore.getState().sessionId).toMatch(/^web-[a-z0-9]+-[a-z0-9]+$/);
    expect(localStorage.setItem).toHaveBeenCalledWith(
      "atelier-session",
      expect.stringMatching(/^web-[a-z0-9]+-[a-z0-9]+$/)
    );
  });
});
