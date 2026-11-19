import { describe, expect, it } from "vitest";
import { heatCellFill, toHeatCells } from "@/lib/heatmap";
import type { Position } from "@/lib/types";

const base: Position = {
  ticker: "AAPL",
  quantity: 10,
  avg_cost: 190,
  current_price: 191,
  market_value: 1910,
  unrealized_pnl: 10,
  unrealized_pnl_pct: 0.5263,
  weight: 19.08,
};

describe("heatmap model", () => {
  it("sizes cells by market value and computes correct weights", () => {
    const cells = toHeatCells([
      { ...base, ticker: "AAPL", market_value: 750, unrealized_pnl_pct: 4, weight: 75 },
      { ...base, ticker: "NVDA", market_value: 250, unrealized_pnl_pct: -2, weight: 25 },
    ]);
    expect(cells).toHaveLength(2);
    expect(cells[0]).toMatchObject({ ticker: "AAPL", value: 750, weight: 75 });
    expect(cells[1]).toMatchObject({ ticker: "NVDA", value: 250, weight: 25 });
  });

  it("maps profit to positive and loss to negative with bounded intensity", () => {
    const [profit, loss, flat] = toHeatCells([
      { ...base, ticker: "AAPL", market_value: 500, unrealized_pnl_pct: 20 },
      { ...base, ticker: "NVDA", market_value: 300, unrealized_pnl_pct: -20 },
      { ...base, ticker: "MSFT", market_value: 200, unrealized_pnl_pct: 0 },
    ]);

    expect(profit.tone).toBe("positive");
    expect(profit.intensity).toBeGreaterThanOrEqual(0.14);
    expect(profit.intensity).toBeLessThanOrEqual(0.5);
    expect(heatCellFill(profit)).toContain("--positive-rgb");

    expect(loss.tone).toBe("negative");
    expect(loss.intensity).toBeLessThanOrEqual(0.5);
    expect(heatCellFill(loss)).toContain("--negative-rgb");

    expect(flat.tone).toBe("neutral");
    expect(heatCellFill(flat)).toContain("--neutral-rgb");
  });

  it("survives a position with a missing mark and an empty portfolio", () => {
    const cells = toHeatCells([
      { ...base, market_value: 0, unrealized_pnl_pct: Number.NaN },
    ]);
    expect(cells[0].value).toBe(0.01);
    expect(cells[0].tone).toBe("neutral");
    expect(toHeatCells([])).toEqual([]);
  });
});
