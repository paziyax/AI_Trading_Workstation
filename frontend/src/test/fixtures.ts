import { vi } from "vitest";
import type { Portfolio, WatchlistResponse } from "@/lib/types";

export const portfolioFixture: Portfolio = {
  cash_balance: 8100,
  positions_value: 1910,
  total_value: 10010,
  total_pnl: 10,
  total_pnl_pct: 0.1,
  unrealized_pnl: 10,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 190,
      current_price: 191,
      market_value: 1910,
      unrealized_pnl: 10,
      unrealized_pnl_pct: 0.5263,
      weight: 19.08,
    },
  ],
};

export const emptyPortfolioFixture: Portfolio = {
  cash_balance: 10000,
  positions_value: 0,
  total_value: 10000,
  total_pnl: 0,
  total_pnl_pct: 0,
  unrealized_pnl: 0,
  positions: [],
};

export const watchlistFixture: WatchlistResponse = {
  tickers: [
    {
      ticker: "AAPL",
      price: 191,
      previous_price: 190.8,
      change: 1,
      change_pct: 0.5263,
      open_price: 190,
      timestamp: 1795102697.4,
    },
    {
      ticker: "NVDA",
      price: 120,
      previous_price: 120.5,
      change: -1.5,
      change_pct: -1.2345,
      open_price: 121.5,
      timestamp: 1795102697.4,
    },
  ],
};

export const historyFixture = {
  points: [
    { total_value: 10000, recorded_at: "2026-11-19T15:00:00Z" },
    { total_value: 10010, recorded_at: "2026-11-19T15:00:30Z" },
  ],
};

export const priceFrame = {
  AAPL: {
    ticker: "AAPL",
    price: 192,
    previous_price: 191,
    timestamp: 1795102698.4,
    source: "simulator",
  },
  NVDA: {
    ticker: "NVDA",
    price: 119,
    previous_price: 120,
    timestamp: 1795102698.4,
    source: "simulator",
  },
};

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** Route API calls by substring; unmatched URLs reject loudly. */
export function installFetch(handler: Handler) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    return handler(url, init);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

export function installDefaultApi({
  portfolio = portfolioFixture,
  watchlist = watchlistFixture,
}: {
  portfolio?: Portfolio;
  watchlist?: WatchlistResponse;
} = {}) {
  return installFetch((url) => {
    if (url.startsWith("/api/portfolio/history")) return jsonResponse(historyFixture);
    if (url.startsWith("/api/portfolio")) return jsonResponse(portfolio);
    if (url.startsWith("/api/watchlist")) return jsonResponse(watchlist);
    throw new Error(`Unhandled fetch: ${url}`);
  });
}
