import { INITIAL_STATE, SNAPSHOT_INTERVAL, MAX_CANDIDATES, MAX_ERRORS } from "./initialState";

// ─────────────────────────────────────────────────────────────
// Pure event application (NO metrics, NO derived state)
//
// Every case here follows the same immutable-update discipline the V1
// reducer already used (new Map/Set/object on every change, never mutate
// in place) -- that discipline is *why* the checkpointing below can get
// away with storing plain references instead of deep-cloning: a past
// `state` value can never change out from under a stored checkpoint.
// ─────────────────────────────────────────────────────────────

export function applyEvent(state, event) {
  switch (event.type) {

    case "SNAPSHOT_FULL": {
      const nodes = new Map();
      (event.nodes || []).forEach(n => {
        nodes.set(n.node_id, { ...n });
      });

      // V2: hydrate the telemetry slices too, so a client that connects
      // mid-crawl catches up on pipeline/candidate/error state and not
      // just the node graph (docs/V2_ARCHITECTURE.md §B.2.1).
      const pipelineStats = {};
      Object.entries(event.pipeline_stats || {}).forEach(([stage, s]) => {
        const completed = s.completed || 0;
        pipelineStats[stage] = {
          ...s,
          // Reconstructed running sum so subsequent live PIPELINE_EVENT
          // ticks blend into this average instead of discarding pre-join
          // history (the backend snapshot only carries the derived
          // average, not the raw sum/count it was built from).
          _totalDuration: (s.avg_duration_ms || 0) * completed,
          _samples: completed,
        };
      });

      const candidates = (event.candidates || []).slice(-MAX_CANDIDATES).map(c => ({ ...c }));

      const nodeDetails = {};
      Object.entries(event.node_details || {}).forEach(([id, d]) => {
        nodeDetails[id] = { ...d };
      });

      const errors = (event.errors || []).slice(-MAX_ERRORS).map(e => ({ ...e }));

      return {
        ...state,
        nodes,
        edges: new Set(),
        status: event.status || "RUNNING",
        stop_reason: event.stop_reason || null,
        metrics: event.metrics || state.metrics,
        pipelineStats,
        candidates,
        nodeDetails,
        errors,
      };
    }

    case "NODE_ADDED": {
      if (!event.node?.node_id) return state;

      const nodes = new Map(state.nodes);
      const edges = new Set(state.edges);

      const node = { ...event.node };
      const nodeId = node.node_id;
      const parentId = node.parent_id;

      nodes.set(nodeId, node);

      if (parentId) {
        edges.add(`${parentId}→${nodeId}`);
      }

      return { ...state, nodes, edges };
    }

    case "NODE_STATE_CHANGED": {
      if (!event.node_id) return state;

      const existing = state.nodes.get(event.node_id);
      if (!existing) return state;

      const nodes = new Map(state.nodes);

      nodes.set(event.node_id, {
        ...existing,
        state: event.state,
        links_accepted: event.links_accepted ?? existing.links_accepted,
        links_rejected: event.links_rejected ?? existing.links_rejected,
        items_accepted: event.items_accepted ?? existing.items_accepted,
        scored_count: event.scored_count ?? existing.scored_count,
      });

      return { ...state, nodes };
    }

    case "NODE_EXPANDED": {
      if (!event.parent_id) return state;

      const nodes = new Map(state.nodes);
      const parent = nodes.get(event.parent_id);

      if (parent) {
        nodes.set(event.parent_id, {
          ...parent,
          state: "EXPANDED",
        });
      }

      return { ...state, nodes };
    }

    case "CRAWL_STOPPED": {
      return {
        ...state,
        status: "STOPPED",
        stop_reason: event.reason ?? event.stop_reason ?? null,
        metrics: event.metrics || state.metrics,
      };
    }

    // ─────────────────────────────────────────────────────────
    // V2 additions
    // ─────────────────────────────────────────────────────────

    case "PIPELINE_EVENT": {
      const stage = event.stage;
      if (!stage) return state;

      const prev = state.pipelineStats[stage] || {
        started: 0, completed: 0, failed: 0, queue_size: 0,
        last_duration_ms: null, avg_duration_ms: null,
        _totalDuration: 0, _samples: 0,
      };
      const next = { ...prev };

      if (event.phase === "enqueued") {
        if (event.queue_size != null) next.queue_size = event.queue_size;
      } else if (event.phase === "started") {
        next.started = prev.started + 1;
      } else if (event.phase === "completed") {
        next.completed = prev.completed + 1;
        if (event.duration_ms != null) {
          next.last_duration_ms = event.duration_ms;
          next._totalDuration = (prev._totalDuration || 0) + event.duration_ms;
          next._samples = (prev._samples || 0) + 1;
          next.avg_duration_ms = next._totalDuration / next._samples;
        }
      } else if (event.phase === "failed") {
        next.failed = prev.failed + 1;
      }

      return { ...state, pipelineStats: { ...state.pipelineStats, [stage]: next } };
    }

    case "CANDIDATE_EVALUATED": {
      if (!event.candidates?.length) return state;

      const additions = event.candidates.map(c => ({
        parent_id: event.parent_id,
        decision: event.decision,
        url: c.url,
        nlp_score: c.nlp_score,
        nlp_breakdown: c.nlp_breakdown,
        ts: event.ts,
      }));

      let candidates = state.candidates.concat(additions);
      if (candidates.length > MAX_CANDIDATES) {
        candidates = candidates.slice(candidates.length - MAX_CANDIDATES);
      }
      return { ...state, candidates };
    }

    case "NODE_SCORED_DETAIL": {
      if (!event.node_id) return state;
      const { type, ts, ...detail } = event; // eslint-disable-line no-unused-vars
      return { ...state, nodeDetails: { ...state.nodeDetails, [event.node_id]: detail } };
    }

    case "NODE_ERROR": {
      const entry = {
        node_id: event.node_id ?? null,
        stage: event.stage,
        error_type: event.error_type,
        error_message: event.error_message,
        ts: event.ts,
      };
      let errors = state.errors.concat([entry]);
      if (errors.length > MAX_ERRORS) errors = errors.slice(errors.length - MAX_ERRORS);
      return { ...state, errors };
    }

    // Socket health is tracked separately from crawl lifecycle (`status`)
    // -- V1 appended these to the event log for the timeline to show but
    // never actually updated any state, so a dropped connection during a
    // long crawl looked identical to a healthy one (docs/V2_ARCHITECTURE.md
    // §A.1.9).
    case "__WS_CONNECTED":
      return { ...state, connectionStatus: "CONNECTED" };
    case "__WS_DISCONNECTED":
      return { ...state, connectionStatus: "DISCONNECTED" };

    default:
      return state;
  }
}

