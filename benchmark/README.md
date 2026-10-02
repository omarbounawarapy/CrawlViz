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
rate limits). Token usage is not available because the translators drop it.
A replay prints its own wall time next to the live one; the difference is the
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
