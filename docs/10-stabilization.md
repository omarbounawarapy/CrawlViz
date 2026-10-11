# Stabilization Phase

This page records the stabilization phase: the work done on 2026-10-01 to fix runtime defects before any comparison of crawl policies. Each claim was checked against the code and the commit history.

For the design context, see [`09-design-decisions.md`](09-design-decisions.md). For the test commands, see [`08-developer-guide.md`](08-developer-guide.md).

## Why it happened

Before this phase the crawler could visit pages in the wrong order, stop with work still pending, count the seed page wrongly, and write run state into a shared store. Any comparison between crawl policies run on that code would measure those defects as much as the policies. The phase fixed the defects first, and added the tests that keep them fixed.

## What it changed

Work was grouped in three tiers. Each item fixed a defect or made an implicit contract explicit. None of it added a benchmark framework, a plugin system, a new event bus or a new database.

### P0: structural correctness

| Item | Change | Commit |
|---|---|---|
| P0.0 | Runtime invariant harness in `tests/test_runtime_invariants.py`, first with strict `xfail` markers | `c9c2bf0` |
| P0.1 | Higher-priority nodes are fetched and scored first | `70a674c` |
| P0.2 | One priority scale; an LLM score of 0 is a score | `1eaec10` |
| P0.3 | `node.ready` resolves on every terminal failure | `70ce943` |
| P0.4 | An empty LLM sample is not a failure; empty-result retries are capped | `71e9cb2` |
| P0.5 | Natural termination completes; the gateway closes on stop | `90e0496` |
| P0.6 | Blueprint extraction transforms are applied | `c149521` |

### P1: contract hardening

| Item | Change | Commit |
|---|---|---|
| P1.1 | The blueprint is validated at load; malformed input returns 422 | `adbd00d` |
| P1.2 | `max_nodes` counts fetched pages; `max_depth` limits admission | `435013e` |
| P1.3 | Run isolation: spaces are keyed by blueprint and model, stored as npz and json, read-only unless the blueprint opts in; `items.db` rows are keyed by `(crawl_id, id)` | `ebd35d5` |
| P1.4 | Scorer, annotator and fetcher contracts are declared and injected | `693ac6a` |
| P1.5 | Decision events carry plain values and a broker-assigned sequence number | `5ebb1bd` |
| P1.6 | Each request, processing and scoring task binds a trace id | `88321a2` |
| P1.7 | Scoring and expansion responses are typed; malformed outcomes are counted | `d0c399d` |
| P1.8 | Scoring reads page text, not raw HTML; crawl and NLP evaluation share one function | `7f6f152` |
| P1.9 | URL identity drops fragments and trailing slashes, and normalizes percent-encoding | `17682a1` |
| P1.10 | The wire protocol lists every emitted message | `ecf6f1c` |

### P2: infrastructure

| Item | Change | Commit |
|---|---|---|
| P2.1 | The UI gateway uses the current `websockets` asyncio API, with a configurable port (`Crawler(ui_port=...)`, default 8765, 0 in tests) | `bbe2119` |
| P2.2 | 429 backoff keys on the HTTP status, not on error text | `b631b17` |
| P2.3 | `robots.txt` is honoured and the User-Agent is honest | `8535526` |
| P2.4 | `Crawler` reads thresholds and batching from `RuntimeConfig`, with per-run overrides | `e1dbd75` |
| P2.5 | Bounded shutdown in `Crawler._run_until_stopped`, which cancels stragglers and re-raises task errors | `bbe2119` |

P2.5 does not use `asyncio.TaskGroup`. The bounded shutdown in `_run_until_stopped` met the goal without it.

### P3: testing and observability

| Item | Change | Commit |
|---|---|---|
| P3.1 | Every filesystem root a `Crawler` writes is injectable; construction needs no `keys.json` | `d5fc233` |
| P3.2 | Seeded RNG streams and explicit fetch and scoring concurrency | `72dc433` |
| P3.3 | The UI wire stream and a run manifest are written to `export/<crawl_id>` | `190a134` |
| P3.4 | The narrative crawl log is JSON lines, written by a single worker | `757e6a2` |
| P3.5 | A hashing embedding engine lets NLP scoring be tested without MiniLM | `8d76a01` |
| P3.6 | Documentation claims the code does not back were removed, including references to the missing `V2_ARCHITECTURE.md` | `e3b1fc5` |

Fixed after the phase: `ExportingPipeline` flushes its buffer when cancelled, so `POST /stop` keeps the rows already collected (`test_cancelled_exporter_flushes_its_buffer`). The CORS origin regex is now `CRAWLVIZ_CORS_ORIGIN_REGEX`, so a deployment can turn off the localhost-only default.

Two fixes landed alongside the tiers: a `ScoringPipeline` worker stops waiting on `node.ready` once the crawl stops (`3a313c0`), and the UI no longer reconnects a stale WebSocket, so events are not delivered twice (`8c2d4f9`, after the phase).

## Exit criteria

Four checks decided that the runtime was stable enough for experiments. Each one was checked against the repository.

1. **All four P0.0 harness assertions pass without `xfail`.** Confirmed. `tests/test_runtime_invariants.py` has no remaining xfail markers, and the full backend run reports no xfailed tests.
2. **P1.2 (budget), P1.3 (isolation), P1.5 (value records) and P3.2 (determinism) are in.** Confirmed by commits `435013e`, `ebd35d5`, `5ebb1bd` and `72dc433`.
3. **A `wikiMD` run reaches its stop condition, `Crawler.start()` returns, and `/status` reports not running, with no manual `/stop`.** Confirmed by live runs on 2026-10-01 with capped page counts. `wikiMD` stopped on `MAX_NODES_REACHED`, and `isi` stopped by itself. Both returned from `start()`. The `/status` response was not called through the API during those runs, so this criterion is checked by reading the code (`/status` returns `running = not task.done()`), not by a live call.
4. **Two seeded harness runs produce byte-identical decision records.** Confirmed by the test added in `6e360a6`.

## Test status

The backend suite has 248 tests in 26 files, all passing, with no xfail markers. A full run takes about 70 seconds. The frontend suite (Vitest) covers the reducer, the replay scrubber, the layout and the top-level app.

## Known limitations

These describe the code as it is today:

- LLM token usage is always `None`. The translators discard the `usage` field from provider responses, so `TracedLlmHandler` has nothing to record. `benchmark/__main__.py` prints the same caveat.
- `Crawler.start()` builds every service, including the NLP service and the LLM handler, whether or not a run uses them.
- The frozen-graph benchmark in `benchmark/` compares crawl policies on recorded pages. See `benchmark/README.md`.
