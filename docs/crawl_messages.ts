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
  | NodeErrorMsg;


// ─── React integration ────────────────────────────────────────────────────────

/*

*/
