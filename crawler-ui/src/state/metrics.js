export function deriveMetrics(state) {
  let total_links_found = 0;
  let total_items_stored = 0;
  let nodes_created = state.nodes.size;

  let start_time = null;
  let last_time  = null;

  for (const node of state.nodes.values()) {
    // ── Links (from filtering stage)
    if (node.links_accepted || node.links_rejected) {
      total_links_found +=
        (node.links_accepted || 0) +
        (node.links_rejected || 0);
    }

    // ── Items (if you use it)
    if (node.items_accepted) {
      total_items_stored += node.items_accepted;
    }

    // ── Timing (optional but correct)
    if (node.created_at) {
      if (!start_time || node.created_at < start_time) {
        start_time = node.created_at;
      }
      if (!last_time || node.created_at > last_time) {
        last_time = node.created_at;
      }
    }
  }

  const elapsed_seconds =
    start_time && last_time ? last_time - start_time : 0;

  return {
    nodes_created,
    total_links_found,
    total_items_stored,
    elapsed_seconds,
  };
}