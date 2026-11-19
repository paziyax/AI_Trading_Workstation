import { expect, test } from "@playwright/test";

test.describe("terminal shell", () => {
  test("loads seeded data, streams prices and renders the full layout", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await page.goto("/");

    await expect(page.getByTestId("connection-status")).toHaveAttribute(
      "data-state",
      "connected",
    );
    await expect(page.getByTestId("watchlist-panel")).toBeVisible();
    await expect(page.locator("[data-watchlist-row]")).toHaveCount(10);

    await expect(page.getByTestId("header-cash")).toHaveText("$10,000.00");
    await expect(page.getByTestId("header-total-value")).toHaveText("$10,000.00");
    await expect(page.getByTestId("header-pnl")).toContainText("$0.00");

    await expect(page.getByTestId("watchlist-row-AAPL")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("chart-title")).toHaveText("AAPL");
    await expect(page.getByTestId("main-chart")).toBeVisible();
    await expect(page.getByTestId("portfolio-panel")).toBeVisible();
    await expect(page.getByTestId("chat-panel")).toBeVisible();

    // Every seeded ticker has a price, and the stream keeps changing them.
    await expect(page.getByTestId("watchlist-price-AAPL")).toHaveText(
      /^\$[\d,]+\.\d{2}$/,
    );
    const firstPrice = await page.getByTestId("watchlist-price-AAPL").innerText();
    await expect
      .poll(async () => page.getByTestId("watchlist-price-AAPL").innerText(), {
        timeout: 10_000,
        intervals: [100],
      })
      .not.toBe(firstPrice);

    // Flash attribute must fire on an uptick or downtick.
    await expect
      .poll(
        async () => page.getByTestId("watchlist-price-AAPL").getAttribute("data-flash"),
        { timeout: 10_000, intervals: [50] },
      )
      .not.toBe("none");

    expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  });

  test("selecting a ticker moves the main chart", async ({ page }) => {
    await page.goto("/");

    await page.getByTestId("watchlist-row-MSFT").click();

    await expect(page.getByTestId("chart-title")).toHaveText("MSFT");
    await expect(page.getByTestId("watchlist-row-MSFT")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("watchlist-row-AAPL")).toHaveAttribute(
      "aria-selected",
      "false",
    );
    await expect(page.getByTestId("trade-ticker")).toHaveValue("MSFT");
  });
});
