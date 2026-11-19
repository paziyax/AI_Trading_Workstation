/** Sparkline and sample-history helpers. No synthetic data, ever. */

export const SAMPLE_CAP = 90;

export function appendSample(
  samples: number[] | undefined,
  price: number,
  cap: number = SAMPLE_CAP,
): number[] {
  const next = samples ? [...samples, price] : [price];
  if (next.length <= cap) return next;
  return next.slice(next.length - cap);
}

export interface SparklineGeometry {
  points: string;
  min: number;
  max: number;
  tone: "up" | "down" | "flat";
}

/**
 * Map samples onto an SVG viewBox. Returns null until two samples exist so a
 * single tick cannot masquerade as a trend.
 */
export function buildSparkline(
  samples: number[],
  width = 54,
  height = 22,
  padding = 2,
): SparklineGeometry | null {
  if (samples.length < 2) return null;
  const min = Math.min(...samples);
  const max = Math.max(...samples);
  const span = max - min;
  const innerWidth = Math.max(width - padding * 2, 1);
  const innerHeight = Math.max(height - padding * 2, 1);
  const step = innerWidth / (samples.length - 1);

  const points = samples
    .map((sample, index) => {
      const x = padding + index * step;
      const y =
        span === 0
          ? height / 2
          : padding + innerHeight - ((sample - min) / span) * innerHeight;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const delta = samples[samples.length - 1] - samples[0];
  const tone = Math.abs(delta) < 0.000001 ? "flat" : delta > 0 ? "up" : "down";
  return { points, min, max, tone };
}
