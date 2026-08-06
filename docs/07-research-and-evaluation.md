# Research & Evaluation

This documents the experimental protocol and results from the project report, clearly separated from architectural claims — this page describes what one measured run showed, not general performance guarantees.

## Research motivation

Unfocused crawling from a semantically rich seed drifts off-topic quickly because pure link-structure traversal (BFS/DFS) has no notion of meaning — the report's own example is a Wikipedia BFS from "Black Hole" reaching science-fiction and video-game pages within a few hops, because those topics are densely cross-linked to the seed despite being off-topic for someone looking for physics content. CrawlViz's research question, as posed in the report, is whether a hybrid local-embedding-plus-selective-LLM scoring cascade can keep exploration on-topic while keeping evaluation cost tractable.

## Experimental protocol

| Parameter | Value |
|---|---|
| Target domain | `wikimd.org` (a medical encyclopedia) |
| Seed | `/wiki/Diabetes` (framed around Type 2 Diabetes) |
| Max nodes | 600 |
| Max depth | 10 |
| Max time | 1200 s |
| Priority strategy | `AGGRESSIVE` |
| LLM scoring strategy | `TOPICAL` |
| LLM-generated expansions | 50 |
| Rate limit | 1 request/second/worker, 2 workers |

This exact configuration is checked into the repository as `templates/wikiMD.json` and matches the report's parameters field-for-field (topic, seed URL, scoring strategy, expansion count) — this is a live, runnable blueprint corresponding to the report's case study, not a description of a setup that no longer exists.

## Sequential vs. concurrent execution

| Approach | Nodes | Links discovered | Time |
|---|---|---|---|
| Sequential | 560 | 65,000 | 600+ s |
| Concurrent | 560 | 65,000 | 15 s |

Same work, ~40x wall-clock difference. This is presented in the report as the empirical justification for the asyncio architecture, not a theoretical claim about I/O-bound workloads in general — it's a measurement on this codebase specifically.

## Reference run results

| Metric | Value |
|---|---|
| Nodes explored | 539 |
| Links identified | 50,828 |
| Total duration | 1200 s (time limit reached) |

**Time decomposition.** The report separates total time into rate-limit-imposed waiting versus actual system work:

$$T_{\text{politeness}} = \frac{N}{w \cdot r} \qquad T_{\text{effective}} = T_{\text{total}} - T_{\text{politeness}}$$

With $N=539$ nodes, $w=2$ workers, $r=1$ req/s: $T_{\text{politeness}} \approx 270\text{s}$ (22.5% of the 1200s budget), leaving ~77.5% for fetching, NLP/LLM scoring, and event orchestration combined.

**Selectivity.** Of 50,828 links identified, 539 nodes (≈1%) were ultimately explored — the report frames this as evidence the scoring cascade substantially narrows the search space while retaining topically relevant material, which the qualitative graph structure (below) supports, though the report does not report a precision/recall figure against a ground-truth relevance labeling, so "narrows the space while retaining relevant material" is a structural/qualitative observation, not a measured precision metric.

**Qualitative structure.** The resulting graph organized into recognizable clusters — complications (neuropathy, retinopathy, nephropathy), treatments (insulin, metformin, semaglutide), and epidemiology/associated pathologies (obesity, metabolic syndrome) — connected by bridge nodes such as "Glycemic Index" and "HbA1c" that link across these sub-topic clusters. The report characterizes this as resembling the real organizational structure of the medical domain, which is a reasonable qualitative read of the described clustering, though it is the report's own interpretation rather than a metric computed against an external topic taxonomy.

## What this evaluation does and doesn't establish

**Established, with direct measurement:**
- Concurrent execution is dramatically faster than sequential for this workload, on this codebase.
- The cascade substantially reduces the fraction of discovered links that receive full exploration.
- A single reference run produces topically coherent, structurally sensible clustering.

**Not established by this evaluation, and shouldn't be inferred from it:**
- **No baseline comparison.** The report doesn't compare CrawlViz's cascade against a plain BFS or a pure-LLM-scores-everything crawl on the same seed/budget, so "narrows the space while retaining relevant material" is a claim about this one configuration's output shape, not a measured improvement over an alternative.
- **No repeated runs / variance data.** One reference run is reported; there's no indication of how much node selection, cluster structure, or the precision/recall trade-off would vary across repeated runs with the same configuration, different seeds, or different topics.
- **No precision/recall against ground truth.** "On-topic" is assessed qualitatively (does the resulting cluster structure look sensible) rather than against a labeled relevance set.
- **Single target domain.** The evaluation is one topic (Type 2 Diabetes) on one site (`wikimd.org`) — generalization to other topics, domains, or link densities is untested here.

None of this diminishes what the reference run demonstrates about the architecture working end-to-end at a meaningful scale (539 real nodes, tens of thousands of scored candidates, within a realistic politeness budget) — it's a legitimate systems demonstration. It's a smaller claim than "the scoring approach outperforms alternatives," which the report doesn't attempt and this documentation shouldn't imply on its behalf.

## Limitations acknowledged in the report itself

The report is explicit that a significant share of total wall-clock time (22.5% in the reference run) is spent on politeness-driven waiting rather than active processing — a structural cost of respecting per-site rate limits that scales with node count regardless of how fast the scoring pipeline itself is.
