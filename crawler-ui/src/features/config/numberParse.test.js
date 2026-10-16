import { describe, it, expect } from "vitest";
import { parseNumberText, formatNumber } from "./numberParse";

describe("parseNumberText", () => {
  it("reads dot and comma decimals the same way", () => {
    expect(parseNumberText("0.3")).toEqual({ ok: true, value: 0.3 });
    expect(parseNumberText("0,3")).toEqual({ ok: true, value: 0.3 });
  });
  it("treats a comma as thousands when a dot is also present", () => {
    expect(parseNumberText("1,000.5")).toEqual({ ok: true, value: 1000.5 });
  });
  it("keeps empty text as null, not an error", () => {
    expect(parseNumberText("  ")).toEqual({ ok: true, value: null });
  });
  it("rejects text that is not a number", () => {
    expect(parseNumberText("abc").ok).toBe(false);
    expect(parseNumberText("1.2.3").ok).toBe(false);
    expect(parseNumberText("0,3,1").ok).toBe(false);
  });
  it("reads a trailing dot while typing as the number so far", () => {
    expect(parseNumberText("2.").value).toBe(2);
  });
  it("always shows dot decimals", () => {
    expect(formatNumber(0.25)).toBe("0.25");
    expect(formatNumber(null)).toBe("");
  });
});
