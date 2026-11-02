import { describe, it, expect } from "vitest";
import { median, percentile, std, confidenceScore, leadHoursFrom } from "../src/lib/stats";

describe("stats", () => {
  it("median", () => {
    expect(median([1, 2, 3, 4])).toBe(2.5);
    expect(median([1, 2, 3])).toBe(2);
  });
  it("percentile", () => {
    expect(percentile([1, 2, 3, 4], 0.5)).toBe(2.5);
  });
  it("std", () => {
    expect(std([2, 4, 4, 4, 5, 5, 7, 9])).toBeCloseTo(2, 5);
  });
  it("confidenceScore", () => {
    const r = confidenceScore(0.1, 0.1, 10);
    expect(r.score).toBeGreaterThan(80);
    expect(r.label).toBe("High");
  });
  it("leadHoursFrom", () => {
    expect(leadHoursFrom("2026-11-01T00:00:00Z", "2026-11-01T06:00:00Z")).toBe(6);
  });
});
