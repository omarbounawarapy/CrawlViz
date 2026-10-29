// Plain-language hints computed from the current draft. Each rule names the section it
// belongs to and, when it has a safe one-click fix, the values to set.

const RULES = [
  {
    id: "gentle-delay",
    section: "Fetch",
    when: (c) => c.fetch.min_delay < 1 && c.pipelines.requests.workers >= 4,
    text: (c) =>
      `A pause of ${c.fetch.min_delay}s with ${c.pipelines.requests.workers} request workers is fast enough to draw 429 responses from small sites.`,
    fix: { label: "Set the pause to 1 s", set: [["fetch.min_delay", 1]] },
  },
  {
    id: "ignore-robots",
    section: "Fetch",
    when: (c) => c.fetch.respect_robots === false,
    text: () => "Many sites block crawlers that ignore robots.txt, and doing so often breaks their terms.",
    fix: { label: "Honor robots.txt", set: [["fetch.respect_robots", true]] },
  },
  {
    id: "no-saving",
    section: "Scoring cascade",
    when: (c) => c.scoring_cascade.high_score_llm_fraction >= 1,
    text: () => "Every confident link still goes to the LLM, so the cascade saves no model calls on the high bucket.",
    fix: { label: "Send half", set: [["scoring_cascade.high_score_llm_fraction", 0.5]] },
  },
  {
    id: "unbounded-queue",
    section: "Pipelines",
    when: (c) => Object.values(c.pipelines).some((p) => p.max_queue_size == null && p.workers >= 16),
    text: (c) => {
      const names = Object.entries(c.pipelines)
        .filter(([, p]) => p.max_queue_size == null && p.workers >= 16)
        .map(([n]) => n);
      return `No queue limit with 16 or more workers (${names.join(", ")}) can let memory grow on a large crawl.`;
    },
  },
];

/** Suggestions that apply to `cfg`, minus the dismissed ids. */
export function suggest(cfg, dismissed = []) {
  if (!cfg) return [];
  return RULES.filter((r) => !dismissed.includes(r.id)).flatMap((r) => {
    try {
      return r.when(cfg) ? [{ id: r.id, section: r.section, text: r.text(cfg), fix: r.fix }] : [];
    } catch {
      return [];
    }
  });
}
