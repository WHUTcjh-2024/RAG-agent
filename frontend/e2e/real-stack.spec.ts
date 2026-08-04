import { expect, test } from "@playwright/test";

test("真实前端、Java 网关与 Python Agent 完成流式推荐", async ({ page }) => {
  test.setTimeout(180_000);
  const streamStatuses: number[] = [];
  const browserDiagnostics: string[] = [];
  page.on("console", message => browserDiagnostics.push(`console:${message.type()}:${message.text()}`));
  page.on("pageerror", error => browserDiagnostics.push(`pageerror:${error.message}`));
  page.on("requestfailed", request => {
    if (request.url().includes("/api/")) {
      browserDiagnostics.push(`requestfailed:${request.method()}:${request.url()}:${request.failure()?.errorText}`);
    }
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/chat/stream")) {
      streamStatuses.push(response.status());
    }
  });

  await page.goto("/");
  await expect(page.getByTestId("open-stylist")).toBeVisible();
  await page.getByTestId("open-stylist").click();
  await page.getByTestId("agent-message").fill("推荐一件红色衬衫");
  await page.getByTestId("agent-message").press("Enter");

  const answer = page.getByTestId("assistant-message").last();
  try {
    await expect(answer).toBeVisible({ timeout: 120_000 });
  } catch (error) {
    console.log(`stream_statuses=${JSON.stringify(streamStatuses)}`);
    console.log(`browser_diagnostics=${JSON.stringify(browserDiagnostics)}`);
    console.log(`page_text=${JSON.stringify(await page.locator("body").innerText())}`);
    throw error;
  }
  await expect(answer).not.toHaveText("");
  await expect.poll(() => streamStatuses).toEqual([200]);
});
