import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import PipelineFlow from "./PipelineFlow";
import StrategyCards from "./explainers/StrategyCards";
import defaults from "./fixtures/defaults.json";

afterEach(cleanup);

describe("pipeline picture", () => {
  it("shows the items waiting in each queue while a crawl runs", () => {
    const { container } = render(<PipelineFlow pipelines={defaults.pipelines} batchSize={10}
                                               queues={{ requests: { size: 4, max: 50 } }} />);
    expect(container.textContent).toContain("4 waiting now");
  });

  it("shows no queue line when no crawl is running", () => {
    const { container } = render(<PipelineFlow pipelines={defaults.pipelines} batchSize={10} queues={null} />);
    expect(container.textContent).not.toContain("waiting now");
  });
});

describe("strategy cards keyboard", () => {
  it("moves focus and the default with the arrow keys, and only the default is a Tab stop", () => {
    const onChange = vi.fn();
    render(<StrategyCards priority={defaults.priority} defaults={defaults.priority}
                          defaultStrategy="balanced" onChange={onChange} />);
    const cards = screen.getAllByRole("radio");
    expect(cards.map((c) => c.tabIndex)).toEqual([-1, 0, -1]);
    cards[1].focus();
    fireEvent.keyDown(cards[1], { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("scoring_cascade.default_priority_strategy", "exploration");
    expect(document.activeElement).toBe(cards[2]);
  });
});
