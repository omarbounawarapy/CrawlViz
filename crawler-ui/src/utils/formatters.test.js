import { describe, it, expect } from "vitest";
import { hasScore } from "./formatters";

describe("hasScore", () => {
  it("counts a score of 0 as a score", () => {
    expect(hasScore(0)).toBe(true);
    expect(hasScore(72)).toBe(true);
    expect(hasScore(0.5)).toBe(true);
  });

  it("rejects a missing score", () => {
    expect(hasScore(null)).toBe(false);
    expect(hasScore(undefined)).toBe(false);
    expect(hasScore("")).toBe(false);
    expect(hasScore(Number.NaN)).toBe(false);
  });
});
