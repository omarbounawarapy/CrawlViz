# Evaluation protocol

Pre-registered before any crawl result exists: this file is committed and
pushed first, then the graph is labelled and audited, then the arms run.
Changes after that point are listed in the amendments section at the end,
with the date and the reason, and never edit the text above them.

## 1. Question and hypotheses

Does the LLM-scored cascade find more relevant pages than cheaper strategies
under the same fetch budget, and how close does it get to scoring every link
with the LLM at a fraction of the calls?

| | Hypothesis | Comparison |
|---|---|---|
| H1 | The cascade has higher harvest@30 than BFS and anchor-lexical. | `cascade` vs `bfs`, `anchor_lexical` |
| H2 | The cascade has higher harvest@30 than embedding-only. | `cascade` vs `no_llm` |
| H3 | The cascade is close to `llm_all` on harvest@30 and uses fewer LLM tokens (calls reported, not compared). | `cascade` vs `llm_all`, plus tokens |

"Close" for H3 is a non-inferiority margin of 0.05 on harvest@30: the lower
bound of the 95% CI of the paired mean difference (cascade minus `llm_all`)
is above -0.05. "Fewer tokens" means the cascade's mean tokens per run are
below `llm_all`'s, reported with the ratio.

## 2. Primary metric

harvest@30 at label >= 1: the share of the first 30 fetched pages (the seed
counts) graded 1 or 2 by the judge. Computed per run, averaged over repeats
per arm, 95% Student-t CI. Each title counts once (redirect duplicates removed
at first visit, `--graphs-dir`).

Tests: paired Wilcoxon signed-rank, cascade against each arm, paired on
(graph, repeat). `benchmark.analyze` writes `wilcoxon_table.tex`.

Multiple comparisons: Holm correction over the four confirmatory tests
(cascade vs `bfs`, `anchor_lexical`, `no_llm`, `llm_all` on harvest@30); both
raw and Holm-adjusted p are reported. Everything else is descriptive.
Pairing: only the (graph, repeat) indices both arms have are paired, so
`llm_all` is compared on its 3 repeats and the others on 10.

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

- Graph: `benchmark/data/isi.json`, 1,462 pages, a radius-2 ball around the
  seed `Universit%C3%A9_de_Tunis_El_Manar` (Wikipedia fr), topic "institut
  superieur informatique ISI (tunisia / ariana)", target of the rubric: the
  ISI itself. Its judge labels were cleared; it is labelled in full before
  anything else runs. One graph, one seed page. `ball.json` (5,865 pages,
  unlabelled) is **not** part of this protocol; using it later is an
  amendment.
- `python -m benchmark` refuses a `--graph` that is not fully graded or has
  fewer than 30 relevant pages (`--allow-ungraded` overrides, used only for
  the smoke test); `benchmark.audit sample` refuses an unlabelled graph.
  If `isi.json` ends with fewer than 30 relevant pages the experiment stops
  and that is reported, not worked around.
- Labelling settings: the judge run uses `BATCH = 8` and
  `TOKENS_PER_MINUTE = 5500` from `benchmark/label.py` (the committed values),
  450-character excerpts.
- Labels: judge model `qwen/qwen3.8-27b` on Groq, rubric `benchmark/rubric.md`
  (hash recorded in the graph). The judge (Qwen) is a different model family
  from the only crawler model (gpt-oss).
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
| `llm_all` | 3 (every link is scored; more only as an amendment) | `rep0..rep2` | yes |
| `bfs`, `anchor_lexical`, `random`, `oracle` | 10 seeds each | seed = repeat | no |

`oracle` is an upper bound, reported but not part of H1-H3. `random` stays in
the main table.

Cascade settings: production defaults, percentile bucketing 20 / 75, scoring
strategy from `templates/isi.json`, `--flush-every 8`. No sensitivity runs
(`--low-pct` / `--high-pct`, `--low` / `--high`) are pre-registered; any that
are run are labelled exploratory.

## 6. Models and providers

| Role | Provider | Model |
|---|---|---|
| Cascade scoring and expansion | groq | `openai/gpt-oss-120b` (CLI default) |
| `llm_all` scoring | same as cascade | same as cascade |
| Judge | groq | `qwen/qwen3.8-27b` |
| Embeddings | local | per `config.runtime_config` embeddings model |

One provider and one crawler model; no second back-end. Model and provider
are in every result's manifest and in the LLM cache key.

## 7. Validity and replay rules

- A run is **invalid** if it stalls with work pending, a node exhausts its
  scoring retries, a request/priority/storage failure event fires, or a
  pipeline swallows an exception. Invalid runs are excluded from every metric
  and listed in the validity table; they are not silently rerun.
  An invalid repeat is not re-run: the count drops and is reported. Only if
  an arm is left with fewer than 5 valid repeats are more run, with new
  scopes `rep10, rep11, ...` for every arm that has fewer, and that is
  stated.
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
  `+dirty` commit are not used. The code under test is the commit that
  pushes this file; the experiment runs on that commit or one that changes
  nothing under `benchmark/`, `pipelines/`, `services/`, `nlp/`,
  `priority/` or `models/`, and every manifest records the hash.

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
token WARNING is printed; both repeats are valid.

Outcome: run 2026-10-15 on commit `aaff7ae` plus a result-file naming fix
(`removesuffix`, no effect on behaviour), `isi.json`, budget 10, 2 repeats, groq `openai/gpt-oss-120b`. Live: rep 0
4 calls, 3,121 in / 4,090 out tokens; rep 1 5 calls, 3,442 in / 4,179 out;
both valid. Replay in separate processes with `PYTHONHASHSEED` 1 and 777:
"replay matches the original" for both repeats each time, 0 live calls, 0
cache misses, identical token totals. Passed.

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
4. Second annotator: if one is found, they label the first 50 ids of the same
   TSV, blind in the same way (`--tsv2` reports human-human kappa on those).
   If none is found, that is stated and only judge-vs-human is reported.
5. Acceptance, fixed before looking: binary (label >= 1) kappa >= 0.60 and
   reweighted binary agreement >= 0.85. If not met, the results are still
   reported, with the audit numbers beside them as a stated bound on label
   noise; the rubric and the labels are not changed after crawl results
   exist.
6. Sample: `--total 180` (all label-2 pages included, the rest split 40 / 40
   / 20) and `--seed 0`. The audit is completed before any crawl result is
   read.

The key file stays out of the annotator's reach until scoring. The sample
excludes the pilot pages, which were used to tune the rubric.

## 9. Reporting

Dataset table (`graph_stats`), harvest tables at the primary and secondary
metrics, curves, Wilcoxon table, efficiency, validity and replay tables, the
audit report, and the manifest hashes in an appendix. Venue and page limit are not decided and do not affect the experiments.

## 10. Known limits to state

- A single graph and one seed page; results do not
  generalize beyond it without more graphs.
- Concurrency 1 and lockstep only.
- The judge is an LLM; audit agreement bounds how far its labels can be
  trusted.
- Wall-clock numbers depend on the provider's rate limits that day.

## Amendments

(none)
