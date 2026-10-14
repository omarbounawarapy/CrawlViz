# Frozen-graph benchmark

Runs traversal policies through the real pipelines (requests, extraction,
filtering, storage, scoring, priority, retry) on a graph that never changes.
Concurrency is 1 and every RNG is seeded, so a policy and seed give one visit
order. There is no network, LLM, embedding model, exporter or UI.

    .venv/bin/python -m benchmark --runs 5 --budget 100
    .venv/bin/python -m benchmark --graph my_graph.json

## What it measures
Relevant pages found among the first N fetched. Policies only rank the
frontier: each writes a score on every link, equal scores keep FIFO order
(so a constant score is BFS), and the scoring stage admits every link.

Policies: `bfs`, `random`, `anchor_lexical` (topic words in the anchor),
`oracle` (reads the label; a ceiling).

## Lockstep, and what is measured separately
The crawler picks its next page from a frontier that scoring is still filling,
so with overlapped fetching and scoring the visit order depends on how fast
scoring finishes. That would make a live LLM run and its cached replay walk
different pages. In lockstep (the default) a page is fetched only after the
previous page's scoring, priority calculation and new frontier nodes have
landed, and the scoring worker picks its next node only then too. Only state
decides when the crawler moves on, never the clock. `tests/test_benchmark.py`
checks that the visit order is identical under different and irregular
scoring latencies.

This is the behavioral benchmark: decision quality on a fixed trajectory.
Live cascade runs also print performance numbers (wall time, pages per
second, LLM latency mean, median and p95, time spent waiting on pacing and
rate limits) and input and output tokens, which the translators now pass
through and the LLM cache stores with each answer (replayed answers count at
the tokens they originally cost). A replay prints its own wall time next to the live one; the difference is the
LLM contribution on an identical page sequence. Overlapped, production-style
execution is a different experiment and is not built (`lockstep=False` runs it
but nothing reports on it).

## Cascade repeats
Each repeat has its own LLM cache scope and its own semantic-space store, so
repeats are independent live realizations and a rerun replays each one.
Semantic-space growth is committed every `--flush-every` scored nodes instead
of on a wall-clock timer. A repeat that ended early, gave up scoring a node or
swallowed a pipeline exception is reported INVALID and left out of the mean
and standard deviation; handled LLM failures and empty answers stay in and are
reported. `--replay-only` makes no LLM calls, fails on any unrecorded lookup
and checks that each repeat visits exactly the pages it visited originally.

Time spent asleep on pacing or a 429 back-off pauses the runner's idle clock
(and is reported as 429 back-off time), so a long rate-limit wait is not
mistaken for a stall. Scoring calls made after the budget is fetched are
never answered: whether the last page's call started before the stop used to
depend on timing, which made a replay ask for an answer the live run never
recorded.

## Arms and thresholds
With `--cascade`:

- `--llm-all`: every discovered link goes to the LLM, same prompt, calls of
  at most `MAX_LLM_LINKS_PER_NODE` links, no bucketing. NLP scores are still
  computed (the priority strategy blends them) but decide nothing about who
  is sent.
- `--no-llm`: embedding scores only. No scoring call and no learned
  expansions; the topic expansion is replayed from `--llm-cache` (scope
  `rep<N>`), so the topic basis is the cascade's own. An unrecorded
  expansion raises `ReplayMiss` instead of silently running with no topic.
- `--low` / `--high`: override the 0.20 / 0.75 thresholds. The cascade
  normally buckets by per-node percentiles (20th / 75th), under which the
  absolute thresholds only apply to nodes with fewer than 10 links, so giving
  either flag switches percentile bucketing off for that run.

Arms are recorded under their own policy name: `llm_all`, `no_llm`,
`cascade_low0.1_high0.5`.

## Output
Each run writes one JSON file to `--results-dir` (default
`benchmark/results/`): page sequence, label of each page, validity, LLM calls,
tokens, timings. `--save-sequences FILE` writes the visit order of every
policy and repeat. `python -m benchmark.analyze` reads the result files and
writes `benchmark/analysis/`: `curves.csv` (harvest@k to k = 100, mean and 95%
CI), `harvest_table.tex`, and `wilcoxon_table.tex` (cascade against each other
policy on harvest@30, paired on graph and repeat).

## Graph files
Page names and link targets are re-encoded on load the way the crawler
encodes URLs (`utils.html_utils.normalize_url`), so raw non-ASCII names in a
file are fetched correctly. Labels are 0/1/2 (`label`); older files with only
`relevant` read as 0/1. A warning lists pages that share a title (usually a
redirect crawled twice); `FrozenGraph.merge(keep, drop)` folds one into the other.

## Not covered yet
- The cascade itself. It needs the embedding model and an LLM (or a simulated
  annotator), and its bucketing drops low-scored links, which the baselines
  skip on purpose.
- A real graph. Only the synthetic generator exists; `FrozenGraph.load` takes
  the JSON format in `benchmark/graph.py`, but nothing records one from a
  live crawl yet. Synthetic results show the harness works, not how the
  cascade performs on the web.
- Results hold for concurrency 1 and lockstep only.

## Rubric v1 (frozen 2026-10-02) and its pilot

`rubric.md` is frozen; its SHA-256 goes into the graph file on `label_graph --merge`.
The judge is `qwen/qwen3.8-27b` (Groq retired `llama-3.3-70b-versatile`); the cascade uses
`openai/gpt-oss-120b`, a different family.

Pilot (`pilot30.tsv`, `pilot_label2.tsv`; run `python -m benchmark.pilot <tsv>`): 42 pages
labelled by hand, judge matched on 38. The four differences: Ariana, Gouvernorat de l'Ariana and Licence d'informatique (hand 1,
judge 0) and Institut supérieur de documentation de Tunis (hand 0, judge 1).
They come from the hand labeller asking "does this lead toward the ISI" where the rubric
asks "is the subject a Tunisian higher-education institution or system". Label 1 therefore
measures topical neighbourhood, not navigation value. The label-2 check found the target
and no false 2s (1 target page exists in the graph; no programme or department pages).
