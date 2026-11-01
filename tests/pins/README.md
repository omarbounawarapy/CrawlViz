# Behaviour pins

Pins record what a crawl does today so a later refactor can prove it changed
nothing it did not mean to. Each pin runs a full cascade crawl offline and
compares four things with golden files (the `crawler` pin compares less, see below).

| Pin | Graph | Pages | Golden files |
|---|---|---|---|
| `isi` | `benchmark/data/isi.json` (frozen) | 50 | `golden/isi/` |
| `synthetic` | 200 pages generated in `synthetic_site.py` from a fixed seed | 60 | `golden/synthetic/` |
| `crawler` | `benchmark/data/isi.json` through the real `Crawler` (see below) | 5 | `golden/crawler/` |

Per pin, one JSON-lines file each:

- `fetch_order.jsonl`: the pages in the order they were fetched.
- `link_scores.jsonl`: every link's NLP score, LLM score and priority as decided, and the links the cascade dropped or trusted without the LLM.
- `llm_requests.jsonl`: the prompt of every LLM call, in order.
- `wire_messages.jsonl`: every message the UI bridge broadcast (types in `docs/crawl_messages.ts`).

No network, keys or embedding model are used: `FrozenGraph` serves the pages,
`HashingEmbeddingEngine` embeds, and a scripted LLM answers behind `CachedLlm`.
Timestamps, durations and worker ids are replaced by `<volatile>`, floats are
rounded to 6 places, and recording stops when the last page of the budget is
requested (what follows races with the stop). See `golden_files.py` and
`pin_observer.py`.

### The `crawler` pin

`isi` and `synthetic` run `benchmark.runner`, which builds its own stages. The `crawler`
pin runs `Crawler.start()` itself, so `core/crawler.py` and `core/stages.py` are covered.
It crawls the `offline_demo.json` blueprint with a budget of 5 pages, one fetch worker
and one scoring worker, on the doubles of `CRAWLVIZ_OFFLINE=1` (`build_offline_session`).
`Crawler` has no lockstep, so the stop event races the next fetch and a run may fetch one
page more than the budget. The pin records only what that race cannot change
(`pin_crawler.py`):

- `composition.jsonl`: the stages in start order, then each event type with its consumers in
  dispatch order.
- `fetch_order.jsonl`: the first 5 pages fetched.
- `llm_requests.jsonl`: the first 2 prompts (the expansion and the first scoring call).

It takes about 7 seconds. It has no `link_scores` or `wire_messages` golden: their length
depends on the race.

## How a run is compared

The golden file and the run are read back as JSON and compared value by value.
Everything must be equal, including types (`36` is not `36.0`), key sets, list
lengths and the order of the lines. The one exception is the computed scores:
the floats under `priority`, `nlp_score` and `nlp_breakdown` match when they
differ by at most 1.5e-6, one rounding step plus half a step (`FLOAT_TOLERANCE`).
The tolerance is absolute and meant for values in [0, 1]. Any other float, such
as a temperature, must be equal.

Why: the hashing embeddings are float32 (`nlp/embedding_engine.py`), and another
numpy or BLAS build can move a score by one float32 ulp, about 6e-8. A value next
to a rounding boundary then rounds to the neighbouring digit. For example
`boilerplate_score` = sqrt(2/7) is 0.53452247 in float32, which rounds to
`0.534522`; the next float32 up, 0.53452253, rounds to `0.534523`. CI run
39410825053 (Python 3.12) failed on seven such values in `nlp_breakdown`, with
the same pages, order, priorities and LLM requests. The goldens stay as they
are; `fixtures/ci_run_39410825053_wire_messages.json` holds those seven lines and
`test_golden_comparison.py` checks they pass.

The tolerance cannot hide a change of fetch order:

- Fetch order, node ids, page URLs, LLM prompts and the sequence of wire messages
  hold no floats or are strings, so they are compared exactly.
- The floats that decide the order may drift within the tolerance, but only
  without a strict inversion: if the golden has `a < b` and the run has `a > b`,
  the pin fails. Rounding is monotone, so a drift that keeps the true order can
  make two values equal (a merge) or split two equal ones, but never invert them.
  Priorities are compared across the whole file, because the queue compares any
  two. `nlp_score` is compared only among the links of one parent page, which is
  how the cascade uses it; the parent is `parent_id` in a wire message and
  `node_id` in `link_scores.jsonl`, and a score that names no parent is not
  compared.
  A failure reads `order changed, priority: ...`.
- A merge or a split can still reorder the queue. The strategy rounds a priority
  to 6 places (`priority/strategy.py`, `_score`), and pages with equal priorities
  leave the queue in the order they went in (`pipelines/frontier_queue.py`). The
  inversion guard does not look at this. `fetch_order.jsonl` does: it is compared
  exactly, so it fails whenever a merge or split changes which page is fetched
  next.

If `order changed` fires while `fetch_order.jsonl`, `llm_requests.jsonl` and all
the link decisions match, two near-equal values flipped between machines. Do not
widen the tolerance and do not re-record the goldens on one machine; bring it to
the research-scientist.

A failure lists the changed values by line and path, for example
`line 69: record.nlp_breakdown.boilerplate_score: 0.534522 became 0.5346`,
followed by the unified diff. Lines that differ only within the tolerance are
left out of the diff. `--update-pins` still writes the run's rounded values.

## Run

From the repository root:

```
uv run pytest -q tests/pins
uv run pytest -q -m pins
```

`pytest.ini` puts the repository root on the import path (`pythonpath = .`), so the
same commands work in the main checkout and in a git worktree. A pin takes a few seconds. A mismatch
fails with a unified diff of the changed golden lines, for example
`fetch_order.jsonl changed (50 golden lines, 50 now)` followed by the changed values and the `-` and `+` lines.

## Update

Goldens are rewritten only with `--update-pins`; without it nothing is written
and a missing file fails.

```
uv run pytest -q tests/pins --update-pins
```

The run ends with a list of the golden files it rewrote, for example
`isi/wire_messages.jsonl`; review each with `git diff`.

An update needs, in this order:

1. the cause found: which commit changed the behaviour, and is that intended;
2. a CHANGE-REQUEST to test-engineer naming that commit and the reason;
3. research-scientist sign-off when scores, ordering or prompts changed;
4. the golden changes in their own commit, never mixed with the behaviour change.

Never update a golden to make a failure go away.

## Determinism

The same commit must give byte-identical goldens. Checked by running the pins
repeatedly, under `PYTHONHASHSEED` 1 to 4, and four at a time in parallel: all
green. After an update, run `uv run pytest -q tests/pins` once more without the flag.

## Module names

`tests/pins` has no `__init__.py`, so pytest puts the folder on `sys.path` and its
modules import each other by bare name; mypy does the same through `mypy_path` in
`pyproject.toml`. A module here must therefore never share a name with a top-level
package or module of the repository (`config`, `models`, `core`, ...) or with the
standard library, or it would shadow the real one. `test_module_names.py` fails when
one does.
