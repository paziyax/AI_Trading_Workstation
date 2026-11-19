"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  formatAxisTime,
  formatClock,
  formatCompactCurrency,
  formatCurrency,
  formatSignedCurrency,
  STARTING_CASH,
  trendOf,
} from "@/lib/format";
import { useElementSize } from "@/hooks/useElementSize";
import { useLivePortfolio } from "@/hooks/useLivePortfolio";
import { usePortfolio } from "@/providers/PortfolioProvider";
import { InlineError } from "./InlineError";
import { PanelSkeleton } from "./PanelSkeleton";

interface HistoryDatum {
  time: string;
  value: number;
}

function HistoryTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: HistoryDatum; value?: number }>;
}) {
  const datum = payload?.[0]?.payload;
  if (!active || !datum) return null;
  return (
    <div className="chart-tooltip">
      <span className="chart-tooltip-time mono">{formatClock(datum.time)}</span>
      <span className="chart-tooltip-value mono">{formatCurrency(datum.value)}</span>
    </div>
  );
}

export function PnlChart() {
  const { history, historyLoading, historyError, refreshHistory } = usePortfolio();
  const live = useLivePortfolio();
  const { ref, width, height } = useElementSize<HTMLDivElement>();

  const data = useMemo<HistoryDatum[]>(
    () =>
      history.map((point) => ({
        time: point.recordedAt,
        value: point.totalValue,
      })),
    [history],
  );

  const domain = useMemo<[number, number]>(() => {
    if (data.length === 0) return [STARTING_CASH - 50, STARTING_CASH + 50];
    const values = data.map((point) => point.value);
    const low = Math.min(...values, STARTING_CASH);
    const high = Math.max(...values, STARTING_CASH);
    const pad = Math.max((high - low) * 0.15, high * 0.0006, 1);
    return [low - pad, high + pad];
  }, [data]);

  const pnl = live?.total_pnl ?? null;
  const pnlTrend = trendOf(pnl);

  return (
    <section className="subpanel pnl-panel" data-testid="pnl-chart" aria-label="Portfolio value history">
      <div className="subpanel-header">
        <h3 className="panel-label">P&amp;L</h3>
        <span className={`panel-meta mono is-${pnlTrend}`}>{formatSignedCurrency(pnl)}</span>
      </div>
      <div className="pnl-frame" ref={ref}>
        {historyError ? (
          <div className="pnl-message">
            <InlineError
              message={historyError}
              onRetry={() => void refreshHistory()}
              compact
            />
          </div>
        ) : historyLoading && data.length === 0 ? (
          <PanelSkeleton rows={3} label="Loading portfolio history" />
        ) : data.length === 0 ? (
          <div className="pnl-message">
            <p className="empty-body">
              Equity history builds as the session runs. A snapshot is recorded every 30 seconds.
            </p>
          </div>
        ) : width > 0 && height > 0 ? (
          <div
            className="chart-canvas"
            role="img"
            aria-label={`Portfolio value history with ${data.length} snapshots`}
          >
            <LineChart
              width={width}
              height={height}
              data={data}
              margin={{ top: 8, right: 0, bottom: 0, left: 4 }}
            >
              <CartesianGrid stroke="var(--border)" vertical={false} strokeOpacity={0.6} />
              <XAxis
                dataKey="time"
                tickFormatter={(value: string) => formatAxisTime(value)}
                tick={{ fill: "var(--text-secondary)", fontSize: 11, fontFamily: "var(--font-code)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
                minTickGap={30}
                tickMargin={5}
              />
              <YAxis
                orientation="right"
                domain={domain}
                width={62}
                tickFormatter={(value: number) => formatCompactCurrency(value)}
                tick={{ fill: "var(--text-secondary)", fontSize: 11, fontFamily: "var(--font-code)" }}
                tickLine={false}
                axisLine={false}
                tickMargin={5}
                tickCount={4}
              />
              <ReferenceLine y={STARTING_CASH} stroke="var(--border-strong)" strokeDasharray="4 4" />
              <Tooltip
                content={<HistoryTooltip />}
                cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="var(--primary)"
                strokeWidth={1.5}
                isAnimationActive={false}
                dot={
                  data.length === 1
                    ? { r: 3, fill: "var(--primary)", strokeWidth: 0 }
                    : false
                }
                activeDot={{ r: 3, fill: "var(--primary)", stroke: "var(--bg-panel)" }}
              />
            </LineChart>
          </div>
        ) : null}
      </div>
    </section>
  );
}
