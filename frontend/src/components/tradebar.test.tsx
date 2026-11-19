import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TradeBar } from "@/components/TradeBar";
import {
  historyFixture,
  installFetch,
  jsonResponse,
  portfolioFixture,
} from "@/test/fixtures";
import { PortfolioProvider, usePortfolio } from "@/providers/PortfolioProvider";
import { PricesProvider } from "@/providers/PricesProvider";
import type { Portfolio } from "@/lib/types";

const tradedPortfolio: Portfolio = {
  ...portfolioFixture,
  cash_balance: 7700,
  total_value: 9610,
  total_pnl: -390,
  total_pnl_pct: -3.9,
};

function CashProbe() {
  const { portfolio } = usePortfolio();
  return <span data-testid="cash-probe">{portfolio?.cash_balance ?? "loading"}</span>;
}

function renderTradeBar() {
  return render(
    <PricesProvider>
      <PortfolioProvider>
        <TradeBar selectedTicker="AAPL" />
        <CashProbe />
      </PortfolioProvider>
    </PricesProvider>,
  );
}

describe("trade bar", () => {
  it("disables while pending, then clears quantity and applies the portfolio", async () => {
    let resolveTrade: ((response: Response) => void) | undefined;
    const pendingTrade = new Promise<Response>((resolve) => {
      resolveTrade = resolve;
    });

    const fetchMock = installFetch((url, init) => {
      if (url === "/api/portfolio/trade" && init?.method === "POST") {
        return pendingTrade;
      }
      if (url.startsWith("/api/portfolio/history")) return jsonResponse(historyFixture);
      if (url.startsWith("/api/portfolio")) return jsonResponse(portfolioFixture);
      throw new Error(`Unhandled fetch: ${url}`);
    });

    renderTradeBar();
    await waitFor(() =>
      expect(screen.getByTestId("cash-probe")).toHaveTextContent("8100"),
    );

    await userEvent.type(screen.getByTestId("trade-quantity"), "2");
    await userEvent.click(screen.getByTestId("trade-buy"));

    await waitFor(() => expect(screen.getByTestId("trade-buy")).toBeDisabled());
    expect(screen.getByTestId("trade-sell")).toBeDisabled();
    expect(screen.getByTestId("trade-ticker")).toBeDisabled();

    await act(async () => {
      resolveTrade?.(
        jsonResponse({
          message: "Bought 2 AAPL at $191.00",
          trade: {
            id: "trade-1",
            ticker: "AAPL",
            side: "buy",
            quantity: 2,
            price: 191,
            executed_at: "2026-11-19T15:38:22Z",
          },
          portfolio: tradedPortfolio,
        }),
      );
    });

    expect(await screen.findByTestId("trade-feedback")).toHaveTextContent(
      "Bought 2 AAPL at $191.00",
    );
    expect(screen.getByTestId("trade-quantity")).toHaveValue("");
    expect(screen.getByTestId("cash-probe")).toHaveTextContent("7700");
    expect(screen.getByTestId("trade-buy")).toBeEnabled();

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[1]?.body).toBe(
      JSON.stringify({ ticker: "AAPL", quantity: 2, side: "buy" }),
    );
  });

  it("shows the backend detail and preserves the form on rejection", async () => {
    installFetch((url, init) => {
      if (url === "/api/portfolio/trade" && init?.method === "POST") {
        return jsonResponse(
          { detail: "Insufficient cash: need $19,100.00, available $8,100.00" },
          400,
        );
      }
      if (url.startsWith("/api/portfolio/history")) return jsonResponse(historyFixture);
      if (url.startsWith("/api/portfolio")) return jsonResponse(portfolioFixture);
      throw new Error(`Unhandled fetch: ${url}`);
    });

    renderTradeBar();
    await waitFor(() =>
      expect(screen.getByTestId("cash-probe")).toHaveTextContent("8100"),
    );

    await userEvent.type(screen.getByTestId("trade-quantity"), "100");
    await userEvent.click(screen.getByTestId("trade-sell"));

    expect(await screen.findByTestId("trade-error")).toHaveTextContent(
      "Insufficient cash: need $19,100.00, available $8,100.00",
    );
    expect(screen.getByTestId("trade-quantity")).toHaveValue("100");
    expect(screen.getByTestId("trade-ticker")).toHaveValue("AAPL");
    expect(screen.getByTestId("trade-sell")).toBeEnabled();
  });

  it("validates the quantity before calling the API", async () => {
    const fetchMock = installFetch((url) => {
      if (url.startsWith("/api/portfolio/history")) return jsonResponse(historyFixture);
      if (url.startsWith("/api/portfolio")) return jsonResponse(portfolioFixture);
      throw new Error(`Unhandled fetch: ${url}`);
    });

    renderTradeBar();
    await waitFor(() =>
      expect(screen.getByTestId("cash-probe")).toHaveTextContent("8100"),
    );

    await userEvent.type(screen.getByTestId("trade-quantity"), "0");
    await userEvent.click(screen.getByTestId("trade-buy"));

    expect(await screen.findByTestId("trade-error")).toHaveTextContent(
      "Quantity must be greater than zero.",
    );
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => url === "/api/portfolio/trade" && init?.method === "POST",
      ),
    ).toBe(false);
  });
});
