// What the LLM side of a crawl costs, for the example page and for a whole crawl.
// Links to the LLM come from the same cascade counts the funnel draws
// (cascadeModel.js); tokens are a rough estimate from the prompt wording and the
// text of each candidate link. Both are labelled as estimates where they are shown.
import { cascadeCounts } from "./explainers/cascadeModel";
import { estimateTokens } from "./promptModel";

// URL, anchor text and separators of one candidate, beyond its context text.
const LINK_CHARS = 80;

/**
 * `cascade`, `nlp`, `llm` and `prompts` are the draft's sections; `scores` are one
 * page's NLP scores. Returns calls and tokens for that page, and how many such
 * pages fit under the per-crawl call cap.
 */
export function llmCost({ cascade, nlp, llm, prompts, scores }) {
  const counts = cascadeCounts(scores, { ...cascade, max_llm_links: cascade.max_llm_links_per_node });
  const linksToLlm = counts.toLlm;
  const batch = cascade.llm_batch_size || Math.max(linksToLlm, 1);
  const callsPerPage = linksToLlm === 0 ? 0 : Math.ceil(linksToLlm / batch);
  const promptTokens = estimateTokens(`${prompts?.scoring_system ?? ""}\n${prompts?.scoring_rules ?? ""}`);
  const linkTokens = estimateTokens("x".repeat((nlp?.link_context_length ?? 0) + LINK_CHARS));
  const tokensPerPage = callsPerPage * promptTokens + linksToLlm * linkTokens;
  const cap = llm?.max_calls_per_crawl ?? null;
  return {
    total: scores.length,
    linksToLlm,
    callsPerPage,
    tokensPerPage,
    cap,
    pagesWithinCap: cap !== null && callsPerPage > 0 ? Math.floor(cap / callsPerPage) : null,
  };
}
