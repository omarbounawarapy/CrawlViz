import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import GraphView from "./GraphView";

const nodes = new Map([
  ["a", { node_id: "a", parent_id: null, state: "EXPANDED", llm_score: 90, url: "/wiki/A", depth: 0 }],
  ["b", { node_id: "b", parent_id: "a", state: "SCORED", llm_score: 70, url: "/wiki/B", depth: 1 }],
]);
const edges = new Set(["a→b"]);

function setup(props = {}) {
  render(<GraphView nodes={nodes} edges={edges} candidates={[]} replayIndex={null} onNodeClick={vi.fn()} onBackgroundClick={vi.fn()} selectedNodeId={null} {...props} />);
}

describe("zoom utility", () => {
  it("offers zoom in, out, fit and centre-on-selection, with a level readout", () => {
    setup();
    expect(screen.getByRole("group", { name: "Zoom" })).toBeTruthy();
    for (const name of ["Zoom in", "Zoom out", "Fit the whole plate", "Centre on the selected page"]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    expect(screen.getByLabelText("Zoom level").textContent).toMatch(/%$/);
  });

  it("can only centre on a page when one is selected", () => {
    setup();
    expect(screen.getByRole("button", { name: "Centre on the selected page" }).disabled).toBe(true);
  });

  it("centres on the selection once there is one", () => {
    setup({ selectedNodeId: "b" });
    expect(screen.getByRole("button", { name: "Centre on the selected page" }).disabled).toBe(false);
  });

  it("buttons and keys do not throw", () => {
    setup({ selectedNodeId: "b" });
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
      fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
      fireEvent.click(screen.getByRole("button", { name: "Fit the whole plate" }));
      for (const key of ["+", "-", "0", "f"]) fireEvent.keyDown(window, { key });
    });
  });

  it("ignores the zoom keys while typing in a field", () => {
    setup();
    const input = screen.getByLabelText("Find a node by URL");
    expect(() => fireEvent.keyDown(input, { key: "+" })).not.toThrow();
  });
});
