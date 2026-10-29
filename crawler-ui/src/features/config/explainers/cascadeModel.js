// Counts for the cascade funnel. Mirrors ScoringPipeline.bucket_links
// (pipelines/scoring_pipeline.py); tested against fixtures the Python code wrote.

/** numpy.percentile with linear interpolation; `p` in 0-100. */
export function percentile(values, p) {
  const s = [...values].sort((a, b) => a - b);
  if (s.length === 0) return 0;
  const at = ((s.length - 1) * p) / 100;
  const lo = Math.floor(at);
  const hi = Math.ceil(at);
  return s[lo] + (s[hi] - s[lo]) * (at - lo);
}

/**
 * What the cascade does with a page whose links scored `scores`.
 * `cfg` uses the scoring-cascade field names; `max_llm_links` is
 * `max_llm_links_per_node` in the stored config.
 */
export function cascadeCounts(scores, cfg) {
  let lowCut = cfg.low_threshold;
  let highCut = cfg.high_threshold;
  const usedPercentiles = Boolean(cfg.percentile_bucketing) && scores.length >= (cfg.percentile_min_links ?? 10);
  if (usedPercentiles) {
    lowCut = percentile(scores, cfg.low_percentile);
    highCut = percentile(scores, cfg.high_percentile);
  }
  let low = 0,
    mid = 0,
    high = 0;
  scores.forEach((s) => {
    if (s < lowCut) low += 1;
    else if (s > highCut) high += 1;
    else mid += 1;
  });

  const lowKept = Math.min(Math.floor(low * cfg.low_score_sample_fraction), low);
  const highBudget = Math.min(Math.floor(high * cfg.high_score_llm_fraction), high);
  const highRandom = Math.min(Math.floor(highBudget * cfg.high_score_random_fraction), high);
  const highTop = Math.min(Math.max(highBudget - highRandom, 0), high - highRandom);
  const highTrusted = high - highRandom - highTop;

  let toLlm = lowKept + mid + highRandom + highTop;
  let capped = 0;
  const cap = cfg.max_llm_links ?? null;
  if (cap !== null && toLlm > cap) {
    capped = toLlm - cap;
    toLlm = cap;
  }
  return {
    total: scores.length,
    lowCut,
    highCut,
    usedPercentiles,
    low,
    mid,
    high,
    lowKept,
    lowDropped: low - lowKept,
    highRandom,
    highTop,
    highTrusted,
    capped,
    toLlm,
    trusted: highTrusted + capped,
    dropped: low - lowKept,
  };
}
