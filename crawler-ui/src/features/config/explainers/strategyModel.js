// Priority of a link under a strategy's weights. Mirrors priority/strategy.py `_score`.

export const FEATURES = [
  "target_similarity", "novelty_injection", "coverage_gap", "contextual_consistency",
  "lexical_overlap", "cluster_distance", "semantic_delta",
];

/** Weight keys the backend accepts besides FEATURES and the depth penalty. */
export const EXTRA_FEATURES = ["region_density", "anchor_similarity", "parent_relevance", "boilerplate_score"];

/** Per-part contribution to one link's priority; `total` is clamped at 0 and rounded like Python. */
export function priorityParts(link, weights, nlpBias, llmBias) {
  const parts = Object.entries(weights)
    .filter(([key]) => key !== "depth_penalty")
    .map(([key, w]) => ({ key, value: nlpBias * w * (link.features[key] ?? 0) }));
  const depth = nlpBias * -(link.depth * (weights.depth_penalty ?? 0));
  const llm = llmBias * Math.max(0, Math.min(1, link.llm ?? 0));
  const raw = parts.reduce((a, p) => a + p.value, 0) + depth + llm;
  return { parts, depth, llm, total: Math.round(Math.max(0, raw) * 1e6) / 1e6 };
}


/** Link indices best first; ties keep their original order. */
export function rank(links, weights, nlpBias, llmBias) {
  return links
    .map((l, i) => ({ i, p: priorityParts(l, weights, nlpBias, llmBias).total }))
    .sort((a, b) => b.p - a.p || a.i - b.i)
    .map((x) => x.i);
}
