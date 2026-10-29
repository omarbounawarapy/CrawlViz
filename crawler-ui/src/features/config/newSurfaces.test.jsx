import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import PipelineFlow from "./PipelineFlow";
import BackoffChart from "./explainers/BackoffChart";
import ProviderTable from "./ProviderTable";
import { fetchProviders } from "../../api/client";

vi.mock("../../api/client", () => ({
  fetchProviders: vi.fn(() =>
    Promise.resolve({
      groq: { models: ["openai/gpt-oss-120b"], keys: 2 },
      openai: { models: [], keys: 0 },
    }),
  ),
}));

const PIPES = {
  requests: { workers: 4, max_queue_size: null },
  processing: { workers: 1, max_queue_size: 50 },
  filtering: { workers: 10, max_queue_size: null },
  transformation: { workers: 3, max_queue_size: null },
  scoring: { workers: 1, max_queue_size: null },
  priority: { workers: 10, max_queue_size: null },
  storage: { workers: 1, max_queue_size: null },
  retry: { workers: 1, max_queue_size: null },
  debugging: { workers: 2, max_queue_size: null },
};

const FETCH = {
  min_delay: 1,
  jitter_max: 0.2,
  backoff_start: 1,
  backoff_max: 10,
  backoff_growth: 2,
  backoff_success_decay: 0.5,
  backoff_failure_decay: 0.5,
};

describe("PipelineFlow", () => {
  it("draws every stage with its workers and queue bound", () => {
    render(<PipelineFlow pipelines={PIPES} batchSize={100} />);
    const picture = screen.getByRole("img");
    expect(picture.getAttribute("aria-label")).toContain("Extract: 1 worker, queue up to 50");
    expect(picture.getAttribute("aria-label")).toContain("Fetch: 4 workers, queue unbounded");
    expect(picture.getAttribute("aria-label")).toContain("Export: batch of 100 rows");
  });

  it("says row, not rows, for a batch of one", () => {
    render(<PipelineFlow pipelines={PIPES} batchSize={1} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("batch of 1 row.");
  });
});

describe("BackoffChart delay handle", () => {
  it("is a slider that moves the minimum delay one tenth of a second per arrow key", () => {
    const onMinDelay = vi.fn();
    render(<BackoffChart cfg={FETCH} latency={0.3} onMinDelay={onMinDelay} />);
    const handle = screen.getByRole("slider", { name: "Minimum delay between requests" });
    expect(handle.getAttribute("aria-valuenow")).toBe("1");
    fireEvent.keyDown(handle, { key: "ArrowUp" });
    expect(onMinDelay).toHaveBeenLastCalledWith(1.1);
    fireEvent.keyDown(handle, { key: "PageDown" });
    expect(onMinDelay).toHaveBeenLastCalledWith(0);
    fireEvent.keyDown(handle, { key: "Home" });
    expect(onMinDelay).toHaveBeenLastCalledWith(0);
  });

  it("is not drawn without a way to change the value", () => {
    render(<BackoffChart cfg={FETCH} latency={0.3} />);
    expect(screen.queryByRole("slider", { name: "Minimum delay between requests" })).toBeNull();
  });
});

describe("ProviderTable", () => {
  it("shows each provider's URL, models and stored keys", async () => {
    render(<ProviderTable endpoints={{ groq: "https://api.groq.com/x", openai: "https://api.openai.com/y" }} />);
    await waitFor(() => expect(screen.getByText("2 stored")).toBeTruthy());
    expect(fetchProviders).toHaveBeenCalled();
    expect(screen.getByText("https://api.groq.com/x")).toBeTruthy();
    expect(screen.getByText("openai/gpt-oss-120b")).toBeTruthy();
    expect(screen.getByText("No key stored")).toBeTruthy();
  });
});
