// Re-exported from nodeStates.js (the single source of truth -- see
// docs/V2_ARCHITECTURE.md §A.1.4) under its historical array-shaped name,
// so existing consumers (MetricsPanel, Legend, useDemoMode) that iterate
// it with .forEach/.map keep working unchanged.
export { NODE_STATE_ORDER as NODE_STATES } from "./nodeStates";

export const TYPE_BADGE = {
  SNAPSHOT_FULL: { bg: "#e9edf1", fg: "#33435a", label: "SNAP"  },
  NODE_ADDED: { bg: "#e9edf1", fg: "#33435a", label: "ADD"   },
  NODE_STATE_CHANGED: { bg: "#e9edf1", fg: "#33435a", label: "STATE" },
  NODE_EXPANDED: { bg: "#dfe5ec", fg: "#0f1b2d", label: "EXPND" },
  CRAWL_STOPPED: { bg: "#f1e3ec", fg: "#7a1f5c", label: "STOP"  },
  __WS_CONNECTED: { bg: "#e9edf1", fg: "#33435a", label: "WS↑"  },
  __WS_DISCONNECTED: { bg: "#f1e3ec", fg: "#7a1f5c", label: "WS↓"  },
  // V2 additions
  PIPELINE_EVENT: { bg: "#e9edf1", fg: "#33435a", label: "PIPE"  },
  CANDIDATE_EVALUATED: { bg: "#dfe5ec", fg: "#0f1b2d", label: "CAND"  },
  NODE_SCORED_DETAIL: { bg: "#dfe5ec", fg: "#0f1b2d", label: "SCORE" },
  NODE_ERROR: { bg: "#f1e3ec", fg: "#7a1f5c", label: "ERR"   },
};

// V1 used this as a hard allowlist and silently dropped anything not in
// it -- meaning every new backend message type needed a coordinated edit
// here *and* in the reducer *and* in TYPE_BADGE before it became visible
// anywhere (see docs/V2_ARCHITECTURE.md §A.1.7). eventNormalizer.js no
// longer filters against this; it's kept only as the set TYPE_BADGE falls
// back from, so a still-unrecognized `type` renders as a labeled generic
// badge instead of a blank one.
export const KNOWN_TYPES = new Set(Object.keys(TYPE_BADGE));