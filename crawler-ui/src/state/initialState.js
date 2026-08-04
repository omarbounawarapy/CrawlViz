// How often (in event-log entries) the reducer checkpoints full state for
// replay scrubbing. See state/reducer.js's REPLAY_SEEK handling and
// docs/V2_ARCHITECTURE.md §A.1.8 / §B.3.2 for why this exists: without it,
// every scrub-slider tick re-runs applyEvent over the entire event log
// from scratch, which is fine for a few hundred events and not fine for
// the low thousands a real crawl produces.
export const SNAPSHOT_INTERVAL = 200;

// Bounds mirroring the backend's own (see ui_bridge/crawl_state_snapshot.py
// _MAX_CANDIDATES / _MAX_ERRORS) so a long-running crawl can't grow either
// list without limit client-side either.
export const MAX_CANDIDATES = 4000;
export const MAX_ERRORS = 1000;

export const INITIAL_STATE = {
  nodes:        new Map(),  // node_id → NodeRecord
  edges:        new Set(),  // "parent_id→child_id" strings
  metrics:      null,
  status:       "CONNECTING",   // crawl lifecycle: CONNECTING | RUNNING | STOPPED
  stop_reason:  null,
  eventLog:     [],         // append-only; used for replay
  _replayIndex: null,
  _checkpoints: [],         // [{ index, state }] periodic full-state snapshots for O(1)-ish seeking

  // V2 additions
  connectionStatus: "CONNECTING",  // socket health: CONNECTING | CONNECTED | DISCONNECTED
                                     // -- deliberately separate from `status` (crawl
                                     // lifecycle) -- see docs/V2_ARCHITECTURE.md §A.1.9
  pipelineStats: {},   // stage -> { started, completed, failed, queue_size, last_duration_ms, avg_duration_ms }
  candidates:    [],   // flat, most-recent-last, bounded to MAX_CANDIDATES
  nodeDetails:   {},   // node_id -> { nlp_score, nlp_breakdown, llm_score, priority, priority_strategy }
  errors:        [],   // flat, most-recent-last, bounded to MAX_ERRORS
};
