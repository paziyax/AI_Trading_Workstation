import { describe, expect, it } from "vitest";
import {
  isValidTicker,
  normalizeTicker,
  TICKER_ERROR,
  validateQuantity,
} from "@/lib/validation";

describe("ticker validation", () => {
  it("accepts the contract alphabet and uppercases", () => {
    expect(normalizeTicker(" aapl ")).toBe("AAPL");
    expect(isValidTicker("BRK.B")).toBe(true);
    expect(isValidTicker("RDS-A")).toBe(true);
    expect(isValidTicker("A")).toBe(true);
    expect(isValidTicker("ABCDEFGHIJ")).toBe(true);
  });

  it("rejects empty, numeric and overlong tickers", () => {
    expect(isValidTicker("")).toBe(false);
    expect(isValidTicker("1BAD")).toBe(false);
    expect(isValidTicker("ABCDEFGHIJK")).toBe(false);
    expect(isValidTicker("BAD TICKER")).toBe(false);
    expect(TICKER_ERROR).toContain("1–10");
  });
});

describe("quantity validation", () => {
  it("accepts positive fractions up to four decimals", () => {
    expect(validateQuantity("5")).toEqual({ ok: true, value: 5 });
    expect(validateQuantity("0.125")).toEqual({ ok: true, value: 0.125 });
  });

  it("rejects empty, zero, negative, huge and over-precise values", () => {
    expect(validateQuantity("").ok).toBe(false);
    expect(validateQuantity("0").ok).toBe(false);
    expect(validateQuantity("-2").ok).toBe(false);
    expect(validateQuantity("1000001").ok).toBe(false);
    expect(validateQuantity("1.12345").ok).toBe(false);
    expect(validateQuantity("abc").ok).toBe(false);
  });
});
