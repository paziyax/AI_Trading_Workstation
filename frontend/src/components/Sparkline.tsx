"use client";

import type { Trend } from "@/lib/format";
import { buildSparkline } from "@/lib/series";

interface SparklineProps {
  ticker: string;
  samples: number[];
  /** Session trend keeps the line colour aligned with the change cell. */
  tone?: Trend;
  width?: number;
  height?: number;
}

/**
 * Hand-drawn SVG sparkline. The element always exists so layout and tests have
 * a stable target; the path appears only once two real samples exist.
 */
export function Sparkline({
  ticker,
  samples,
  tone,
  width = 54,
  height = 22,
}: SparklineProps) {
  const geometry = buildSparkline(samples, width, height, 2);
  const strokeTone = tone ?? geometry?.tone ?? "flat";
  const stroke =
    strokeTone === "up"
      ? "var(--positive)"
      : strokeTone === "down"
        ? "var(--negative)"
        : "var(--neutral)";

  return (
    <svg
      className="sparkline"
      data-testid={`watchlist-sparkline-${ticker}`}
      data-samples={samples.length}
      data-tone={geometry ? strokeTone : "pending"}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="none"
    >
      {geometry ? (
        <polyline
          points={geometry.points}
          fill="none"
          stroke={stroke}
          strokeWidth={1.25}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
    </svg>
  );
}
