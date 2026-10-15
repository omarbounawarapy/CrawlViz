# Evaluation protocol (DRAFT for review, not committed)

Everything marked **TODO** is a choice only you can make. Nothing here has been
run.

## 1. Question and hypotheses

Does the LLM-scored cascade find more relevant pages than cheaper strategies
under the same fetch budget, and how close does it get to scoring every link
with the LLM at a fraction of the calls?

| | Hypothesis | Comparison |
|---|---|---|
| H1 | The cascade has higher harvest@30 than BFS and anchor-lexical. | `cascade` vs `bfs`, `anchor_lexical` |
| H2 | The cascade has higher harvest@30 than embedding-only. | `cascade` vs `no_llm` |
| H3 | The cascade is close to `llm_all` on harvest@30 and uses fewer LLM tokens (calls reported, not compared). | `cascade` vs `llm_all`, plus tokens |

**TODO** define "close" for H3 before running: e.g. the lower 95% CI bound of
cascade harvest@30 is within X percentage points of `llm_all`, or a
non-inferiority margin of X. State X here: ____

## 2. Primary metric

harvest@30 at label >= 1: the share of the first 30 fetched pages (the seed
counts) graded 1 or 2 by the judge. Computed per run, averaged over repeats
per arm, 95% Student-t CI. Each title counts once (redirect duplicates removed
at first visit, `--graphs-dir`).

Tests: paired Wilcoxon signed-rank, cascade against each arm, paired on
(graph, repeat). `benchmark.analyze` writes `wilcoxon_table.tex`.

**TODO** multiple-comparison correction across the H1-H3 comparisons: Holm /
Bonferroni / none (and say so): ____
**TODO** pairing: baselines have 10 seeds, `llm_all` 3-5 repeats; the pairs
are the shared (graph, repeat) indices only. Confirm that is acceptable.

## 3. Secondary metrics

- harvest@k for k in 10, 30, 50, 100 (label >= 1), and for direct targets only
  (label == 2).
- recall@k: relevant fetched over all relevant pages in the graph.
- nDCG@k over the fetch order with grades 0/1/2 as gains.
- **Cost is measured in tokens** (input + output per run, and relevant pages
  per 1k tokens, `efficiency_table.tex`). Call counts are listed but are not
  comparable between arms: `llm_all` sends up to 60 links per call while the
  cascade sends one batch per page. H3's "fewer LLM calls" is therefore
  tested on tokens. Replayed answers count at the tokens they originally
  cost. A run whose provider reported no usage prints a warning and is not
  used for cost.
- Wall time and rate-limit waiting (live runs only; reported, not tested).
- Validity: valid / invalid / early-stopped runs per arm.

## 4. Data

- Graph: **TODO** which frozen graphs. Status as of this draft:
  - `ball.json` (5,865 pages): **not yet usable.** The graph file has no
    labels; `ball_labels.jsonl` holds 516 judge labels so far (482 / 27 / 7 for
    0 / 1 / 2), so about 5,350 pages still need the judge (live Groq calls,
    quota-limited) before `label_graph --merge` will write them. Only after
    that can the cascade, harvest or the audit run.
  - `isi.json` (1,462 pages): **not usable for harvest.** Ungraded, with one
    relevant page.
  - `python -m benchmark` refuses a `--graph` that is not fully graded or has
    fewer than 30 relevant pages (`--allow-ungraded` overrides);
    `benchmark.audit sample` refuses an unlabelled graph.
  Seed page: ____
- Labelling settings: the judge run uses `BATCH` and `TOKENS_PER_MINUTE` from
  `benchmark/label.py`; **TODO** commit the values you want (currently 20 /
  7000 in the working tree, 8 / 5500 committed) before labelling.
- Labels: judge model `qwen/qwen3.8-27b` on Groq, rubric `benchmark/rubric.md`
  (hash recorded in the graph). **TODO** confirm the judge differs in family
  from every crawler model.
- `python -m benchmark.graph_stats` output goes in the dataset table.
- Links to pages outside the graph (the rule the paper must state): recorded
  graphs are closed, so none exist. If one is requested anyway, under the
  default `ABSENT_PAGE_HITS = "fail"` it **does not use budget** (only pages
  in the graph count as fetched) but the failed requests make the run
  **invalid**. `absent_page_hits` is in every result and must be 0.

## 5. Arms, budgets, repeats

Budgets (fetched pages, seed included): 50, 100, 200.

| Arm | Repeats | Seeds / scopes | LLM |
|---|---|---|---|
| `cascade` | 10 | `rep0..rep9`, independent live realizations | yes |
| `no_llm` (embedding-only) | 10 | replays the cascade's expansion per scope | expansion only |
| `llm_all` | **TODO** 3, 4 or 5 (cost: every link is scored) | `rep0..` | yes |
| `bfs`, `anchor_lexical`, `random`, `oracle` | 10 seeds each | seed = repeat | no |

`oracle` is an upper bound, reported but not part of H1-H3. **TODO** keep or
drop `random` in the main table.

Cascade settings: production defaults, percentile bucketing 20 / 75, scoring
strategy from `templates/isi.json`, `--flush-every 8`. **TODO** sensitivity
runs (`--low-pct` / `--high-pct`, absolute `--low` / `--high`) and which
values: ____

## 6. Models and providers

