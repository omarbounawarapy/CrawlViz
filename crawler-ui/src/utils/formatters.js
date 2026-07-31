export function formatTs(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toISOString().slice(11, 23);
}

export function eventSummary(ev) {
  switch (ev.type) {
    case "NODE_ADDED":         return ev.node?.url?.split("/").pop() || ev.node?.node_id;
    case "NODE_STATE_CHANGED": return `${ev.node_id?.slice(0, 6)}… → ${ev.state}`;
    case "NODE_EXPANDED":      return `${ev.parent_id?.slice(0, 6)}… → ${ev.children_count} children`;
    case "SNAPSHOT_FULL":      return `${ev.nodes?.length ?? 0} nodes`;
    case "CRAWL_STOPPED":      return ev.reason;
    // V2 additions
    case "PIPELINE_EVENT":      return `${ev.stage} ${ev.phase}${ev.detail ? " — " + ev.detail : ""}`;
    case "CANDIDATE_EVALUATED": return `${ev.candidates?.length ?? 0} link${ev.candidates?.length === 1 ? "" : "s"} ${ev.decision === "dropped" ? "dropped" : "trusted"}`;
    case "NODE_SCORED_DETAIL":  return `${ev.node_id?.slice(0, 6)}… priority=${fmtNum(ev.priority)}`;
    case "NODE_ERROR":          return `${ev.stage}: ${ev.error_message}`;
    default:                   return "";
  }
}

function fmtNum(n) {
  return typeof n === "number" ? n.toFixed(2) : "—";
}

// ── V2 additions ─────────────────────────────────────────────────────────────

/** "1.2s", "340ms", "2m 04s" — always a fixed, short, tabular-friendly form. */
export function formatDuration(ms) {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const totalSeconds = ms / 1000;
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

export function formatPercent(x, digits = 0) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}

export function shortId(id, len = 8) {
  if (!id) return "—";
  return String(id).length > len ? `${String(id).slice(0, len)}…` : String(id);
}

export function hostnameOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url || "";
  }
}

export function pathOf(url) {
  try {
    const u = new URL(url);
    return `${u.pathname}${u.search}` || "/";
  } catch {
    return url || "";
  }
}