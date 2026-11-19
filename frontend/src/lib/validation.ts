/** Ticker and quantity validation. Shared by the watchlist and trade bar. */

export const TICKER_PATTERN = /^[A-Za-z][A-Za-z0-9.\-]{0,9}$/;
export const MAX_TICKER_LENGTH = 10;

export function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase();
}

export function isValidTicker(raw: string): boolean {
  return TICKER_PATTERN.test(raw.trim());
}

export const TICKER_ERROR = "Use 1–10 letters, digits, dots or hyphens; start with a letter.";

export type QuantityValidation =
  | { ok: true; value: number }
  | { ok: false; error: string };

export function validateQuantity(raw: string): QuantityValidation {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: false, error: "Enter a quantity." };
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return { ok: false, error: "Quantity must be a number." };
  if (value <= 0) return { ok: false, error: "Quantity must be greater than zero." };
  if (value > 1_000_000) return { ok: false, error: "Maximum quantity is 1,000,000." };
  const decimals = trimmed.split(".")[1]?.length ?? 0;
  if (decimals > 4) return { ok: false, error: "Use at most 4 decimal places." };
  return { ok: true, value };
}
