import { afterEach, describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import BenchmarkPage from "./BenchmarkPage";

const EMPTY_PROTOCOL = {
  hypotheses: [], arms: [], budgets: [], models: [], primary_metric: "", amendments: [],
};
let overviewProtocol = null;

vi.mock("../../api/client", () => ({
  fetchBenchmarkOverview: () => Promise.resolve({
    protocol: overviewProtocol ?? {
      hypotheses: [{ id: "H1", text: "Cascade beats bfs.", comparison: "cascade vs bfs" }],
      primary_metric: "harvest@30", budgets: [50],
      arms: [{ arm: "cascade", repeats: "10", scopes: "rep0..rep9", llm: "yes" }],
      models: [{ role: "Judge", provider: "groq", model: "j" }],
      amendments: [{ title: "2026-10-15, a change", body: "Why." }],
    },
    graphs: {}, audit: null, runs: 3,
  }),
  fetchAudit: () => Promise.resolve({ items: [{ id: "1", title: "Page one", excerpt: "x", human_label: null }], done: 0 }),
  putAuditLabel: vi.fn(() => Promise.resolve({})),
  fetchAuditScore: () => Promise.reject(new Error("no annotated items yet")),
}));

describe("BenchmarkPage", () => {
  afterEach(() => { overviewProtocol = null; });

  it("says there is no study protocol yet instead of showing empty headings", async () => {
    overviewProtocol = EMPTY_PROTOCOL;
    render(<BenchmarkPage />);
    expect(await screen.findByText(/No study protocol has been written yet/)).toBeTruthy();
    expect(screen.queryByText("Hypotheses")).toBeNull();
    expect(screen.queryByText(/Primary metric/)).toBeNull();
  });

  it("shows the hypotheses on the overview", async () => {
    render(<BenchmarkPage />);
    expect(await screen.findByText(/Cascade beats bfs/)).toBeTruthy();
  });

  it("saves an audit answer without showing the judge label", async () => {
    const { putAuditLabel } = await import("../../api/client");
    render(<BenchmarkPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Audit" }));
    expect(await screen.findByText("Page one")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Label 1" }));
    await waitFor(() => expect(putAuditLabel).toHaveBeenCalledWith("1", 1, "1"));
    expect(screen.queryByText(/judge_label/)).toBeNull();
  });
});
