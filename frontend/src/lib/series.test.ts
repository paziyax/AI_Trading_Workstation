import { describe, expect, it } from "vitest";
import { appendSample, buildSparkline } from "@/lib/series";

describe("stream sample history", () => {
  it("caps a ticker's samples at 90 and keeps the newest", () => {
    let samples: number[] = [];
    for (let index = 1; index <= 120; index += 1) {
      samples = appendSample(samples, index);
    }
    expect(samples).toHaveLength(90);
    expect(samples[0]).toBe(31);
    expect(samples[samples.length - 1]).toBe(120);
  });

  it("does not mutate the previous sample array", () => {
    const original = [1, 2, 3];
    const next = appendSample(original, 4);
    expect(original).toEqual([1, 2, 3]);
    expect(next).toEqual([1, 2, 3, 4]);
  });

  it("refuses to draw a trend before two samples exist", () => {
    expect(buildSparkline([])).toBeNull();
    expect(buildSparkline([190])).toBeNull();
  });

  it("builds an upward path and tone from real samples", () => {
    const geometry = buildSparkline([190, 191, 193]);
    expect(geometry).not.toBeNull();
    expect(geometry?.tone).toBe("up");
    expect(geometry?.points.split(" ")).toHaveLength(3);
    expect(geometry?.points).not.toContain("NaN");
  });

  it("handles a flat line without dividing by zero", () => {
    const geometry = buildSparkline([190, 190, 190]);
    expect(geometry?.tone).toBe("flat");
    expect(geometry?.points).not.toContain("NaN");
  });
});
