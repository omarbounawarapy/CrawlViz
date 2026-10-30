import { describe, it, expect } from "vitest";
import { deriveMetrics } from "./metrics";
import { INITIAL_STATE } from "./initialState";

function stateWithNodes(states) {
  const nodes = new Map(states.map((s, i) => [String(i), { node_id: String(i), state: s }]));
  return { ...INITIAL_STATE, nodes };
}

describe("deriveMetrics", () => {
  it("counts fetched pages as the nodes that have left CREATED, and found as all of them", () => {
    const metrics = deriveMetrics(stateWithNodes(["CREATED", "CREATED", "FETCHED", "SCORED", "EXPANDED"]));
    expect(metrics.nodes_created).toBe(5);
    expect(metrics.nodes_fetched).toBe(3);
  });

  it("reports no fetched pages for an empty or all-CREATED crawl", () => {
    expect(deriveMetrics(INITIAL_STATE).nodes_fetched).toBe(0);
    expect(deriveMetrics(stateWithNodes(["CREATED"])).nodes_fetched).toBe(0);
  });
});
