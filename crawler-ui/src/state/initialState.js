export const INITIAL_STATE = {
  nodes:        new Map(),  // node_id → NodeRecord
  edges:        new Set(),  // "parent_id→child_id" strings
  metrics:      null,
  status:       "CONNECTING",
  stop_reason:  null,
  eventLog:     [],         // append-only; used for replay
  _replayIndex: null,
};