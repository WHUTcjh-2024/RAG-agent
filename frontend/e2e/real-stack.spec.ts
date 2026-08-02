import { expect, test } from "@playwright/test";

test("真实前端、Java 网关与 Python Agent 完成流式推荐", async ({ page }) => {
  const streamStatuses: number[] = [];
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
  await expect(answer).toBeVisible();
  await expect(answer).not.toHaveText("");
  await expect.poll(() => streamStatuses).toEqual([200]);
});
