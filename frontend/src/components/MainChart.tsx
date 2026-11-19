"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  formatCompactCurrency,
  formatCurrency,
  formatPercent,
  formatPrice,
  formatTimestamp,
  trendGlyph,
  trendOf,
} from "@/lib/format";
import { useElementSize } from "@/hooks/useElementSize";
import { usePrices } from "@/providers/PricesProvider";
import { useWatchlist } from "@/providers/WatchlistProvider";

interface MainChartProps {
  selectedTicker: string | null;
}

interface ChartDatum {
  timestamp: number;
  price: number;
}

function PriceTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: ChartDatum; value?: number }>;
}) {
  const datum = payload?.[0]?.payload;
  if (!active || !datum) return null;
  return (
    <div className="chart-tooltip">
      <span className="chart-tooltip-time mono">{formatTimestamp(datum.timestamp)}</span>
      <span className="chart-tooltip-value mono">{formatPrice(datum.price)}</span>
    </div>
  );
}

export function MainChart({ selectedTicker }: MainChartProps) {
  const { history, historyTimes, prices } = usePrices();
  const { tickers, loading } = useWatchlist();
  const { ref, width, height } = useElementSize<HTMLDivElement>();

  const entry = selectedTicker
    ? tickers.find((candidate) => candidate.ticker === selectedTicker)
    : undefined;
  const update = selectedTicker ? prices[selectedTicker] : undefined;
  const price = update?.price ?? entry?.price ?? null;
  const samples = selectedTicker ? history[selectedTicker] ?? [] : [];
  const times = selectedTicker ? historyTimes[selectedTicker] ?? [] : [];
  const open = entry?.open_price ?? samples[0] ?? null;
  const change =
    price !== null && open !== null && open !== 0 ? price - open : entry?.change ?? null;
  const changePct =
    price !== null && open !== null && open !== 0
      ? ((price - open) / open) * 100
      : entry?.change_pct ?? null;
  const trend = trendOf(changePct);

  const data = useMemo<ChartDatum[]>(
    () =>
      samples.map((sample, index) => ({
        timestamp: times[index] ?? times[times.length - 1] ?? 0,
        price: sample,
      })),
    [samples, times],
  );

  const domain = useMemo<[number, number]>(() => {
    if (data.length === 0) return [0, 1];
    const values = data.map((datum) => datum.price);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const pad = Math.max((max - min) * 0.12, max * 0.0008, 0.01);
    return [min - pad, max + pad];
  }, [data]);

  const source = update?.source ?? null;

  return (
    <section
      className="panel chart-panel"
      data-testid="main-chart"
      aria-labelledby="chart-title"
    >
      <div className="chart-head">
        <div className="chart-ident">
          <span className="panel-label">Session price</span>
          <h2 className="chart-ticker mono" id="chart-title" data-testid="chart-title">
            {selectedTicker ?? "—"}
          </h2>
        </div>

        <div className="chart-quote">
          <span className="chart-price mono">{formatPrice(price)}</span>
          <span className={`chart-change mono is-${trend}`}>
            {trend !== "flat" ? (
              <span className="trend-glyph" aria-hidden="true">
                {trendGlyph(trend)}
              </span>
            ) : null}
            {formatPercent(changePct)}
          </span>
        </div>
      </div>

      <div className="chart-frame" ref={ref}>
        {loading && !selectedTicker ? (
          <div className="chart-placeholder" role="status" aria-label="Loading chart">
            <span className="skeleton-block chart-skeleton-line" aria-hidden="true" />
          </div>
        ) : !selectedTicker ? (
          <div className="chart-empty">
            <p className="empty-title">Select a ticker</p>
            <p className="empty-body">Choose a row in the watchlist to chart its live price.</p>
          </div>
        ) : data.length === 0 ? (
          <div className="chart-empty">
            <p className="empty-title">Waiting for the first tick</p>
            <p className="empty-body">
              The chart fills from the live stream the moment {selectedTicker} prints.
            </p>
          </div>
        ) : width > 0 && height > 0 ? (
          <div
            className="chart-canvas"
            role="img"
            aria-label={`${selectedTicker} price over the current session, ${samples.length} ticks`}
          >
            <AreaChart
              width={width}
              height={height}
              data={data}
              margin={{ top: 10, right: 0, bottom: 0, left: 4 }}
            >
              <CartesianGrid stroke="var(--border)" vertical={false} strokeOpacity={0.65} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(value: number) => formatTimestamp(value)}
                tick={{ fill: "var(--text-secondary)", fontSize: 11, fontFamily: "var(--font-code)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
                minTickGap={44}
                tickMargin={6}
              />
              <YAxis
                orientation="right"
                domain={domain}
                width={68}
                tickFormatter={(value: number) =>
                  Math.abs(value) >= 10_000
                    ? formatCompactCurrency(value)
                    : formatCurrency(value)
                }
                tick={{ fill: "var(--text-secondary)", fontSize: 11, fontFamily: "var(--font-code)" }}
                tickLine={false}
                axisLine={false}
                tickMargin={6}
                tickCount={5}
              />
              <Tooltip
                content={<PriceTooltip />}
                cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="var(--primary)"
                strokeWidth={1.5}
                fill="var(--primary)"
                fillOpacity={0.08}
                isAnimationActive={false}
                dot={
                  data.length === 1
                    ? { r: 3, fill: "var(--primary)", strokeWidth: 0 }
                    : false
                }
                activeDot={{ r: 3, fill: "var(--primary)", stroke: "var(--bg-panel)" }}
              />
            </AreaChart>
          </div>
        ) : null}
      </div>

      <div className="chart-foot">
        <span className="chart-foot-item">
          {samples.length > 0 ? `${samples.length} ticks` : "No ticks yet"}
        </span>
        <span className="chart-foot-item">
          {source ? `Source: ${source}` : "Live stream"}
        </span>
      </div>
    </section>
  );
}