| Role | Provider | Model |
|---|---|---|
| Cascade scoring and expansion | groq | `openai/gpt-oss-120b` (CLI default) |
| `llm_all` scoring | same as cascade | same as cascade |
| Judge | groq | `qwen/qwen3.8-27b` |
| Embeddings | local | per `config.runtime_config` embeddings model |

**TODO** confirm model ids and whether a second provider/model is run as a
robustness check: ____. Model and provider are in every result's manifest and
in the LLM cache key.

## 7. Validity and replay rules

- A run is **invalid** if it stalls with work pending, a node exhausts its
  scoring retries, a request/priority/storage failure event fires, or a
  pipeline swallows an exception. Invalid runs are excluded from every metric
  and listed in the validity table; they are not silently rerun.
  **TODO** whether an invalid repeat is re-run with a new scope or the count
  simply drops: ____
- A run that ends because the frontier is empty is **early-stopped**: valid,
  kept, and reported.
- Handled LLM failures and empty answers (rescheduled and scored later) are
  part of the measurement and are reported.
- Rate limiting is infrastructure: `PacedLlm` waits and the idle clock pauses;
  it changes wall time only.
- **Replay**: `--replay-only` makes no LLM calls and must reproduce each
  repeat's page sequence exactly. Any cache miss aborts and is written as
  `__replay-miss.json`. The cache key includes scope, provider, model, prompt
  version and graph SHA-256, so any change to those requires re-recording.
- Every result JSON has a manifest (commit, graph and rubric hashes, model,
  provider, prompt version, budget, thresholds, seed, repeat). Results from a
  `+dirty` commit are not used. **TODO** freeze the commit hash for the final
  runs: ____

## 7a. What differs from production

The benchmark runs the real pipelines at concurrency 1 in lockstep. The only
behaviour that exists solely for this is benchmark-side: the quiet frontier
pop (`_QuietQueue`), the lockstep fetch gate, count-based semantic-space
flushes and the budget gate. They live in `benchmark/runner.py`; production
`FrontierQueue` and `RequestsPipeline` are unchanged. Two production-code
changes exist and neither alters default crawling: token usage is read from
provider responses (additive), and `ScoringPipeline.llm_batch_size` defaults
to `None` (one call per node, as before). `llm_all` is the only user of it.
State this in the paper's threats-to-validity.

## 7b. Smoke test (mandatory before labelling or any experiment)

Nothing has touched a real model since the frontier change and the new cache
keys, and old caches are unusable. Run once, on `isi.json` (labels are not
needed to test determinism or token counting):

```
.venv/bin/python -m benchmark --graph benchmark/data/isi.json --allow-ungraded --cascade \
  --budget 10 --reps 2 --llm-cache benchmark/data/smoke_cache.jsonl \
  --runs-file benchmark/data/smoke_runs.json --results-dir benchmark/smoke
.venv/bin/python -m benchmark --graph benchmark/data/isi.json --allow-ungraded --cascade \
  --budget 10 --reps 2 --llm-cache benchmark/data/smoke_cache.jsonl \
  --runs-file benchmark/data/smoke_runs.json --results-dir benchmark/smoke --replay-only
```

Pass criteria: the replay finishes with "replay matches the original" for
every repeat and no `ReplayMiss` (0 misses, no `__replay-miss.json`);
`input_tokens` and `output_tokens` are non-zero in the live results and no
token WARNING is printed; both repeats are valid. **TODO** record the date,
commit and outcome here: ____

## 8. Blind audit of the judge

Purpose: show the judge's labels agree with a human enough to be the ground
truth.

1. `python -m benchmark.audit sample --graph <graph> --seed <n>`: all
   label-2 pages, about 60 label-1, about 60 label-0 (weighted toward pages
   mentioning Tunisia), about 30 uniform; the pilot pages are excluded. Output:
   a shuffled TSV (id, title, 450-char excerpt, empty `human_label`) and a key
   file with the stratum and the judge label.
2. The annotator fills `human_label` (0, 1, 2) from the rubric, **without
   opening the key file** and without seeing the judge's output.
3. `python -m benchmark.audit score --tsv ... --key ...` reports confusion
   matrices (3-class and binary), per-class precision/recall, raw agreement,
   Cohen's kappa with 1,000-sample bootstrap CIs, and agreement reweighted to
   the graph's label distribution.
4. **TODO** second annotator: who, and whether they label the same sample
   (`--tsv2` reports human-human kappa): ____
5. **TODO** acceptance threshold set before looking: e.g. binary kappa >= 0.__
   and reweighted agreement >= 0.__. If not met: ____
6. **TODO** the sample size (`--total`) and the seed, fixed before sampling.

The key file stays out of the annotator's reach until scoring. The sample
excludes the pilot pages, which were used to tune the rubric.

## 9. Reporting

Dataset table (`graph_stats`), harvest tables at the primary and secondary
metrics, curves, Wilcoxon table, efficiency, validity and replay tables, the
audit report, and the manifest hashes in an appendix. **TODO** venue and
page limit, which decides which tables go to the appendix.

## 10. Known limits to state

- Single graph (or **TODO** how many) and one seed page; results do not
  generalize beyond it without more graphs.
- Concurrency 1 and lockstep only.
- The judge is an LLM; audit agreement bounds how far its labels can be
  trusted.
- Wall-clock numbers depend on the provider's rate limits that day.
