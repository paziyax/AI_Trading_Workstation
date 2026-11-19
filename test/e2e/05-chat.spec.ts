import { expect, test } from "@playwright/test";
import { removeTickerViaApi, sellViaApi } from "../helpers/api";

test.describe("AI chat", () => {
  test("shows the greeting, sends a message and executes a trade", async ({
    page,
    request,
  }) => {
    await page.goto("/");

    await expect(page.getByTestId("chat-message-assistant")).toHaveCount(1);
    await expect(page.getByTestId("chat-message-assistant").first()).toContainText(
      "FinAlly",
    );

    await page.getByTestId("chat-input").fill("buy 1 MSFT");
    await page.getByTestId("chat-send").click();

    await expect(page.getByTestId("chat-message-user")).toHaveCount(1);
    await expect(page.getByTestId("chat-message-assistant")).toHaveCount(2);

    const reply = page.getByTestId("chat-message-assistant").last();
    await expect(reply).toContainText("[mock]");
    await expect(page.getByTestId("chat-actions").last()).toContainText("Bought 1 MSFT");

    // The trade is applied to the rest of the terminal, not just the chat.
    await expect(page.getByTestId("position-row-MSFT")).toBeVisible();

    // Loading state resolves and the composer is usable again.
    await expect(page.getByTestId("chat-loading")).toHaveCount(0);
    await expect(page.getByTestId("chat-input")).toBeEnabled();

    await sellViaApi(request, "MSFT", 1);
  });

  test("adds a ticker through chat and shows the action chip", async ({ page, request }) => {
    await page.goto("/");

    await page.getByTestId("chat-input").fill("add PYPL");
    await page.getByTestId("chat-send").click();

    await expect(page.getByTestId("chat-actions").last()).toContainText("Added PYPL");
    await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();

    await removeTickerViaApi(request, "PYPL");
  });
});
