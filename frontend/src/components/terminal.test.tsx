import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TerminalShell } from "@/components/TerminalShell";
import { installDefaultApi } from "@/test/fixtures";

describe("terminal shell contract hooks", () => {
  it("mounts every required data-testid at desktop", async () => {
    installDefaultApi();
    render(<TerminalShell />);

    await screen.findByTestId("watchlist-row-AAPL");
    await waitFor(() =>
      expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,010.00"),
    );

    const hooks = [
      "header-total-value",
      "header-cash",
      "header-pnl",
      "connection-status",
      "watchlist-panel",
      "watchlist-row-AAPL",
      "watchlist-price-AAPL",
      "watchlist-change-AAPL",
      "watchlist-sparkline-AAPL",
      "add-ticker-input",
      "add-ticker-submit",
      "remove-ticker-AAPL",
      "main-chart",
      "chart-title",
      "trade-ticker",
      "trade-quantity",
      "trade-buy",
      "trade-sell",
      "portfolio-heatmap",
      "pnl-chart",
      "positions-table",
      "position-row-AAPL",
      "portfolio-panel",
      "chat-panel",
      "chat-input",
      "chat-send",
      "chat-message-assistant",
    ];

    for (const hook of hooks) {
      expect(screen.getByTestId(hook), `missing data-testid="${hook}"`).toBeInTheDocument();
    }

    expect(screen.getByTestId("chart-title")).toHaveTextContent("AAPL");
    expect(screen.getByTestId("connection-status")).toHaveAttribute(
      "data-state",
      "reconnecting",
    );
  });
});
