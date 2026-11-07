/**
 * UI message contract — ws://localhost:8765
 *
 * Protocol:
 *   On connect  → server pushes one SNAPSHOT_FULL (catch-up).
 *   Thereafter  → server pushes incremental messages as events occur.
 *   Client      → never sends anything.
 *
 * All messages are JSON objects with a discriminant `type` field.
 * No raw internal objects ever appear — every field is a primitive or
 * a plain nested object matching one of the interfaces below.
 */


// ─── Shared value types ───────────────────────────────────────────────────────

export type NodeState =
  | "CREATED"
  | "FETCHED"
  | "FILTERED"
  | "SCORED"
  | "EXPANDED";

export interface NodeRecord {
  node_id:    string;
  url:        string;
  depth:      number;
  priority:   number;
  llm_score:  number;
  parent_id:  string | null;
  state:      NodeState;
  created_at: number;           // unix timestamp (seconds)
}

export interface CrawlMetrics {
  nodes_created:      number;
  nodes_fetched:      number;
  nodes_filtered:     number;
  nodes_scored:       number;
  nodes_expanded:     number;
  total_links_found:  number;
  total_items_stored: number;
  start_time:         number;   // unix timestamp (seconds)
  elapsed_seconds:    number;
}

export type PipelineStage =
  | "request"
  | "extraction"
  | "filtering"
  | "scoring"
  | "priority"
  | "transformation"
  | "export";

export interface PipelineStat {
  started:          number;
  completed:        number;
  failed:           number;
  queue_size:       number | null;
  last_duration_ms: number | null;
  avg_duration_ms:  number | null;
}

/**
 * "dropped"        — low NLP confidence or budget exhausted; never a node.
 * "trusted_no_llm" — high NLP confidence; skips the LLM but DOES become a
 *                    node (it arrives later as NODE_ADDED).
 */
export type CandidateDecision = "dropped" | "trusted_no_llm";

export interface CandidateRecord {
  parent_id:     string;
  url:           string;
  nlp_score:     number;
  decision:      CandidateDecision;
  nlp_breakdown: Record<string, number>;
  ts:            number;
}

export interface NodeDetailRecord {
  node_id:           string;
  nlp_score:         number | null;
  nlp_breakdown:     Record<string, number>;
  llm_score:         number | null;
  priority:          number | null;
  priority_strategy: string | null;
}

export interface ErrorRecord {
  node_id:       string | null;
  stage:         string;
  error_type:    string;
  error_message: string;
  ts:            number;
}

export interface ScoredChild {
  url:      string;
  score:    number;
  priority: number;
}


// ─── Message types ────────────────────────────────────────────────────────────

/**
 * Sent exactly once, immediately after a client connects.
 * Contains the full state of the crawl at that moment.
 * Use this to hydrate the UI from scratch.
 */
export interface SnapshotFullMsg {
  type:        "SNAPSHOT_FULL";
  status:      "RUNNING" | "STOPPED";
  stop_reason: string | null;
  metrics:     CrawlMetrics;
  nodes:       NodeRecord[];
  pipeline_stats: Record<PipelineStage, PipelineStat>;
  candidates:     CandidateRecord[];
  node_details:   Record<string, NodeDetailRecord>;
  errors:         ErrorRecord[];
}

/**
 * A new node entered the crawl graph.
 * Use to add a vertex to the force-directed graph.
 */
export interface NodeAddedMsg {
  type: "NODE_ADDED";
  ts:   number;
  node: NodeRecord;
}

/**
 * An existing node advanced to the next lifecycle state.
 * Optional fields are present only for the states that produce them.
 */
export interface NodeStateChangedMsg {
  type:    "NODE_STATE_CHANGED";
  ts:      number;
  node_id: string;
  state:   NodeState;

  // FILTERED state extras
  links_accepted?: number;
  links_rejected?: number;
  items_accepted?: number;

  // SCORED state extras
  scored_count?: number;
}

/**
 * A node was scored and its high-value children were resolved.
 * Use to add edges to the force-directed graph.
 */
export interface NodeExpandedMsg {
  type:           "NODE_EXPANDED";
  ts:             number;
  parent_id:      string;
  children_count: number;
  children:       ScoredChild[];
}

/**
 * The crawl has terminated (any reason).
 * After this message no further domain messages will arrive.
 */
export interface CrawlStoppedMsg {
  type:       "CRAWL_STOPPED";
  ts:         number;
  reason:     string;
  node_count: number;
  max_depth:  number;
  duration:   number;          // seconds
  detail:     string | null;
  metrics:    CrawlMetrics;
}


/**
 * One pipeline stage ticked (enqueued / started / completed / failed).
 * node_id is null for table-level export ticks.
 */
export interface PipelineEventMsg {
  type:        "PIPELINE_EVENT";
  ts:          number;
  stage:       PipelineStage;
  phase:       string;
  node_id:     string | null;
  worker_id:   number | string | null;
  queue_size:  number | null;
  duration_ms: number | null;
  detail:      string | null;
}

/**
 * Links the scoring cascade decided on without an LLM call. Both decisions
 * are sent here; only "trusted_no_llm" candidates go on to become nodes.
 */
