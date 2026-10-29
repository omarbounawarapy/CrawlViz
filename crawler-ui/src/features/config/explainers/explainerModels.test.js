import { describe, it, expect } from "vitest";
import cases from "./fixtures/python_cases.json";
import sample from "./sampleData.json";
import { cascadeCounts } from "./cascadeModel";
import { priorityParts } from "./strategyModel";
import { simulate, scenario, summary } from "./backoffModel";
import { clusterAngles, linkContext, topKMean } from "./topkModel";

// The fixtures are written by tools/gen_explainer_fixtures.py from the Python code itself.

describe("cascadeCounts", () => {
  cases.cascade.forEach((c, i) => {
    it(`case ${i} matches ScoringPipeline.bucket_links`, () => {
      const got = cascadeCounts(c.scores, c.config);
      expect({ toLlm: got.toLlm, trusted: got.trusted, dropped: got.dropped }).toEqual(c.expected);
    });
  });
  it("accounts for every link", () => {
    const g = cascadeCounts(sample.cascadeScores, {
      low_threshold: 0.2,
      high_threshold: 0.75,
      high_score_llm_fraction: 0.3,
      low_score_sample_fraction: 0.1,
      high_score_random_fraction: 0.25,
    });
    expect(g.toLlm + g.trusted + g.dropped).toBe(g.total);
  });
});

describe("priorityParts", () => {
  const defaults = {
    aggressive: {
      target_similarity: 0.4,
      coverage_gap: 0.15,
      novelty_injection: 0.1,
      contextual_consistency: 0.05,
      depth_penalty: 0.08,
    },
    balanced: {
      target_similarity: 0.25,
      novelty_injection: 0.2,
      coverage_gap: 0.15,
      contextual_consistency: 0.1,
      lexical_overlap: 0.05,
      depth_penalty: 0.05,
    },
    exploration: {
      novelty_injection: 0.35,
      cluster_distance: 0.25,
      coverage_gap: 0.2,
      target_similarity: 0.05,
      semantic_delta: 0.05,
      depth_penalty: 0.03,
    },
  };
  cases.strategy.forEach((c, i) => {
    it(`case ${i} (${c.strategy}) matches priority/strategy.py`, () => {
      const w = c.weights ?? defaults[c.strategy];
      const got = sample.strategyLinks.map((l) => priorityParts(l, w, c.nlpBias, c.llmBias).total);
      got.forEach((v, j) => expect(v).toBeCloseTo(c.scores[j], 5));
    });
  });
});

describe("backoff simulate", () => {
  cases.backoff.forEach((c, i) => {
    it(`case ${i} matches the request worker loop`, () => {
      const { waits } = simulate(c.outcomes, c.config, 0);
      expect(waits.length).toBe(c.delays.length);
      waits.forEach((w, j) => expect(Math.abs(w - c.delays[j])).toBeLessThan(0.011));
    });
  });
  it("reports the worst case as min delay + backoff cap + jitter", () => {
    const s = summary({ min_delay: 1, jitter_max: 0.2, backoff_max: 10 });
    expect(s.worstWait).toBeCloseTo(11.2);
    expect(s.steadyRate).toBeGreaterThan(0.5);
  });
  it("builds a burst scenario", () => {
    expect(scenario(10, 3, 2)).toEqual(["ok", "ok", "429", "429", "429", "ok", "ok", "ok", "ok", "ok"]);
  });
});

describe("NLP illustrations", () => {
  it("clusterAngles equals sklearn DBSCAN with cosine distance", () => {
    cases.cluster.forEach((c) => {
      expect(clusterAngles(sample.cluster.angles, c.eps, c.minSamples)).toEqual(c.labels);
    });
  });
  it("linkContext equals the extractor for each limit", () => {
    cases.context.forEach((c) => {
      expect(linkContext(sample.context.text, sample.context.anchor, c.limit)).toBe(c.context);
    });
  });
  it("topKMean averages the k nearest", () => {
    expect(topKMean([0.9, 0.5, 0.1], 2)).toBeCloseTo(0.7);
    expect(topKMean([0.9, 0.5, 0.1], 1)).toBeCloseTo(0.9);
    expect(topKMean([0.9, 0.5, 0.1], 9)).toBeCloseTo(0.5);
  });
});
