import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SpiderLoader from "./SpiderLoader";

function renderLoader() {
  const onSkip = vi.fn();
  render(<SpiderLoader progress={0.2} done={false} onSkip={onSkip} />);
  return onSkip;
}

describe("SpiderLoader", () => {
  it("skips once when the Skip button is pressed", () => {
    const onSkip = renderLoader();
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("skips when Escape is pressed", () => {
    const onSkip = renderLoader();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("skips when the overlay itself is clicked", () => {
    const onSkip = renderLoader();
    fireEvent.click(screen.getByRole("status", { name: "Loading CrawlViz" }));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("starts with focus on the Skip button", () => {
    renderLoader();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Skip" }));
  });
});
