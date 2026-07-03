import { INITIAL_STATE } from "./initialState";

// ─────────────────────────────────────────────────────────────
// Pure event application (NO metrics, NO derived state)
// ─────────────────────────────────────────────────────────────

export function applyEvent(state, event) {
  switch (event.type) {

    case "SNAPSHOT_FULL": {
      const nodes = new Map();
      (event.nodes || []).forEach(n => {
        nodes.set(n.node_id, { ...n });
      });

      return {
        ...state,
        nodes,
        edges: new Set(),
        status: event.status || "RUNNING",
        stop_reason: event.stop_reason || null,
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
      };
    }

    default:
      return state;
  }
}

// ─────────────────────────────────────────────────────────────
// Reducer -- every WS event and the replay controls flow through here
// ─────────────────────────────────────────────────────────────

export function crawlReducer(state, action) {

  // ── Replay forward up to index ─────────────────────────────
  if (action.type === "__REPLAY_SEEK") {
    const slice = state.eventLog.slice(0, action.index + 1);

    const replayed = slice.reduce(
      (s, ev) => applyEvent(s, ev),
      { ...INITIAL_STATE, eventLog: state.eventLog }
    );

    return {
      ...replayed,
      eventLog: state.eventLog,
      _replayIndex: action.index,
    };
  }

  // ── Exit replay → rebuild live state ───────────────────────
  if (action.type === "__REPLAY_EXIT") {
    const live = state.eventLog.reduce(
      (s, ev) => applyEvent(s, ev),
      { ...INITIAL_STATE, eventLog: state.eventLog }
    );

    return {
      ...live,
      eventLog: state.eventLog,
      _replayIndex: null,
    };
  }

  // ── Normal event append ────────────────────────────────────
  const next = applyEvent(state, action);

  const entry = {
    ...action,
    _receivedAt: action._receivedAt ?? Date.now(),
  };

  return {
    ...next,
    eventLog: [...state.eventLog, entry],
    _replayIndex: null,
  };
}