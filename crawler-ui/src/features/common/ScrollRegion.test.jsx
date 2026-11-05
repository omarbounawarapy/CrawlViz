import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import ScrollRegion from "./ScrollRegion";

// jsdom has no layout, so the box sizes the hook reads are stubbed per test.
const size = { scrollWidth: 100, clientWidth: 100, scrollHeight: 50, clientHeight: 50 };
const observers = [];

beforeEach(() => {
  Object.assign(size, { scrollWidth: 100, clientWidth: 100, scrollHeight: 50, clientHeight: 50 });
  for (const key of Object.keys(size)) {
    vi.spyOn(HTMLElement.prototype, key, "get").mockImplementation(() => size[key]);
  }
  observers.length = 0;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback) {
        this.callback = callback;
        observers.push(this);
      }
      // Like the real observer, report once when observation starts.
      observe() {
        this.callback();
      }
      disconnect() {}
    },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ScrollRegion", () => {
  it("is not a tab stop while its content fits", () => {
    render(<ScrollRegion label="Runs table">content</ScrollRegion>);
    expect(screen.getByRole("region", { name: "Runs table" }).hasAttribute("tabindex")).toBe(false);
  });

  it("takes keyboard focus once its content overflows sideways", () => {
    size.scrollWidth = 400;
    render(<ScrollRegion label="Runs table">content</ScrollRegion>);
    expect(screen.getByRole("region", { name: "Runs table" }).getAttribute("tabindex")).toBe("0");
  });

  it("follows the container when it is resized", () => {
    render(<ScrollRegion label="Runs table">content</ScrollRegion>);
    const region = screen.getByRole("region", { name: "Runs table" });
    expect(region.hasAttribute("tabindex")).toBe(false);
    size.scrollWidth = 400;
    act(() => observers.forEach((o) => o.callback()));
    expect(region.getAttribute("tabindex")).toBe("0");
    size.scrollWidth = 100;
    act(() => observers.forEach((o) => o.callback()));
    expect(region.hasAttribute("tabindex")).toBe(false);
  });
});
