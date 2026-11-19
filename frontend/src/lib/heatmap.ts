import type { Position } from "./types";

export type HeatTone = "positive" | "negative" | "neutral";

export interface HeatCellModel {
  ticker: string;
  /** Treemap area: market value. */
  value: number;
  /** Share of portfolio in percent. */
  weight: number;
  pnlPct: number;
  pnl: number;
  tone: HeatTone;
  /** 0.12 – 0.5 alpha for the semantic fill. */
  intensity: number;
}

/**
 * Constant floor sizes keep the Treemap stable and readable when a position is
 * worth pennies. Tone is driven by unrealised P&L percent, which is the same
 * signal the positions table shows.
 */
export function toHeatCells(positions: Position[]): HeatCellModel[] {
  const total = positions.reduce((sum, position) => sum + Math.max(position.market_value, 0), 0);

  return positions.map((position) => {
    const pnlPct = Number.isFinite(position.unrealized_pnl_pct)
      ? position.unrealized_pnl_pct
      : 0;
    const tone: HeatTone = pnlPct > 0.005 ? "positive" : pnlPct < -0.005 ? "negative" : "neutral";
    const magnitude = Math.min(Math.abs(pnlPct), 10);
    const intensity = tone === "neutral" ? 0.1 : 0.14 + (magnitude / 10) * 0.36;
    // The API defines weight against total portfolio value (cash included).
    // Recomputing only over positions would inflate every tile.
    const weight =
      Number.isFinite(position.weight) && position.weight >= 0
        ? position.weight
        : total > 0
          ? (Math.max(position.market_value, 0) / total) * 100
          : 0;

    return {
      ticker: position.ticker,
      value: Math.max(position.market_value, 0.01),
      weight,
      pnlPct,
      pnl: position.unrealized_pnl,
      tone,
      intensity: Math.round(intensity * 100) / 100,
    };
  });
}

export function heatCellFill(cell: HeatCellModel): string {
  if (cell.tone === "positive") return `rgb(var(--positive-rgb) / ${cell.intensity})`;
  if (cell.tone === "negative") return `rgb(var(--negative-rgb) / ${cell.intensity})`;
  return `rgb(var(--neutral-rgb) / ${cell.intensity})`;
}

export function heatCellBorder(cell: HeatCellModel): string {
  if (cell.tone === "positive") return "rgb(var(--positive-rgb) / 0.55)";
  if (cell.tone === "negative") return "rgb(var(--negative-rgb) / 0.55)";
  return "var(--border)";
}
