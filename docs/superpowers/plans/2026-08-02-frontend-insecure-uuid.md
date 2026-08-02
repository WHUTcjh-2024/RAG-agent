# Frontend HTTP UUID Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure the frontend starts and can make requests when opened through an HTTP LAN address that does not expose `crypto.randomUUID()`.

**Architecture:** Centralize browser-generated IDs in one small frontend utility. The utility preserves native UUIDs when available and falls back to a non-security client ID when unavailable; all current direct browser UUID calls consume this utility.

**Tech Stack:** React 19, TypeScript, Vite, Vitest.

## Global Constraints

- Do not modify Python RAG source, generated catalog data, or Java services.
- Do not add a runtime dependency.
- The fallback ID is not an authentication, authorization, or security token.
- Preserve native `crypto.randomUUID()` behavior in secure browser contexts.

---

### Task 1: Add a compatible client ID utility

**Files:**
- Create: `frontend/src/utils/clientId.ts`
- Test: `frontend/src/utils/clientId.test.ts`

**Interfaces:**
- Produces: `createClientId(): string`, a client-side nonempty unique identifier.
- Consumes: `globalThis.crypto?.randomUUID`, `Date.now`, and `Math.random`.

- [ ] **Step 1: Write the failing test**

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- src/utils/clientId.test.ts`

Expected: FAIL because `./clientId` does not exist.

- [ ] **Step 3: Write the minimal implementation**

```ts
export function createClientId(): string {
  const randomUUID = globalThis.crypto?.randomUUID;
  if (typeof randomUUID === "function") return randomUUID.call(globalThis.crypto);

  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `npm test -- src/utils/clientId.test.ts`

Expected: PASS with 2 tests.

- [ ] **Step 5: Commit the utility and its regression test**

```bash
git add frontend/src/utils/clientId.ts frontend/src/utils/clientId.test.ts
git commit -m "fix: 兼容 HTTP 环境下的前端 ID 生成"
```

### Task 2: Route all browser ID generation through the utility

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/store/useAppStore.ts`
- Modify Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: `createClientId(): string` from `frontend/src/utils/clientId.ts`.
- Produces: Existing UI session IDs, message IDs, and `X-Request-Id` values without relying on a secure browser context.

- [ ] **Step 1: Write the failing integration test**

Add this test to `frontend/src/api/client.test.ts` and import `createClientId` from `../utils/clientId`:

```ts
it("uses a fallback request ID when the page is served over HTTP", async () => {
  vi.stubGlobal("crypto", {});
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Request-Id"]).toMatch(/^[a-z0-9]+-[a-z0-9]+$/);
    return new Response("", {
      status: 200,
      headers: { "Content-Type": "text/event-stream" }
    });
  }));

  expect(createClientId()).toBeTruthy();
  await streamChat("test", "session-1", null, "zh", {
    onMeta: vi.fn(), onTool: vi.fn(), onProducts: vi.fn(), onComparison: vi.fn(),
    onDecision: vi.fn(), onConfirmRequired: vi.fn(), onWardrobePlan: vi.fn(),
    onMessage: vi.fn(), onError: vi.fn()
  });
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- src/api/client.test.ts`

Expected: FAIL with `TypeError: crypto.randomUUID is not a function` from `streamChat`.

- [ ] **Step 3: Replace direct UUID calls**

Add the relevant relative `createClientId` import to every file below, then replace each `crypto.randomUUID()` expression with `createClientId()`:

```ts
// frontend/src/App.tsx
import { createClientId } from "./utils/clientId";

// frontend/src/api/client.ts
import { createClientId } from "../utils/clientId";

// frontend/src/store/useAppStore.ts
import { createClientId } from "../utils/clientId";
```

Affected behaviors: initial `atelier-session` creation, streamed assistant message IDs, restored session-history IDs, submitted user-message IDs, and `X-Request-Id` for streamed chat requests.

- [ ] **Step 4: Run focused and full frontend tests**

Run: `npm test -- src/api/client.test.ts`

Expected: PASS, including the HTTP fallback request-ID test.

Run: `npm test`

Expected: PASS with all frontend unit tests.

- [ ] **Step 5: Commit the call-site migration**

```bash
git add frontend/src/App.tsx frontend/src/api/client.ts frontend/src/api/client.test.ts frontend/src/store/useAppStore.ts
git commit -m "fix: 避免前端直接依赖 crypto.randomUUID"
```

### Task 3: Verify the production artifact

**Files:**
- Verify only: `frontend/Dockerfile`
- Verify only: `frontend/nginx.conf`

**Interfaces:**
- Consumes: TypeScript source compiled by `npm run build`.
- Produces: Static frontend files that load through Nginx on the HTTP LAN address.

- [ ] **Step 1: Build the production frontend**

Run: `npm run build`

Expected: TypeScript checking and Vite build both finish successfully.

- [ ] **Step 2: Confirm no direct UUID calls remain outside the utility**

Run: `rg -n "crypto\\.randomUUID" src`

Expected: only `frontend/src/utils/clientId.ts` appears.

- [ ] **Step 3: Review the branch state**

Run: `git status --short`

Expected: no uncommitted application changes after the implementation commits.
