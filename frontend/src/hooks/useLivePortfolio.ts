"use client";

import { useMemo } from "react";
import { STARTING_CASH } from "@/lib/format";
import type { Portfolio, PriceMap } from "@/lib/types";
import { usePortfolio } from "@/providers/PortfolioProvider";
import { usePrices } from "@/providers/PricesProvider";

/**
 * Overlay the live SSE price map on the last REST portfolio snapshot. The
 * server remains the source of truth for cash and cost basis; only current
 * marks and everything derived from them move on every tick.
 */
export function applyLivePrices(portfolio: Portfolio, prices: PriceMap): Portfolio {
  let positionsValue = 0;

  const marked = portfolio.positions.map((position) => {
    const streamed = prices[position.ticker]?.price;
    const currentPrice =
      typeof streamed === "number" && Number.isFinite(streamed)
        ? streamed
        : position.current_price;
    const marketValue = position.quantity * currentPrice;
    const costBasis = position.quantity * position.avg_cost;
    const unrealizedPnl = marketValue - costBasis;
    const unrealizedPnlPct = costBasis > 0 ? (unrealizedPnl / costBasis) * 100 : 0;
    positionsValue += marketValue;

    return {
      ...position,
      current_price: currentPrice,
      market_value: marketValue,
      unrealized_pnl: unrealizedPnl,
      unrealized_pnl_pct: unrealizedPnlPct,
      weight: 0,
    };
  });

  const totalValue = portfolio.cash_balance + positionsValue;
  const totalPnl = totalValue - STARTING_CASH;
  const unrealizedPnl = marked.reduce((sum, position) => sum + position.unrealized_pnl, 0);

  return {
    ...portfolio,
    positions_value: positionsValue,
    total_value: totalValue,
    total_pnl: totalPnl,
    total_pnl_pct: STARTING_CASH > 0 ? (totalPnl / STARTING_CASH) * 100 : 0,
    unrealized_pnl: unrealizedPnl,
    positions: marked.map((position) => ({
      ...position,
      weight: totalValue > 0 ? (position.market_value / totalValue) * 100 : 0,
    })),
  };
}

export function useLivePortfolio(): Portfolio | null {
  const { portfolio } = usePortfolio();
  const { prices } = usePrices();

  return useMemo(
    () => (portfolio ? applyLivePrices(portfolio, prices) : null),
    [portfolio, prices],
  );
}
