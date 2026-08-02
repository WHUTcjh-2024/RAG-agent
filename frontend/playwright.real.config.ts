import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "real-stack.spec.ts",
  workers: 1,
  timeout: 60_000,
  reporter: "list",
  use: {
    baseURL: process.env.REAL_E2E_BASE_URL || "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
});
