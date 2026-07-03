export const NODE_STATES = ["CREATED", "FETCHED", "FILTERED", "SCORED", "EXPANDED"];


export const TYPE_BADGE = {
  SNAPSHOT_FULL:      { bg: "#1a2a4a", fg: "#4da6e0", label: "SNAP"  },
  NODE_ADDED:         { bg: "#1a3a2a", fg: "#40d9a0", label: "ADD"   },
  NODE_STATE_CHANGED: { bg: "#2a2a1a", fg: "#e0b840", label: "STATE" },
  NODE_EXPANDED:      { bg: "#2a1a3a", fg: "#b860e0", label: "EXPND" },
  CRAWL_STOPPED:      { bg: "#3a1a1a", fg: "#e04040", label: "STOP"  },
  __WS_CONNECTED:     { bg: "#1a3a2a", fg: "#40d9a0", label: "WS↑"  },
  __WS_DISCONNECTED:  { bg: "#3a1a1a", fg: "#e04040", label: "WS↓"  },
};

export const KNOWN_TYPES = new Set([
  "SNAPSHOT_FULL",
  "NODE_ADDED",
  "NODE_STATE_CHANGED",
  "NODE_EXPANDED",
  "CRAWL_STOPPED",
]);