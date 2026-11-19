"use client";

import { formatCurrency, formatPercent, formatSignedCurrency, formatUpdateTime, trendGlyph, trendOf } from "@/lib/format";
import { useLivePortfolio } from "@/hooks/useLivePortfolio";
import { usePortfolio } from "@/providers/PortfolioProvider";
import { usePrices } from "@/providers/PricesProvider";
import type { RefObject } from "react";
import { ConnectionStatus } from "./ConnectionStatus";
import { Logo } from "./Logo";

interface AppHeaderProps {
  chatOpen: boolean;
  onToggleChat: () => void;
  chatToggleRef: RefObject<HTMLButtonElement | null>;
}

export function AppHeader({ chatOpen, onToggleChat, chatToggleRef }: AppHeaderProps) {
  const live = useLivePortfolio();
  const { loading } = usePortfolio();
  const { connection, lastUpdatedAt } = usePrices();

  const pnl = live?.total_pnl ?? null;
  const pnlPct = live?.total_pnl_pct ?? null;
  const pnlTrend = trendOf(pnl);
  const busy = loading && !live;

  return (
    <header className="app-header">
      <Logo />
      <span className="paper-chip">Paper</span>

      <div className="header-stats" aria-busy={busy}>
        <div className="header-stat header-stat-total">
          <span className="stat-label">Total value</span>
          <span className="stat-total mono" data-testid="header-total-value">
            {live ? formatCurrency(live.total_value) : "—"}
          </span>
        </div>

        <div className="header-stat">
          <span className="stat-label">Total P&amp;L</span>
          <span
            className={`stat-pnl mono is-${pnlTrend}`}
            data-testid="header-pnl"
            aria-label={
              live
                ? `Total profit and loss ${formatSignedCurrency(pnl)}, ${formatPercent(pnlPct)}`
                : "Total profit and loss unavailable"
            }
          >
            {live ? (
              <>
                {pnlTrend !== "flat" ? (
                  <span className="trend-glyph" aria-hidden="true">
                    {trendGlyph(pnlTrend)}
                  </span>
                ) : null}
                <span>{formatSignedCurrency(pnl)}</span>
                <span className="stat-sub">{formatPercent(pnlPct)}</span>
              </>
            ) : (
              "—"
            )}
          </span>
        </div>

        <div className="header-stat">
          <span className="stat-label">Cash</span>
          <span className="stat-cash mono" data-testid="header-cash">
            {live ? formatCurrency(live.cash_balance) : "—"}
          </span>
        </div>
      </div>

      <div className="header-right">
        {lastUpdatedAt ? (
          <span className="header-tick mono" title="Last streamed tick">
            {formatUpdateTime(lastUpdatedAt)}
          </span>
        ) : null}
        <ConnectionStatus state={connection} />
        <button
          type="button"
          ref={chatToggleRef}
          className="chat-toggle"
          aria-expanded={chatOpen}
          aria-controls="chat-panel"
          onClick={onToggleChat}
          data-testid="chat-toggle"
        >
          AI assistant
        </button>
      </div>
    </header>
  );
}
