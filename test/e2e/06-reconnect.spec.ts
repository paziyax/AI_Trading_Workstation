import { expect, test } from "@playwright/test";

/**
 * Chromium's offline emulation does not cut an already-open loopback SSE stream,
 * so the drop is simulated by aborting the stream request itself. The app must
 * report the loss, reach its offline state after the ten-second watchdog, and
 * come back to `connected` once the stream is reachable again.
 */
test.describe("connection resilience", () => {
  test("reports a dropped stream and recovers when it returns", async ({ page }) => {
    await page.goto("/");
    const status = page.getByTestId("connection-status");
    await expect(status).toHaveAttribute("data-state", "connected");

    // Reload with the stream blocked: the page starts offline.
    await page.route("**/api/stream/prices", (route) => route.abort("failed"));
    await page.reload();

    await expect
      .poll(async () => status.getAttribute("data-state"), {
        timeout: 15_000,
        intervals: [250],
      })
      .not.toBe("connected");

    // Ten seconds without a frame is reported as disconnected, not "connected".
    await expect(status).toHaveAttribute("data-state", "disconnected", {
      timeout: 25_000,
    });

    // Restore the stream and reload: the terminal is live again.
    await page.unroute("**/api/stream/prices");
    await page.reload();

    await expect(status).toHaveAttribute("data-state", "connected", { timeout: 30_000 });
    await expect(page.getByTestId("watchlist-price-AAPL")).toHaveText(
      /^\$[\d,]+\.\d{2}$/,
    );
  });
});
