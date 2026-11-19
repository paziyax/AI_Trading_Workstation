/** Number, currency and time formatting shared by every surface. */

export const STARTING_CASH = 10_000;
export const DASH = "—";
export const MINUS = "\u2212";

function isRenderable(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Two-decimal money with thousands separators. */
export function formatCurrency(
  value: number | null | undefined,
  options: { dash?: string } = {},
): string {
  if (!isRenderable(value)) return options.dash ?? DASH;
  const rounded = Math.round((value + Number.EPSILON) * 100) / 100;
  const absolute = Math.abs(rounded).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${rounded < 0 ? MINUS : ""}$${absolute}`;
}

/** Money that always carries a + / − sign, for P&L. */
export function formatSignedCurrency(
  value: number | null | undefined,
  options: { dash?: string } = {},
): string {
  if (!isRenderable(value)) return options.dash ?? DASH;
  const rounded = Math.round((value + Number.EPSILON) * 100) / 100;
  if (rounded === 0) return "$0.00";
  const absolute = Math.abs(rounded).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${rounded > 0 ? "+" : MINUS}$${absolute}`;
}

/** Percent input is in percent units (0.53 → +0.53%). */
export function formatPercent(
  value: number | null | undefined,
  options: { dash?: string; digits?: number } = {},
): string {
  if (!isRenderable(value)) return options.dash ?? DASH;
  const digits = options.digits ?? 2;
  const factor = 10 ** digits;
  const rounded = Math.round((value + Number.EPSILON) * factor) / factor;
  if (rounded === 0) return `${(0).toFixed(digits)}%`;
  return `${rounded > 0 ? "+" : MINUS}${Math.abs(rounded).toFixed(digits)}%`;
}

/** Weight is unsigned: 19.1%. */
export function formatWeight(
  value: number | null | undefined,
  options: { dash?: string; digits?: number } = {},
): string {
  if (!isRenderable(value)) return options.dash ?? DASH;
  const digits = options.digits ?? 1;
  return `${value.toFixed(digits)}%`;
}

/** Shares: up to four decimals, trailing zeros trimmed, thousands separated. */
export function formatQuantity(value: number | null | undefined): string {
  if (!isRenderable(value)) return DASH;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
    useGrouping: true,
  });
}

export function formatPrice(value: number | null | undefined): string {
  return formatCurrency(value);
}

/**
 * Axis money without cents: precise enough that adjacent equity ticks do not
 * collapse to the same label ($10,034 vs $10,049).
 */
export function formatCompactCurrency(value: number): string {
  if (!Number.isFinite(value)) return DASH;
  const absolute = Math.abs(value);
  const sign = value < 0 ? MINUS : "";
  if (absolute >= 1_000_000) return `${sign}$${(absolute / 1_000_000).toFixed(2)}m`;
  if (absolute >= 1_000) return `${sign}$${Math.round(absolute).toLocaleString("en-US")}`;
  return `${sign}$${absolute.toFixed(0)}`;
}

export type Trend = "up" | "down" | "flat";

export function trendOf(value: number | null | undefined, epsilon = 0.000001): Trend {
  if (!isRenderable(value) || Math.abs(value) < epsilon) return "flat";
  return value > 0 ? "up" : "down";
}

export function trendGlyph(trend: Trend): string {
  if (trend === "up") return "▲";
  if (trend === "down") return "▼";
  return "";
}

const timeFormatter = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const axisFormatter = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Unix seconds → local HH:mm:ss. */
export function formatTimestamp(seconds: number | null | undefined): string {
  if (!isRenderable(seconds)) return DASH;
  return timeFormatter.format(new Date(seconds * 1000));
}

/** ISO-8601 string → local HH:mm:ss. */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return timeFormatter.format(date);
}

/** ISO-8601 string → local HH:mm for chart axes. */
export function formatAxisTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return axisFormatter.format(date);
}

export function formatUpdateTime(milliseconds: number | null | undefined): string {
  if (!isRenderable(milliseconds)) return DASH;
  return timeFormatter.format(new Date(milliseconds));
}
