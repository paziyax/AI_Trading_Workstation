import { describe, expect, it } from "vitest";
import {
  formatCompactCurrency,
  formatCurrency,
  formatPercent,
  formatPrice,
  formatQuantity,
  formatSignedCurrency,
  formatWeight,
} from "@/lib/format";

describe("number formatting", () => {
  it("formats money with separators and two decimals", () => {
    expect(formatCurrency(10000)).toBe("$10,000.00");
    expect(formatCurrency(191.005)).toBe("$191.01");
    expect(formatCurrency(-1234.5)).toBe("−$1,234.50");
    expect(formatCurrency(null)).toBe("—");
    expect(formatPrice(189.9)).toBe("$189.90");
  });

  it("always signs profit and loss, including a true minus", () => {
    expect(formatSignedCurrency(10)).toBe("+$10.00");
    expect(formatSignedCurrency(-8.4)).toBe("−$8.40");
    expect(formatSignedCurrency(0)).toBe("$0.00");
    expect(formatSignedCurrency(null)).toBe("—");
  });

  it("formats percentages in percent units with signs", () => {
    expect(formatPercent(0.5263)).toBe("+0.53%");
    expect(formatPercent(-1.2345)).toBe("−1.23%");
    expect(formatPercent(0)).toBe("0.00%");
    expect(formatPercent(null)).toBe("—");
  });

  it("trims quantities to at most four decimals", () => {
    expect(formatQuantity(10)).toBe("10");
    expect(formatQuantity(0.5)).toBe("0.5");
    expect(formatQuantity(1234.56784)).toBe("1,234.5678");
    expect(formatQuantity(null)).toBe("—");
  });

  it("formats weights and compact chart axes", () => {
    expect(formatWeight(19.08)).toBe("19.1%");
    expect(formatCompactCurrency(10010)).toBe("$10,010");
    expect(formatCompactCurrency(982.4)).toBe("$982");
  });

  it("uses a real minus sign but keeps the ASCII dash as unavailable", () => {
    expect(formatCurrency(-2)).toContain("\u2212");
    expect(formatPercent(-2)).not.toContain("-");
  });
});
