import { expect, test } from "@playwright/test";
import { cashBalance } from "../helpers/api";

test.describe("trading", () => {
  test("buys and sells a position and updates cash", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("header-cash")).toContainText("$");

    const before = await cashBalance(page);

    await page.getByTestId("trade-ticker").fill("AAPL");
    await page.getByTestId("trade-quantity").fill("2");
    await page.getByTestId("trade-buy").click();

    await expect(page.getByTestId("trade-feedback")).toContainText("Bought 2 AAPL");
    await expect(page.getByTestId("position-row-AAPL")).toBeVisible();
    await expect(page.getByTestId("position-row-AAPL")).toContainText("AAPL");

    await expect.poll(async () => cashBalance(page)).toBeLessThan(before);
    const afterBuy = await cashBalance(page);

    // Sell the same quantity back; the position disappears and cash returns.
    await page.getByTestId("trade-quantity").fill("2");
    await page.getByTestId("trade-sell").click();

    await expect(page.getByTestId("trade-feedback")).toContainText("Sold 2 AAPL");
    await expect(page.getByTestId("position-row-AAPL")).toHaveCount(0);
    await expect.poll(async () => cashBalance(page)).toBeGreaterThan(afterBuy);
  });

  test("rejects a buy that exceeds available cash", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("header-cash")).toContainText("$");

    await page.getByTestId("trade-ticker").fill("AAPL");
    await page.getByTestId("trade-quantity").fill("100000");
    await page.getByTestId("trade-buy").click();

    await expect(page.getByTestId("trade-error")).toContainText("Insufficient cash");
    await expect(page.getByTestId("trade-feedback")).toHaveCount(0);
    await expect(page.getByTestId("trade-quantity")).toHaveValue("100000");
  });

  test("rejects an invalid quantity client-side", async ({ page }) => {
    await page.goto("/");

    await page.getByTestId("trade-ticker").fill("AAPL");
    await page.getByTestId("trade-quantity").fill("0");
    await page.getByTestId("trade-buy").click();

    await expect(page.getByTestId("trade-error")).toContainText(
      "Quantity must be greater than zero",
    );
  });
});
