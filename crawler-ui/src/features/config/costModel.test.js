import { describe, it, expect } from "vitest";
import { llmCost } from "./costModel";
import sample from "./explainers/sampleData.json";
import { cascadeCounts } from "./explainers/cascadeModel";
import { estimateTokens } from "./promptModel";

const cascade = {
  percentile_bucketing: false,
  low_threshold: 0.2,
  high_threshold: 0.75,
  high_score_llm_fraction: 0.5,
  high_score_random_fraction: 0.2,
  low_score_sample_fraction: 0.1,
  low_percentile: 20,
  high_percentile: 75,
  percentile_min_links: 10,
  max_llm_links_per_node: 100,
  llm_batch_size: null,
};
const nlp = { link_context_length: 100 };
const llm = { max_calls_per_crawl: null };
const prompts = { scoring_system: "a".repeat(400), scoring_rules: "b".repeat(400) };
const scores = sample.cascadeScores;
const toLlm = cascadeCounts(scores, { ...cascade, max_llm_links: 100 }).toLlm;

describe("llmCost", () => {
  it("counts the links the cascade sends to the LLM", () => {
    expect(llmCost({ cascade, nlp, llm, prompts, scores }).linksToLlm).toBe(toLlm);
  });

  it("makes one call per page when no batch size is set", () => {
    expect(llmCost({ cascade, nlp, llm, prompts, scores }).callsPerPage).toBe(toLlm === 0 ? 0 : 1);
  });

  it("splits a page into batches of llm_batch_size", () => {
    const c = llmCost({ cascade: { ...cascade, llm_batch_size: 2 }, nlp, llm, prompts, scores });
    expect(c.callsPerPage).toBe(Math.ceil(toLlm / 2));
  });

  it("adds prompt tokens per call and context tokens per link", () => {
    const one = llmCost({ cascade: { ...cascade, llm_batch_size: 1 }, nlp, llm, prompts, scores });
    const promptTokens = estimateTokens(`${prompts.scoring_system}\n${prompts.scoring_rules}`);
    const linkTokens = Math.ceil((100 + 80) / 4);
    expect(one.tokensPerPage).toBe(one.callsPerPage * promptTokens + toLlm * linkTokens);
  });

  it("says how many pages fit under a per-crawl call cap", () => {
    const perPage = llmCost({ cascade, nlp, llm, prompts, scores }).callsPerPage;
    const c = llmCost({ cascade, nlp, llm: { max_calls_per_crawl: 10 }, prompts, scores });
    expect(c.cap).toBe(10);
    expect(c.pagesWithinCap).toBe(perPage ? Math.floor(10 / perPage) : null);
  });

  it("has no page count when there is no cap", () => {
    expect(llmCost({ cascade, nlp, llm, prompts, scores }).pagesWithinCap).toBeNull();
  });
});
