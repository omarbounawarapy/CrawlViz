// The LLM calls a whole crawl may make, for pages that call the LLM the way the
// example page does. Used where a crawl is about to start (Run, Blueprints review).
import { useEffect, useState } from "react";
import { fetchConfig } from "../../api/client";
import { llmCost } from "./costModel";
import sample from "./explainers/sampleData.json";

/** Calls and tokens for `pages` pages, capped by the per-crawl call limit. */
export function crawlEstimate(cost, pages) {
  const perPage = cost.callsPerPage;
  const raw = perPage * pages;
  const calls = cost.cap === null ? raw : Math.min(raw, cost.cap);
  return { calls, tokens: cost.tokensPerPage * pages, capped: cost.cap !== null && raw > cost.cap };
}

/** The estimate for `pages` pages under the saved settings; null until they have loaded. */
export function useCrawlCost(pages) {
  const [cost, setCost] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((cfg) => !cancelled && setCost(llmCost({
        cascade: cfg.scoring_cascade, nlp: cfg.nlp, llm: cfg.llm, prompts: cfg.prompts,
        scores: sample.cascadeScores,
      })))
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  if (!cost || !Number.isFinite(Number(pages))) return null;
  return crawlEstimate(cost, Number(pages));
}
