import { describe, it, expect } from "vitest";
import { crawlEstimate } from "./crawlCost";

describe("crawlEstimate", () => {
  const cost = { callsPerPage: 3, tokensPerPage: 1000, cap: null };
  it("multiplies the example page by the number of pages", () => {
    expect(crawlEstimate(cost, 100)).toEqual({ calls: 300, tokens: 100000, capped: false });
  });
  it("stops at the call cap and says so", () => {
    expect(crawlEstimate({ ...cost, cap: 200 }, 100)).toEqual({ calls: 200, tokens: 100000, capped: true });
  });
  it("is not capped when the cap is not reached", () => {
    expect(crawlEstimate({ ...cost, cap: 500 }, 100)).toEqual({ calls: 300, tokens: 100000, capped: false });
  });
});
