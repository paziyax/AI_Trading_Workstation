"use client";

import { formatPercent, formatPrice, formatQuantity, formatSignedCurrency, trendGlyph, trendOf } from "@/lib/format";
import type { Portfolio } from "@/lib/types";
import { PanelSkeleton } from "./PanelSkeleton";

interface PositionsTableProps {
  portfolio: Portfolio | null;
  loading: boolean;
}

export function PositionsTable({ portfolio, loading }: PositionsTableProps) {
  const positions = portfolio?.positions ?? [];
  const pnl = portfolio?.unrealized_pnl ?? null;
  const pnlTrend = trendOf(pnl);

  const focusTradeBar = () => {
    document.getElementById("trade-ticker")?.focus();
  };

  return (
    <section className="positions-panel" aria-label="Open positions">
      <div className="subpanel-header positions-head">
        <h3 className="panel-label">
          Positions
          {positions.length > 0 ? (
            <span className="count-badge mono" aria-hidden="true">
              {positions.length}
            </span>
          ) : null}
        </h3>
        <span className={`panel-meta mono is-${pnlTrend}`}>
          Unrealized {formatSignedCurrency(pnl)}
        </span>
      </div>

      {loading && !portfolio ? (
        <PanelSkeleton rows={4} label="Loading positions" />
      ) : (
        <div className="positions-scroll">
          <table className="positions-table" data-testid="positions-table">
            <caption className="sr-only">Open positions with live marks and unrealized profit and loss</caption>
            <thead>
              <tr>
                <th scope="col">Ticker</th>
                <th scope="col" className="num">
                  Qty
                </th>
                <th scope="col" className="num col-avg">
                  Avg cost
                </th>
                <th scope="col" className="num">
                  Last
                </th>
                <th scope="col" className="num">
                  Unrealized
                </th>
                <th scope="col" className="num">
                  %
                </th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="positions-empty-cell">
                    <div className="positions-empty">
                      <span className="empty-title">No open positions</span>
                      <span className="empty-body">
                        Use the trade bar to buy your first shares.
                      </span>
                      <button type="button" className="text-button" onClick={focusTradeBar}>
                        Go to trade bar
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                positions.map((position) => {
                  const trend = trendOf(position.unrealized_pnl_pct);
                  return (
                    <tr
                      key={position.ticker}
                      data-testid={`position-row-${position.ticker}`}
                      data-trend={trend}
                    >
                      <th scope="row" className="position-ticker mono">
                        {position.ticker}
                      </th>
                      <td className="num mono">{formatQuantity(position.quantity)}</td>
                      <td className="num mono col-avg">{formatPrice(position.avg_cost)}</td>
                      <td className="num mono">{formatPrice(position.current_price)}</td>
                      <td className={`num mono is-${trend}`}>
                        {trend !== "flat" ? (
                          <span className="trend-glyph" aria-hidden="true">
                            {trendGlyph(trend)}
                          </span>
                        ) : null}
                        {formatSignedCurrency(position.unrealized_pnl)}
                      </td>
                      <td className={`num mono is-${trend}`}>
                        {formatPercent(position.unrealized_pnl_pct)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
