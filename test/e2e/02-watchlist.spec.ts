import { expect, test } from "@playwright/test";

test.describe("watchlist", () => {
  test("adds, rejects a duplicate and removes a ticker", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-watchlist-row]")).toHaveCount(10);

    await page.getByTestId("add-ticker-input").fill("pypl");
    await page.getByTestId("add-ticker-submit").click();

    await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();
    await expect(page.locator("[data-watchlist-row]")).toHaveCount(11);

    // A ticker already on the list is rejected with the API message.
    await page.getByTestId("add-ticker-input").fill("AAPL");
    await page.getByTestId("add-ticker-submit").click();
    await expect(page.getByText("AAPL is already in the watchlist")).toBeVisible();
    await expect(page.locator("[data-watchlist-row]")).toHaveCount(11);

    // Removal is a single click, no confirmation dialog.
    await page.getByTestId("watchlist-row-PYPL").hover();
    await page.getByTestId("remove-ticker-PYPL").click();

    await expect(page.getByTestId("watchlist-row-PYPL")).toHaveCount(0);
    await expect(page.locator("[data-watchlist-row]")).toHaveCount(10);
  });

  test("rejects a malformed ticker before calling the API", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-watchlist-row]")).toHaveCount(10);

    await page.getByTestId("add-ticker-input").fill("1ABC");
    await page.getByTestId("add-ticker-submit").click();

    await expect(page.getByText(/Use 1.+10 letters/)).toBeVisible();
    await expect(page.locator("[data-watchlist-row]")).toHaveCount(10);
  });
});
