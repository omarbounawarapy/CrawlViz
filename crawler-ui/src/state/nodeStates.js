// Single source of truth for the node lifecycle enum.
//
// V1 had this disagreeing in four places: docs/crawl_messages.ts (backend,
// correct), state/constants.js (matched backend), NodeDetailsPanel.jsx
// (invented REJECTED/SKIPPED, colors defined for states the backend never
// sent), and theme/tokens.js's tokenShape (a third, mostly disjoint set:
// QUEUED/FETCHING/EXPANDING/STORED/ERROR). See docs/V2_ARCHITECTURE.md §A.1.4.
//
// This file is now the only place the enum is spelled out. Everything else
// -- the reducer, the graph, the inspector, the theme -- imports from here.
//
// DROPPED is new in V2: it's not a NodeState (a link in this state never
// became a full node -- see CandidateRecord in the wire protocol), but it
// shares the same visual language (a color, a label) as the real states, so
// it lives in the same registry rather than a parallel one.

export const NODE_STATES = Object.freeze({
  CREATED:  "CREATED",
  FETCHED:  "FETCHED",
  FILTERED: "FILTERED",
  SCORED:   "SCORED",
  EXPANDED: "EXPANDED",
});

export const NODE_STATE_ORDER = [
  NODE_STATES.CREATED,
  NODE_STATES.FETCHED,
  NODE_STATES.FILTERED,
  NODE_STATES.SCORED,
  NODE_STATES.EXPANDED,
];

// Candidate decisions -- links the cascade evaluated that did not (or did
// not yet) become full nodes. See docs/crawl_messages.ts CandidateDecision.
export const CANDIDATE_DECISIONS = Object.freeze({
  DROPPED: "dropped",
  TRUSTED: "trusted_no_llm",
});

// Pipeline stages, in traversal order -- mirrors backend PIPELINE_STAGES.
export const PIPELINE_STAGES = Object.freeze([
  "request", "extraction", "filtering", "scoring", "priority", "transformation", "export",
]);

export const PIPELINE_STAGE_LABELS = Object.freeze({
  request:        "Request",
  extraction:     "Extraction",
  filtering:      "Filtering",
  scoring:        "Scoring",
  priority:       "Priority",
  transformation: "Transform",
  export:         "Export",
});

export function isKnownNodeState(state) {
  return Object.prototype.hasOwnProperty.call(NODE_STATES, state);
}
