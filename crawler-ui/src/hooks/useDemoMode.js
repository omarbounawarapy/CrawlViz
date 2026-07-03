import { useEffect } from "react";
import { NODE_STATES } from "../state/constants";

const DEMO_URLS = [
  "/wiki/Black_hole",
  "/wiki/C%2B%2B",
  "/wiki/Computer_science",
  "/wiki/Algorithm",
  "/wiki/Graph_theory",
  "/wiki/Compiler",
  "/wiki/Programming_language",
  "/wiki/Turing_machine",
  "/wiki/Recursion",
  "/wiki/Data_structure",
];

export function useDemoMode(dispatch, enabled) {
  useEffect(() => {
    if (!enabled) return;

    const urls   = DEMO_URLS;
    const timers = [];

    // Seed snapshot
    timers.push(setTimeout(() => {
      dispatch({
        type:        "SNAPSHOT_FULL",
        status:      "RUNNING",
        stop_reason: null,
        metrics: {
          nodes_created:      0,
          nodes_fetched:      0,
          nodes_filtered:     0,
          nodes_scored:       0,
          nodes_expanded:     0,
          total_links_found:  0,
          total_items_stored: 0,
          start_time:         Date.now() / 1000,
          elapsed_seconds:    0,
        },
        nodes:       [],
        _receivedAt: Date.now(),
      });
    }, 200));

    // Inject nodes progressively
    urls.forEach((url, i) => {
      const delay = 600 + i * 700;

      timers.push(setTimeout(() => {
        dispatch({
          type:        "NODE_ADDED",
          ts:          Date.now() / 1000,
          _receivedAt: Date.now(),
          node: {
            node_id:    url,
            url,
            depth:      i === 0 ? 0 : Math.floor(Math.random() * 3) + 1,
            priority:   Math.random() * 100,
            llm_score:  Math.random() * 100,
            parent_id:  i === 0 ? null : urls[Math.floor(Math.random() * i)],
            state:      "CREATED",
            created_at: Date.now() / 1000,
          },
        });
      }, delay));

      // State transitions
      NODE_STATES.slice(1).forEach((state, j) => {
        timers.push(setTimeout(() => {
          dispatch({
            type:           "NODE_STATE_CHANGED",
            ts:             Date.now() / 1000,
            _receivedAt:    Date.now(),
            node_id:        url,
            state,
            links_accepted: state === "FILTERED" ? Math.floor(Math.random() * 20) : undefined,
            links_rejected: state === "FILTERED" ? Math.floor(Math.random() * 5)  : undefined,
          });
        }, delay + (j + 1) * 800));
      });

      // Expand some nodes
      if (i < 4) {
        timers.push(setTimeout(() => {
          dispatch({
            type:           "NODE_EXPANDED",
            ts:             Date.now() / 1000,
            _receivedAt:    Date.now(),
            parent_id:      url,
            children_count: 2,
            children: [
              { url: urls[(i + 3) % urls.length], score: Math.random() * 100, priority: Math.random() * 200 },
              { url: urls[(i + 5) % urls.length], score: Math.random() * 100, priority: Math.random() * 200 },
            ],
          });
        }, delay + 4200));
      }
    });

    // Stop
    timers.push(setTimeout(() => {
      dispatch({
        type:        "CRAWL_STOPPED",
        ts:          Date.now() / 1000,
        _receivedAt: Date.now(),
        reason:      "MAX_NODES_REACHED",
        node_count:  urls.length,
        max_depth:   3,
        duration:    12.4,
        detail:      null,
        metrics: {
          nodes_created:      urls.length,
          nodes_fetched:      urls.length,
          nodes_filtered:     urls.length,
          nodes_scored:       urls.length,
          nodes_expanded:     4,
          total_links_found:  38,
          total_items_stored: 92,
          start_time:         (Date.now() - 12400) / 1000,
          elapsed_seconds:    12.4,
        },
      });
    }, 600 + urls.length * 700 + 5000));

    return () => timers.forEach(clearTimeout);
  }, [dispatch, enabled]);
}