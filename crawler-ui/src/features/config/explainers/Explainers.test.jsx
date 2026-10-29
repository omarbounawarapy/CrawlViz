import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import CascadeFunnel from "./CascadeFunnel";
import BackoffChart from "./BackoffChart";
import StrategyCards from "./StrategyCards";
import { TopKExample, ClusterExample, ContextExample } from "./TopKExample";

afterEach(cleanup);

const CASCADE = {
  low_threshold: 0.2,
  high_threshold: 0.75,
  high_score_llm_fraction: 0.3,
  low_score_sample_fraction: 0.1,
  high_score_random_fraction: 0.25,
  percentile_bucketing: false,
  percentile_min_links: 10,
  max_llm_links_per_node: 50,
  low_percentile: 20,
  high_percentile: 75,
};

describe("CascadeFunnel", () => {
  it("states what happens to the example page", () => {
    render(<CascadeFunnel cfg={CASCADE} />);
    expect(screen.getByRole("status").textContent).toBe(
      "Of 40 links: 8 dropped, 25 sent to the LLM, 7 trusted without one.",
    );
  });
  it("re-flows when a cut-off moves", () => {
    const { rerender } = render(<CascadeFunnel cfg={CASCADE} />);
    rerender(<CascadeFunnel cfg={{ ...CASCADE, low_threshold: 0.5, high_threshold: 0.51 }} />);
    expect(screen.getByRole("status").textContent).toContain("20 dropped");
  });
  it("mentions the per-page cap when it bites", () => {
    render(<CascadeFunnel cfg={{ ...CASCADE, max_llm_links_per_node: 12 }} />);
    expect(screen.getByRole("status").textContent).toContain("13 more were held back");
  });
});

describe("StrategyCards", () => {
  const weights = { target_similarity: 0.25, novelty_injection: 0.2, depth_penalty: 0.05 };
  const priority = {
    nlp_bias: 60,
    llm_bias: 40,
    aggressive_weights: weights,
    balanced_weights: weights,
    exploration_weights: weights,
  };

  it("writes a changed weight back under the chosen strategy", () => {
    const onChange = vi.fn();
    render(<StrategyCards priority={priority} defaults={priority} defaultStrategy="aggressive" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("aggressive target similarity"), { target: { value: "0.8" } });
    expect(onChange).toHaveBeenCalledWith(
      "priority.aggressive_weights",
      expect.objectContaining({ target_similarity: 0.8 }),
    );
  });
  it("makes the clicked card the default strategy", () => {
    const onChange = vi.fn();
    render(<StrategyCards priority={priority} defaults={priority} defaultStrategy="balanced" onChange={onChange} />);
    expect(screen.getByRole("radio", { name: /Balanced/ }).getAttribute("aria-checked")).toBe("true");
    fireEvent.click(screen.getByRole("radio", { name: /Exploration/ }));
    expect(onChange).toHaveBeenCalledWith("scoring_cascade.default_priority_strategy", "exploration");
  });
  it("states how the top five of each strategy look on the example page", () => {
    render(<StrategyCards priority={priority} defaults={priority} defaultStrategy="balanced" onChange={() => {}} />);
    expect(screen.getAllByText(/Top 5 of the example page: \d+ off topic, average depth/)).toHaveLength(3);
  });
  it("resets one strategy to its default weights", () => {
    const onChange = vi.fn();
    const changed = { ...priority, balanced_weights: { ...weights, target_similarity: 0.9 } };
    render(<StrategyCards priority={changed} defaults={priority} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /Reset balanced/ }));
    expect(onChange).toHaveBeenCalledWith("priority.balanced_weights", weights);
  });
});

describe("BackoffChart", () => {
  const fetch = {
    min_delay: 1,
    jitter_max: 0.2,
    backoff_start: 1,
    backoff_max: 10,
    backoff_growth: 2,
    backoff_success_decay: 0.5,
    backoff_failure_decay: 0.5,
  };
  it("reports the steady pace and the worst wait", () => {
    render(<BackoffChart cfg={fetch} />);
    expect(screen.getByRole("status").textContent).toContain("The longest a request waits is 11.2 s");
  });
  it("toggles the burst of 429s", () => {
    render(<BackoffChart cfg={fetch} />);
    const chip = screen.getByRole("button", { name: /answers 429/ });
    expect(chip.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("false");
  });
});

describe("NLP examples", () => {
  it("top-k averages the nearest reference vectors", () => {
    render(<TopKExample k={2} />);
    expect(screen.getByRole("status").textContent).toContain("scores 0.78");
  });
  it("cluster example counts clusters", () => {
    render(<ClusterExample eps={0.3} minSamples={2} />);
    expect(screen.getByRole("status").textContent).toMatch(/2 clusters and 0 stray/);
  });
  it("context example warns when the anchor is cut off", () => {
    render(<ContextExample length={20} />);
    expect(screen.getByRole("status").textContent).toContain("falls outside");
  });
});
