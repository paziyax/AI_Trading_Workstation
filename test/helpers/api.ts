import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** "$10,000.00" (or "−$12.34") -> number. */
export function parseMoney(text: string | null): number {
  if (!text) return Number.NaN;
  const cleaned = text.replace(/[^0-9.-]/g, "");
  return Number(cleaned);
}

/** Current cash balance as rendered in the header, in dollars. */
export async function cashBalance(page: Page): Promise<number> {
  return parseMoney(await page.getByTestId("header-cash").innerText());
}

async function trade(
  request: APIRequestContext,
  side: "buy" | "sell",
  ticker: string,
  quantity: number,
): Promise<void> {
  const response = await request.post("/api/portfolio/trade", {
    data: { ticker, quantity, side },
  });
  expect(
    response.ok(),
    `${side} ${quantity} ${ticker} failed: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
}

export async function buyViaApi(
  request: APIRequestContext,
  ticker: string,
  quantity: number,
): Promise<void> {
  await trade(request, "buy", ticker, quantity);
}

export async function sellViaApi(
  request: APIRequestContext,
  ticker: string,
  quantity: number,
): Promise<void> {
  await trade(request, "sell", ticker, quantity);
}

export async function removeTickerViaApi(
  request: APIRequestContext,
  ticker: string,
): Promise<void> {
  const response = await request.delete(`/api/watchlist/${ticker}`);
  expect([200, 404], `delete ${ticker} returned ${response.status()}`).toContain(
    response.status(),
  );
}
