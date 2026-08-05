export function deriveMetrics(state) {
  let total_links_found = 0;
  let total_items_stored = 0;
  let nodes_created = state.nodes.size;

  let start_time = null;
  let last_time  = null;

  // V2: live counts of nodes currently at each lifecycle state -- the data
  // source for the Overview page's cascade funnel. Computed fresh from
  // state.nodes on every call rather than trusting a stale server-computed
  // snapshot, since this needs to update on every single node event, not
  // just at SNAPSHOT_FULL / CRAWL_STOPPED time.
  const stateCounts = { CREATED: 0, FETCHED: 0, FILTERED: 0, SCORED: 0, EXPANDED: 0 };

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

    if (node.state in stateCounts) stateCounts[node.state] += 1;
  }

  const elapsed_seconds =
    start_time && last_time ? last_time - start_time : 0;

  // V2: candidates the cascade evaluated that never became full nodes --
  // the "what didn't happen" counterpart to stateCounts above.
  let dropped = 0, trusted = 0;
  for (const c of state.candidates) {
    if (c.decision === "dropped") dropped += 1;
    else if (c.decision === "trusted_no_llm") trusted += 1;
  }

  return {
    nodes_created,
    total_links_found,
    total_items_stored,
    elapsed_seconds,
    stateCounts,
    candidatesDropped: dropped,
    candidatesTrusted: trusted,
  };
}