export interface CandidateEvaluatedMsg {
  type:       "CANDIDATE_EVALUATED";
  ts:         number;
  parent_id:  string;
  decision:   CandidateDecision;
  candidates: {
    url:           string;
    nlp_score:     number;
    nlp_breakdown: Record<string, number>;
  }[];
}

/**
 * The cascade's explanation for a node's score. Sent right after the
 * NODE_ADDED it belongs to.
 */
export interface NodeScoredDetailMsg extends NodeDetailRecord {
  type: "NODE_SCORED_DETAIL";
  ts:   number;
}

/** A stage failed. node_id is null for crawl-wide or table-level failures. */
export interface NodeErrorMsg {
  type:          "NODE_ERROR";
  ts:            number;
  node_id:       string | null;
  stage:         string;
  error_type:    string;
  error_message: string;
}


// ─── Subsystem status (ADR 8) ─────────────────────────────────────────────────
//
// Source of truth: src/crawlviz/contracts/subsystem_status.py and
// status_messages.py. tests/test_wire_protocol.py fails when these
// declarations and the pydantic models disagree.
//
// Reasons are codes, never sentences: the UI catalog turns them into words.
// "waiting" and "failed" always carry a reason; retry_at is set only while
// "waiting". Times are unix seconds.

export type SubsystemName = "embedder" | "space" | "llm" | "fetch" | "robots" | "export";

export type SubsystemState = "off" | "starting" | "ready" | "waiting" | "failed";

export type CrawlState =
  | "idle"
  | "starting"
  | "running"
  | "stopping"
  | "stopped"
  | "finished"
  | "failed";

export interface EmbedderFacts {
  model:      string | null;
  device:     string | null;
  dimensions: number | null;
}

export interface SpaceFacts {
  vectors:           number | null;
  loaded_from_store: boolean | null;
}

/** Counter names match the LLM call totals; budget_calls is null when uncapped. */
export interface LlmFacts {
  provider:           string | null;
  model:              string | null;
  calls:              number;
  budget_calls:       number | null;
  calls_refused:      number;
  cache_hits:         number;
  failed_calls:       number;
  input_tokens:       number;
  output_tokens:      number;
  estimated_cost_usd: number | null;
  in_flight:          number;
  outcomes:           Record<string, number>;   // keyed by call outcome code
}

export interface FetchFacts {
  in_flight:         number;
  pages_fetched:     number;
  hosts_backing_off: number;
  retries_pending:   number;
}

export interface RobotsFacts {
  hosts_checked: number;
  hosts_blocked: number;
  crawl_delay_s: number | null;
}

export interface ExportFacts {
  rows_written: number;
  rows_failed:  number;
}

export interface SubsystemEntryBase {
  state:    SubsystemState;
  since:    number;
  retry_at: number | null;
}

export interface EmbedderStatus extends SubsystemEntryBase {
  subsystem: "embedder";
  reason:    "loading_model" | "model_missing" | "load_failed" | null;
  facts:     EmbedderFacts;
}

export interface SpaceStatus extends SubsystemEntryBase {
  subsystem: "space";
  reason:    "waiting_for_embedder" | "loading_saved" | "building" | "build_failed" | null;
  facts:     SpaceFacts;
}

export interface LlmStatus extends SubsystemEntryBase {
  subsystem: "llm";
  reason:    "keys_missing" | "rate_limited" | "budget_exhausted" | "provider_error" | null;
  facts:     LlmFacts;
}

export interface FetchStatus extends SubsystemEntryBase {
  subsystem: "fetch";
  reason:    "rate_limited" | "backing_off" | "network_errors" | null;
  facts:     FetchFacts;
}

export interface RobotsStatus extends SubsystemEntryBase {
  subsystem: "robots";
  reason:    "loading_rules" | "rules_unavailable" | null;
  facts:     RobotsFacts;
}

export interface ExportStatus extends SubsystemEntryBase {
  subsystem: "export";
  reason:    "write_failed" | null;
  facts:     ExportFacts;
}

export type SubsystemStatus =
  | EmbedderStatus
  | SpaceStatus
  | LlmStatus
  | FetchStatus
  | RobotsStatus
  | ExportStatus;

/** Every subsystem's entry, in SubsystemName order. */
export interface StatusBoardSnapshot {
  subsystems: Record<SubsystemName, SubsystemStatus>;
}

/**
 * One subsystem's entry changed. Replace that subsystem's entry with
 * `entry`; never merge fields. Sent at most every 250 ms per subsystem.
 */
export interface SubsystemStatusMsg {
  type:  "SUBSYSTEM_STATUS";
  ts:    number;
  entry: SubsystemStatus;
}


// ─── Discriminated union ──────────────────────────────────────────────────────

export type CrawlMessage =
  | SnapshotFullMsg
  | NodeAddedMsg
  | NodeStateChangedMsg
  | NodeExpandedMsg
  | CrawlStoppedMsg
  | PipelineEventMsg
  | CandidateEvaluatedMsg
  | NodeScoredDetailMsg
  | NodeErrorMsg
  | SubsystemStatusMsg;


// ─── React integration ────────────────────────────────────────────────────────

/*

*/
