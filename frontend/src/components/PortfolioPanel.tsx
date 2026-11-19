"use client";

import { useLivePortfolio } from "@/hooks/useLivePortfolio";
import { usePortfolio } from "@/providers/PortfolioProvider";
import { InlineError } from "./InlineError";
import { PnlChart } from "./PnlChart";
import { PortfolioHeatmap } from "./PortfolioHeatmap";
import { PositionsTable } from "./PositionsTable";

export function PortfolioPanel() {
  const { loading, error, refresh } = usePortfolio();
  const live = useLivePortfolio();
  const unavailable = Boolean(error) && !live;

  return (
    <section
      className="panel portfolio-panel"
      data-testid="portfolio-panel"
      aria-label="Portfolio"
    >
      {error ? (
        <div className="panel-banner">
          <InlineError message={error} onRetry={() => void refresh()} compact />
        </div>
      ) : null}

      {unavailable ? (
        <div className="portfolio-unavailable">
          <p className="empty-title">Portfolio unavailable</p>
          <p className="empty-body">
            Allocation and positions will return when the server responds. Retry above.
          </p>
        </div>
      ) : (
        <>
          <div className="portfolio-top">
            <PortfolioHeatmap portfolio={live} loading={loading} />
            <PnlChart />
          </div>

          <PositionsTable portfolio={live} loading={loading} />
        </>
      )}
    </section>
  );
}
