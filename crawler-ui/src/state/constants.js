// Re-exported from nodeStates.js (the single source of truth -- see
// docs/V2_ARCHITECTURE.md §A.1.4) under its historical array-shaped name,
// so existing consumers (MetricsPanel, Legend, useDemoMode) that iterate
// it with .forEach/.map keep working unchanged.
export { NODE_STATE_ORDER as NODE_STATES } from "./nodeStates";

export const TYPE_BADGE = {
  SNAPSHOT_FULL:       { bg: "#1a2a4a", fg: "#4da6e0", label: "SNAP"  },
  NODE_ADDED:          { bg: "#1a3a2a", fg: "#40d9a0", label: "ADD"   },
  NODE_STATE_CHANGED:  { bg: "#2a2a1a", fg: "#e0b840", label: "STATE" },
  NODE_EXPANDED:       { bg: "#2a1a3a", fg: "#b860e0", label: "EXPND" },
  CRAWL_STOPPED:       { bg: "#3a1a1a", fg: "#e04040", label: "STOP"  },
  __WS_CONNECTED:      { bg: "#1a3a2a", fg: "#40d9a0", label: "WS↑"  },
  __WS_DISCONNECTED:   { bg: "#3a1a1a", fg: "#e04040", label: "WS↓"  },
  // V2 additions
  PIPELINE_EVENT:      { bg: "#1a2438", fg: "#6b8cae", label: "PIPE"  },
  CANDIDATE_EVALUATED: { bg: "#2e2410", fg: "#e0a840", label: "CAND"  },
  NODE_SCORED_DETAIL:  { bg: "#1a2a3a", fg: "#4dc0e0", label: "SCORE" },
  NODE_ERROR:          { bg: "#3a1a1a", fg: "#ff6b6b", label: "ERR"   },
};

// V1 used this as a hard allowlist and silently dropped anything not in
// it -- meaning every new backend message type needed a coordinated edit
// here *and* in the reducer *and* in TYPE_BADGE before it became visible
// anywhere (see docs/V2_ARCHITECTURE.md §A.1.7). eventNormalizer.js no
// longer filters against this; it's kept only as the set TYPE_BADGE falls
// back from, so a still-unrecognized `type` renders as a labeled generic
// badge instead of a blank one.
export const KNOWN_TYPES = new Set(Object.keys(TYPE_BADGE));