"use client";

import { useMemo } from "react";
import { Treemap } from "recharts";
import { formatPercent, formatWeight } from "@/lib/format";
import { heatCellBorder, heatCellFill, toHeatCells, type HeatCellModel } from "@/lib/heatmap";
import { useElementSize } from "@/hooks/useElementSize";
import type { Portfolio } from "@/lib/types";

interface HeatNodeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  depth?: number;
}

function HeatCellContent({
  models,
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  name,
}: HeatNodeProps & { models: Map<string, HeatCellModel> }) {
  const model = name ? models.get(name) : undefined;
  if (!model || width <= 0 || height <= 0) return null;

  const showTicker = width >= 52 && height >= 22;
  const showWeight = width >= 60 && height >= 42;
  const showPnl = width >= 72 && height >= 58;
  const textColor = model.tone === "neutral" ? "var(--text-primary)" : "var(--text-primary)";

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={2}
        fill={heatCellFill(model)}
        stroke={heatCellBorder(model)}
        strokeWidth={1}
      />
      <title>
        {`${model.ticker}: ${formatWeight(model.weight)} of portfolio, ${
          model.pnlPct >= 0 ? "up" : "down"
        } ${formatPercent(model.pnlPct)}`}
      </title>
      {showTicker ? (
        <text
          x={x + 8}
          y={y + 17}
          fill={textColor}
          fontFamily="var(--font-code)"
          fontSize={11}
          fontWeight={600}
          letterSpacing="0.04em"
        >
          {model.ticker}
        </text>
      ) : null}
      {showWeight ? (
        <text
          x={x + 8}
          y={y + 31}
          fill="var(--text-secondary)"
          fontFamily="var(--font-code)"
          fontSize={11}
        >
          {formatWeight(model.weight)}
        </text>
      ) : null}
      {showPnl ? (
        <text
          x={x + 8}
          y={y + 45}
          fill="var(--text-primary)"
          fontFamily="var(--font-code)"
          fontSize={11}
        >
          {formatPercent(model.pnlPct)}
        </text>
      ) : null}
    </g>
  );
}

interface PortfolioHeatmapProps {
  portfolio: Portfolio | null;
  loading: boolean;
}

export function PortfolioHeatmap({ portfolio, loading }: PortfolioHeatmapProps) {
  const { ref, width, height } = useElementSize<HTMLDivElement>();
  const cells = useMemo(
    () => (portfolio ? toHeatCells(portfolio.positions) : []),
    [portfolio],
  );
  const models = useMemo(
    () => new Map(cells.map((cell) => [cell.ticker, cell])),
    [cells],
  );
  const data = useMemo(
    () => cells.map((cell) => ({ name: cell.ticker, size: cell.value })),
    [cells],
  );

  const hasPositions = cells.length > 0;

  return (
    <section
      className="subpanel heatmap-panel"
      data-testid="portfolio-heatmap"
      aria-label="Portfolio allocation heatmap"
    >
      <div className="subpanel-header">
        <h3 className="panel-label">Allocation</h3>
        <span className="panel-meta">Weight, P&amp;L</span>
      </div>
      <div className="heatmap-frame" ref={ref}>
        {loading && !portfolio ? (
          <div className="heatmap-skeleton" role="status" aria-label="Loading allocation">
            <span className="heatmap-skeleton-cell" />
            <span className="heatmap-skeleton-cell" />
            <span className="heatmap-skeleton-cell" />
          </div>
        ) : !hasPositions ? (
          <div className="heatmap-empty">
            <p className="empty-body">
              No positions yet — buy your first shares in the trade bar and the heatmap fills here.
            </p>
          </div>
        ) : width > 0 && height > 0 ? (
          <Treemap
            width={width}
            height={height}
            data={data}
            dataKey="size"
            nameKey="name"
            aspectRatio={1.45}
            nodeGap={2}
            isAnimationActive={false}
            content={<HeatCellContent models={models} />}
          />
        ) : null}
        {hasPositions ? (
          <ul className="sr-only">
            {cells.map((cell) => (
              <li key={cell.ticker}>
                {cell.ticker}: {formatWeight(cell.weight)} of portfolio, P&amp;L{" "}
                {formatPercent(cell.pnlPct)}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
