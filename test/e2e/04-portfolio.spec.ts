import { expect, test } from "@playwright/test";
import { buyViaApi, cashBalance, sellViaApi } from "../helpers/api";

test.describe("portfolio panel", () => {
  test("renders positions, heatmap and equity curve from live data", async ({
    page,
    request,
  }) => {
    await buyViaApi(request, "MSFT", 3);
    await page.goto("/");

    const position = page.getByTestId("position-row-MSFT");
    await expect(position).toBeVisible();
    await expect(position).toContainText("MSFT");

    // The heatmap excludes cash, so only invested tickers appear in its model.
    await expect(page.getByTestId("portfolio-heatmap")).toContainText("MSFT");

    // The P&L chart needs at least one snapshot; startup and every trade write one.
    await expect(page.getByTestId("pnl-chart").locator("svg").first()).toBeVisible();

    const cash = await cashBalance(page);
    expect(cash).toBeGreaterThan(0);
    expect(cash).toBeLessThan(10_000);

    await expect(page.getByTestId("header-total-value")).not.toHaveText("—");

    await sellViaApi(request, "MSFT", 3);
    await page.reload();
    await expect(page.getByTestId("position-row-MSFT")).toHaveCount(0);
  });
});
