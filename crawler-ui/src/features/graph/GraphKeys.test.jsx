import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import GraphView from "./GraphView";

const nodes = new Map([
  ["a", { node_id: "a", parent_id: null, state: "EXPANDED", llm_score: 90, url: "/wiki/A", depth: 0 }],
  ["b", { node_id: "b", parent_id: "a", state: "SCORED", llm_score: 70, url: "/wiki/B", depth: 1 }],
]);

function setup() {
  render(
    <GraphView
      nodes={nodes}
      edges={new Set(["a→b"])}
      candidates={[]}
      replayIndex={null}
      onNodeClick={vi.fn()}
      onBackgroundClick={vi.fn()}
      selectedNodeId={null}
    />,
  );
}

const zoomLevel = () => screen.getByLabelText("Zoom level").textContent;

// The engine fits the plate shortly after mounting; wait for that so only a key press can move the level.
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 600));
  });
}

describe("graph keyboard shortcuts", () => {
  it("zooms with + while focus is inside the graph", async () => {
    setup();
    await settle();
    const before = zoomLevel();
    await act(async () => {
      fireEvent.keyDown(screen.getByRole("button", { name: "Zoom in" }), { key: "+" });
    });
    await vi.waitFor(() => expect(zoomLevel()).not.toBe(before));
  });

  it("ignores the shortcuts while typing in the find field", async () => {
    setup();
    await settle();
    const before = zoomLevel();
    await act(async () => {
      fireEvent.keyDown(screen.getByLabelText("Find a page by URL"), { key: "+" });
    });
    expect(zoomLevel()).toBe(before);
  });

  it("does not react to keys pressed outside the graph", async () => {
    setup();
    await settle();
    const before = zoomLevel();
    await act(async () => {
      fireEvent.keyDown(document.body, { key: "+" });
    });
    expect(zoomLevel()).toBe(before);
  });
});
