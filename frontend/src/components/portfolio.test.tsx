import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PortfolioPanel } from "@/components/PortfolioPanel";
import {
  emptyPortfolioFixture,
  historyFixture,
  installFetch,
  jsonResponse,
} from "@/test/fixtures";
import { PortfolioProvider } from "@/providers/PortfolioProvider";
import { PricesProvider } from "@/providers/PricesProvider";

describe("portfolio panel", () => {
  it("shows actionable empty states for a fresh account", async () => {
    installFetch((url) => {
      if (url.startsWith("/api/portfolio/history")) return jsonResponse(historyFixture);
      if (url.startsWith("/api/portfolio")) return jsonResponse(emptyPortfolioFixture);
      throw new Error(`Unhandled fetch: ${url}`);
    });

    render(
      <PricesProvider>
        <PortfolioProvider>
          <PortfolioPanel />
        </PortfolioProvider>
      </PricesProvider>,
    );

    expect(await screen.findByText("No open positions")).toBeInTheDocument();
    expect(screen.getByText(/buy your first shares in the trade bar/)).toBeInTheDocument();
    expect(screen.getByTestId("portfolio-panel")).toBeInTheDocument();
    expect(screen.getByTestId("portfolio-heatmap")).toBeInTheDocument();
    expect(screen.getByTestId("pnl-chart")).toBeInTheDocument();
    expect(screen.getByTestId("positions-table")).toBeInTheDocument();
  });
});
