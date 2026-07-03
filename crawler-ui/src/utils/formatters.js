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
    default:                   return "";
  }
}