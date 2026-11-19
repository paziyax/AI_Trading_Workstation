import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppHeader } from "@/components/AppHeader";
import { applyLivePrices } from "@/hooks/useLivePortfolio";
import { portfolioFixture, installDefaultApi, priceFrame } from "@/test/fixtures";
import { MockEventSource } from "@/test/mockEventSource";
import { PortfolioProvider } from "@/providers/PortfolioProvider";
import { PricesProvider } from "@/providers/PricesProvider";

describe("live portfolio math", () => {
  it("marks positions from SSE and recomputes value, weights and P&L", () => {
    const live = applyLivePrices(portfolioFixture, {
      AAPL: {
        ticker: "AAPL",
        price: 200,
        previous_price: 199,
        timestamp: 1795102698,
        source: "simulator",
      },
    });
    expect(live.positions[0].current_price).toBe(200);
    expect(live.positions[0].market_value).toBe(2000);
    expect(live.positions_value).toBe(2000);
    expect(live.total_value).toBe(10100);
    expect(live.total_pnl).toBe(100);
    expect(live.total_pnl_pct).toBeCloseTo(1, 5);
    expect(live.positions[0].weight).toBeCloseTo((2000 / 10100) * 100, 5);
  });

  it("falls back to the REST mark when no stream price exists", () => {
    const live = applyLivePrices(portfolioFixture, {});
    expect(live.positions[0].current_price).toBe(191);
    expect(live.total_value).toBe(10010);
  });
});

describe("header", () => {
  it("shows live total value, cash, signed P&L and connection state", async () => {
    installDefaultApi();
    render(
      <PricesProvider>
        <PortfolioProvider>
          <AppHeader
            chatOpen={false}
            onToggleChat={() => {}}
            chatToggleRef={{ current: null }}
          />
        </PortfolioProvider>
      </PricesProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,010.00"),
    );
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$8,100.00");
    expect(screen.getByTestId("header-pnl")).toHaveTextContent("+$10.00");

    act(() => MockEventSource.latest!.emitOpen());
    act(() => MockEventSource.latest!.emitFrame(priceFrame));

    expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,020.00");
    expect(screen.getByTestId("header-pnl")).toHaveTextContent("+$20.00");
    expect(screen.getByTestId("header-pnl")).toHaveTextContent("+0.20%");
    expect(screen.getByTestId("connection-status")).toHaveAttribute(
      "data-state",
      "connected",
    );
  });
});
