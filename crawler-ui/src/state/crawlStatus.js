// The words for a crawl's lifecycle, in one place so the header, the overview and the run page
// never describe the same state three different ways.

const STATUS_WORD = {
  IDLE: "Idle",
  RUNNING: "Crawling",
  STOPPED: "Finished",
};

const STOPPED_BY_USER_WORD = "Stopped by you";

// "MAX_NODES" -> "max nodes"
export function humanizeStopReason(reason) {
  return String(reason).toLowerCase().replace(/_/g, " ");
}

/**
 * `{ word, reason }` for a crawl state (or any object with `status`, `stop_reason` and
 * `stopped_by_user`). `word` is "Idle", "Crawling", "Stopped by you" or "Finished"; `reason` is
 * why a finished crawl ended, or null when there is nothing to add.
 */
export function crawlStatusWords({ status, stop_reason: stopReason, stopped_by_user: stoppedByUser }) {
  if (status === "STOPPED" && stoppedByUser) return { word: STOPPED_BY_USER_WORD, reason: null };
  const word = STATUS_WORD[status] ?? String(status).toLowerCase();
  const reason = status === "STOPPED" && stopReason ? humanizeStopReason(stopReason) : null;
  return { word, reason };
}