// ─────────────────────────────────────────────────────────────
// Replay — checkpoint-assisted seeking
//
// V1 rebuilt state by replaying the *entire* event log from scratch on
// every seek, which is fine at a few hundred events and becomes the
// bottleneck on a real crawl's low thousands (docs/V2_ARCHITECTURE.md
// §A.1.8). `crawlReducer` below checkpoints a state reference every
// SNAPSHOT_INTERVAL events; replayTo() restores the nearest checkpoint at
// or before the target index and replays only the remainder.
// ─────────────────────────────────────────────────────────────

function replayTo(state, index) {
  const clampedIndex = Math.max(-1, Math.min(index, state.eventLog.length - 1));

  let startIndex = -1;
  let base = { ...INITIAL_STATE, eventLog: state.eventLog, _checkpoints: state._checkpoints };

  // Checkpoints are stored in increasing index order and there are at
  // most (eventLog.length / SNAPSHOT_INTERVAL) of them -- a linear scan
  // from the end is simple and, at realistic crawl sizes, effectively
  // instant; this isn't a hot path frequent enough to justify a binary
  // search over a list that's a few dozen entries long even for a huge crawl.
  for (let i = state._checkpoints.length - 1; i >= 0; i--) {
    const cp = state._checkpoints[i];
    if (cp.index <= clampedIndex) {
      base = { ...cp.state, eventLog: state.eventLog, _checkpoints: state._checkpoints };
      startIndex = cp.index;
      break;
    }
  }

  let result = base;
  for (let i = startIndex + 1; i <= clampedIndex; i++) {
    result = applyEvent(result, state.eventLog[i]);
  }

  return result;
}

// ─────────────────────────────────────────────────────────────
// Reducer -- every WS event and the replay controls flow through here
// ─────────────────────────────────────────────────────────────

export function crawlReducer(state, action) {

  // ── Replay forward up to index ─────────────────────────────
  if (action.type === "__REPLAY_SEEK") {
    const replayed = replayTo(state, action.index);
    return {
      ...replayed,
      eventLog: state.eventLog,
      _checkpoints: state._checkpoints,
      _replayIndex: action.index,
    };
  }

  // ── Exit replay → rebuild live state ───────────────────────
  if (action.type === "__REPLAY_EXIT") {
    const live = replayTo(state, state.eventLog.length - 1);
    return {
      ...live,
      eventLog: state.eventLog,
      _checkpoints: state._checkpoints,
      _replayIndex: null,
    };
  }

  // ── Normal event append ────────────────────────────────────
  const next = applyEvent(state, action);

  const entry = {
    ...action,
    _receivedAt: action._receivedAt ?? Date.now(),
  };

  const eventLog = [...state.eventLog, entry];

  // Checkpoint every SNAPSHOT_INTERVAL live events. The checkpoint stores
  // a *reference* to `next` (not a clone) -- safe because every case above
  // already returns a fresh object/Map/Set rather than mutating `state`,
  // so this reference can never be invalidated by a later action.
  let _checkpoints = state._checkpoints;
  if (eventLog.length % SNAPSHOT_INTERVAL === 0) {
    _checkpoints = [...state._checkpoints, { index: eventLog.length - 1, state: next }];
  }

  return {
    ...next,
    eventLog,
    _checkpoints,
    _replayIndex: null,
  };
}
