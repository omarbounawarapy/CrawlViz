import { useEffect } from "react";

// Synthetic sample crawl (clearly labelled as such in the UI). A fixed tree
// so every encoding is exercised: nodes stop at different lifecycle stages,
// relevance spans the range, and the cascade skips or fast-tracks links.
//
// [slug, parent slug | null, final state, LLM score | null, NLP score]
const TREE = [
  ["Black_hole",            null,                   "EXPANDED", 92, 0.81],
  ["Event_horizon",         "Black_hole",           "EXPANDED", 88, 0.77],
  ["Hawking_radiation",     "Black_hole",           "EXPANDED", 85, 0.74],
  ["Schwarzschild_metric",  "Event_horizon",        "SCORED",   79, 0.69],
  ["Accretion_disk",        "Black_hole",           "EXPANDED", 74, 0.66],
  ["Singularity",           "Event_horizon",        "FILTERED", 71, 0.62],
  ["Information_paradox",   "Hawking_radiation",    "SCORED",   83, 0.72],
  ["Quasar",                "Accretion_disk",       "FILTERED", 58, 0.55],
  ["Neutron_star",          "Black_hole",           "SCORED",   63, 0.58],
  ["Gravitational_waves",   "Black_hole",           "EXPANDED", 81, 0.73],
  ["LIGO",                  "Gravitational_waves",  "FETCHED",  54, 0.49],
  ["Virgo_interferometer",  "Gravitational_waves",  "CREATED",  null, 0.47],
  ["Stellar_evolution",     "Neutron_star",         "FETCHED",  41, 0.44],
  ["White_dwarf",           "Stellar_evolution",    "CREATED",  null, 0.39],
  ["Dark_matter",           "Quasar",               "CREATED",  null, 0.36],
  ["Wormhole",              "Singularity",          "FILTERED", 46, 0.43],
  ["Science_fiction",       "Wormhole",             "CREATED",  null, 0.22],
];

// Links the cascade evaluated but never fetched: [parent, url, decision, NLP]
const CANDIDATES = [
  ["Black_hole",          "Interstellar_(film)",  "dropped",        0.12],
  ["Black_hole",          "List_of_video_games",  "dropped",        0.06],
  ["Black_hole",          "Kip_Thorne",           "trusted_no_llm", 0.84],
  ["Event_horizon",       "Event_Horizon_(film)", "dropped",        0.09],
  ["Hawking_radiation",   "Stephen_Hawking",      "trusted_no_llm", 0.88],
  ["Hawking_radiation",   "Steven_Seagal",        "dropped",        0.03],
  ["Gravitational_waves", "Nobel_Prize",          "dropped",        0.18],
  ["Gravitational_waves", "Rainer_Weiss",         "trusted_no_llm", 0.82],
  ["Accretion_disk",      "Saturn",               "dropped",        0.15],
  ["Neutron_star",        "Pulsar",               "trusted_no_llm", 0.79],
  ["Wormhole",            "Star_Trek",            "dropped",        0.05],
];

const STAGES = ["CREATED", "FETCHED", "FILTERED", "SCORED", "EXPANDED"];
const url = (slug) => `/wiki/${slug}`;

export function useDemoMode(dispatch, enabled) {
  useEffect(() => {
    if (!enabled) return;

    const timers = [];
    const at = (ms, fn) => timers.push(setTimeout(fn, ms));
    const now = () => Date.now() / 1000;
    const base = { _receivedAt: undefined };
    const emit = (ev) => dispatch({ ...base, ts: now(), _receivedAt: Date.now(), ...ev });

    at(150, () => emit({
      type: "SNAPSHOT_FULL", status: "RUNNING", stop_reason: null, nodes: [],
      metrics: {
        nodes_created: 0, nodes_fetched: 0, nodes_filtered: 0, nodes_scored: 0, nodes_expanded: 0,
        total_links_found: 0, total_items_stored: 0, start_time: now(), elapsed_seconds: 0,
      },
    }));

    TREE.forEach(([slug, parent, finalState, llm, nlp], i) => {
      const t0 = 400 + i * 450;
      const id = url(slug);

      at(t0, () => emit({
        type: "NODE_ADDED",
        node: {
          node_id: id, url: id, depth: parent ? 1 + TREE.findIndex(n => n[0] === parent) % 3 : 0,
          priority: llm != null ? llm * 1.6 : nlp * 60, llm_score: llm,
          parent_id: parent ? url(parent) : null, state: "CREATED", created_at: now(),
        },
      }));

      STAGES.slice(1, STAGES.indexOf(finalState) + 1).forEach((state, j) => {
        at(t0 + (j + 1) * 500, () => emit({
          type: "NODE_STATE_CHANGED", node_id: id, state,
          links_accepted: state === "FILTERED" ? 4 + (i % 7) : undefined,
          links_rejected: state === "FILTERED" ? 1 + (i % 4) : undefined,
        }));
      });

      if (parent) {
        at(t0 + 700, () => emit({
          type: "NODE_SCORED_DETAIL", node_id: id, nlp_score: nlp, llm_score: llm,
          priority: llm != null ? llm * 1.6 : nlp * 60, priority_strategy: "PATHFINDING",
          nlp_breakdown: {
            target_similarity: nlp, contextual_consistency: nlp * 0.8, novelty_injection: 0.1 + (i % 4) * 0.05,
            lexical_overlap: nlp * 0.6, semantic_delta: -0.1 * (i % 3),
          },
        }));
      }
    });

    CANDIDATES.forEach(([parent, link, decision, nlp], i) => {
      at(900 + i * 700, () => emit({
        type: "CANDIDATE_EVALUATED", parent_id: url(parent), decision,
        candidates: [{ url: `/wiki/${link}`, nlp_score: nlp }],
      }));
    });

    return () => timers.forEach(clearTimeout);
  }, [dispatch, enabled]);
}
