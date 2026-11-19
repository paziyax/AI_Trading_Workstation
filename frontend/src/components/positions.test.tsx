import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PositionsTable } from "@/components/PositionsTable";
import { emptyPortfolioFixture, portfolioFixture } from "@/test/fixtures";

describe("positions table", () => {
  it("renders one row per position with signed, formatted values", () => {
    render(<PositionsTable portfolio={portfolioFixture} loading={false} />);

    expect(screen.getByTestId("positions-table")).toBeInTheDocument();
    const row = screen.getByTestId("position-row-AAPL");
    expect(row).toHaveTextContent("AAPL");
    expect(row).toHaveTextContent("10");
    expect(row).toHaveTextContent("$190.00");
    expect(row).toHaveTextContent("$191.00");
    expect(row).toHaveTextContent("+$10.00");
    expect(row).toHaveTextContent("+0.53%");
    expect(row).toHaveAttribute("data-trend", "up");
  });

  it("shows an actionable empty state inside the real table", () => {
    render(<PositionsTable portfolio={emptyPortfolioFixture} loading={false} />);
    expect(screen.getByTestId("positions-table")).toBeInTheDocument();
    expect(screen.getByText("No open positions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to trade bar" })).toBeInTheDocument();
  });

  it("renders a loading state before the first portfolio arrives", () => {
    render(<PositionsTable portfolio={null} loading={true} />);
    expect(screen.getByRole("status", { name: "Loading positions" })).toBeInTheDocument();
    expect(screen.queryByTestId("positions-table")).not.toBeInTheDocument();
  });
});
