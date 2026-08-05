import { describe, it, expect } from "vitest";
import { crawlReducer, applyEvent } from "./reducer";
import { INITIAL_STATE } from "./initialState";

function nodeAdded(id, parentId, ts) {
  return {
    type: "NODE_ADDED", ts,
    node: { node_id: String(id), url: `http://x/${id}`, depth: 0, priority: 0.5, llm_score: 0, parent_id: parentId ? String(parentId) : null, state: "CREATED", created_at: ts },
  };
}

function bruteForceReplay(eventLog, index) {
  const slice = eventLog.slice(0, index + 1);
  return slice.reduce((s, ev) => applyEvent(s, ev), { ...INITIAL_STATE, eventLog });
}

describe("crawlReducer — V2 message types", () => {
  it("PIPELINE_EVENT tracks started/completed/failed counts and running average duration", () => {
    let state = INITIAL_STATE;
    state = crawlReducer(state, { type: "PIPELINE_EVENT", stage: "scoring", phase: "started", node_id: "1" });
    state = crawlReducer(state, { type: "PIPELINE_EVENT", stage: "scoring", phase: "completed", node_id: "1", duration_ms: 10 });
    state = crawlReducer(state, { type: "PIPELINE_EVENT", stage: "scoring", phase: "started", node_id: "2" });
    state = crawlReducer(state, { type: "PIPELINE_EVENT", stage: "scoring", phase: "completed", node_id: "2", duration_ms: 20 });

    expect(state.pipelineStats.scoring.started).toBe(2);
    expect(state.pipelineStats.scoring.completed).toBe(2);
    expect(state.pipelineStats.scoring.avg_duration_ms).toBe(15);
    expect(state.pipelineStats.scoring.last_duration_ms).toBe(20);
  });

  it("CANDIDATE_EVALUATED records dropped/trusted candidates without promoting them to nodes", () => {
    let state = INITIAL_STATE;
    state = crawlReducer(state, nodeAdded(1, null, 1));
    state = crawlReducer(state, {
      type: "CANDIDATE_EVALUATED", parent_id: "1", decision: "dropped",
      candidates: [{ url: "http://x/dropped", nlp_score: 0.05, nlp_breakdown: {} }],
    });
    expect(state.candidates).toHaveLength(1);
    expect(state.candidates[0].decision).toBe("dropped");
    expect(state.nodes.has("http://x/dropped")).toBe(false);
    expect(state.nodes.size).toBe(1); // only the real node from NODE_ADDED
  });

  it("NODE_SCORED_DETAIL is keyed by node_id and NODE_ERROR is bounded/appended", () => {
    let state = INITIAL_STATE;
    state = crawlReducer(state, { type: "NODE_SCORED_DETAIL", node_id: "1", nlp_score: 0.8, llm_score: 7, priority: 0.9 });
    expect(state.nodeDetails["1"]).toMatchObject({ nlp_score: 0.8, llm_score: 7, priority: 0.9 });

    state = crawlReducer(state, { type: "NODE_ERROR", node_id: "1", stage: "request", error_type: "TimeoutError", error_message: "boom" });
    expect(state.errors).toHaveLength(1);
    expect(state.errors[0].error_message).toBe("boom");
  });

  it("tracks connection status separately from crawl status (regression test for §A.1.9)", () => {
    let state = INITIAL_STATE;
    state = crawlReducer(state, { type: "__WS_DISCONNECTED" });
    expect(state.connectionStatus).toBe("DISCONNECTED");
    expect(state.status).toBe("CONNECTING"); // untouched -- crawl lifecycle is independent of socket health
  });
});

describe("crawlReducer — replay correctness (regression test for §A.1.8 perf fix)", () => {
  it("checkpoint-assisted __REPLAY_SEEK matches brute-force full replay at every boundary", () => {
    let state = INITIAL_STATE;
    const NUM_NODES = 850; // spans multiple SNAPSHOT_INTERVAL (200) checkpoints

    for (let i = 1; i <= NUM_NODES; i++) {
      const parent = i === 1 ? null : Math.max(1, i - 3);
      state = crawlReducer(state, nodeAdded(i, parent, 1000 + i));
      state = crawlReducer(state, { type: "PIPELINE_EVENT", stage: "scoring", phase: "completed", node_id: String(i), duration_ms: 5 + (i % 7) });
      if (i % 5 === 0) {
        state = crawlReducer(state, {
          type: "CANDIDATE_EVALUATED", parent_id: String(i), decision: i % 10 === 0 ? "dropped" : "trusted_no_llm",
          candidates: [{ url: `http://x/${i}-cand`, nlp_score: 0.3, nlp_breakdown: {} }],
        });
      }
      state = crawlReducer(state, { type: "NODE_STATE_CHANGED", node_id: String(i), state: "FETCHED" });
    }

    expect(state._checkpoints.length).toBeGreaterThan(1);

    const targets = [3, 199, 200, 201, 450, 799, 800, 801, state.eventLog.length - 1];
    for (const t of targets) {
      const viaCheckpoint = crawlReducer(state, { type: "__REPLAY_SEEK", index: t });
      const viaBruteForce = bruteForceReplay(state.eventLog, t);

      expect(viaCheckpoint.nodes.size).toBe(viaBruteForce.nodes.size);
      expect(viaCheckpoint.candidates.length).toBe(viaBruteForce.candidates.length);
      expect(viaCheckpoint.pipelineStats.scoring).toEqual(viaBruteForce.pipelineStats.scoring);
      expect(viaCheckpoint.nodes.get("500")).toEqual(viaBruteForce.nodes.get("500"));
    }
  });

  it("__REPLAY_EXIT restores exactly the live state", () => {
    let state = INITIAL_STATE;
    for (let i = 1; i <= 30; i++) {
      state = crawlReducer(state, nodeAdded(i, i === 1 ? null : i - 1, 1000 + i));
    }
    const exited = crawlReducer(state, { type: "__REPLAY_EXIT" });
    expect(exited.nodes.size).toBe(state.nodes.size);
    expect(exited._replayIndex).toBeNull();
  });
});
