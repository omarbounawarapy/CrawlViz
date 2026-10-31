# ADR 12: API v2 is a thin HTTP layer over domain services, with one error envelope and only the resources the user requirements need

Status: proposed, 2026-10-30

## Context

- The crawl lifecycle lives in the router: module globals `_current_task` and
  `_current_crawler` (`routes/run.py:29-30`), offline session building (`:42-52`) and the
  status shape (`:105-121`). A command-line tool could not reuse any of it.
- None of the 44 routes declares `response_model`, so no client types can be generated from
  the OpenAPI document. Errors are raw text: `detail=str(exc)` (`routes/run.py:83`, `:88`),
  which gives the user no next step and can leak internal details to the caller.
- Every crawl writes `events.jsonl` and `manifest.json` to `<export_dir>/<crawl_id>/`
  (`ui_bridge/event_recorder.py:1-10`, `core/crawler.py:331`), but no route lists or serves
  them. `/benchmark/runs` covers benchmark runs only, so a page of past crawls has nothing to
  read.
- Datasets are reachable only as samples (`/validation/tables`, `/validation/{table}/crawls`,
  `/validation/{table}/sample`). There is no export.
- No route explains a score or a skipped link. The wire's
  `CANDIDATE_EVALUATED.decision` has two values, `dropped` and `trusted_no_llm`
  (`docs/crawl_messages.ts:70`).
- Scores reach the UI on different scales: NLP and priority 0 to 1, LLM 0 to 100.
- The user requirements come in priority order. These nine come first:
  1. **Why this score**: for a page, what decided its score, the real prompt and reply, and
     the cascade bucket.
  2. **Health strip**: one state per subsystem, with a next step when one needs action.
  3. **True state**: status, counts and stage states match the backend.
  4. **Runs page**: list past runs and open one into the graph and the timeline scrubber.
  5. **Export**: a dataset or a run as CSV or JSONL, from the UI.
  6. **Live cost**: LLM calls, tokens and budget left, during a crawl.
  7. **Skip reasons**: every link that was not followed says why.
  8. **One scale**: one score scale across the app.
  9. **Run mode**: whether a crawl runs offline, cached or live, and with which provider.

  The later ones are in the reserved-paths table below. Candidates that no user task needs
  are dropped, and nothing is built for them.

## Decision

1. **The service layer is each domain's public API**, not a separate package:
   `crawl.CrawlController` (start, stop, state, outcome, the one current crawl),
   `runs.RunStore` (list, load with migration, delete to trash, restore),
   `storage.Datasets` (list, count, rows) and `runs.write_export` (CSV or JSONL rows, shared
   by dataset and run export). They take and return pydantic models and never import FastAPI.
   Routers in `crawlviz.api` parse, call one service and map the result. The planned
   command-line tool calls the same services in-process.
2. **`/api/v2` prefix.** New and changed resources are mounted under `/api/v2`. Today's routes
   stay where they are until the UI no longer calls them (ADR 10), then they are deleted. API v2
   is frozen once the backend resources below are built, before the UI features move onto it.
   After that, a breaking change needs an ADR (ADR 5).
3. **Every route** declares `response_model` and an `operation_id` equal to its client function
   name, so the generated client and the UI use the same verb-first names (`fetchX`,
   `createX`, `deleteX`, `startX`, `stopX`). Each router takes the token dependency, and the
   app adds Host and Origin checks and a JSON content-type check, so that a web page on another
   site cannot reach the API through DNS rebinding or a cross-site form.
4. **One error envelope**: `{"error": {"code", "message", "params", "field"}}`. `code` is a
   snake_case value from a generated enum, and the UI turns it into words (ADR 11). `message`
   is plain English for the command line and the logs. `field` is the settings path for a
   validation error. Domains raise subclasses of `CrawlvizError` that carry a code and an HTTP
   status, and one handler maps them. An unexpected exception is never swallowed: it is logged
   as structured JSON with `crawl_id` and `trace_id`, and returns `internal_error` with no
   exception text.
5. **One score display scale.** `crawlviz.scoring.display_scale` defines, once, the
   factor that takes each score kind (`nlp`, `llm`, `priority`) to 0 to 100. APIs and the wire
   keep raw values under names that say what they are. `/ui-config` serves the table
   (ADR 9). The UI applies it in `formatScore` (ADR 11). Exports apply it in Python. The raw
   cosine value stays available, as secondary text, where it matters.
6. **Resources for the first nine requirements:**

| Route | Returns | Serves |
|---|---|---|
| `GET /api/v2/ui-config` | ADR 9 | run mode, one scale |
| `GET /api/v2/status` | crawl state, crawl id, mode, status board (ADR 8), pages fetched and found, LLM calls used of budget, tokens in and out, cache hits, cost estimate or null, outcome | health strip, true state, live cost, run mode |
| `POST /api/v2/crawls` | 202 with `crawl_id`; `crawl_already_running`, blueprint and settings codes | true state |
| `POST /api/v2/crawls/{crawl_id}/stop` | 202; the outcome becomes `stopped` | true state |
| `GET /api/v2/runs` | run summaries: blueprint name, topic, start time, mode, pages fetched, relevant pages, LLM calls, tokens, end reason, whether it opens and why not; paged with `limit` and `offset` | runs page, live cost, run mode |
| `GET /api/v2/runs/{run_id}` | manifest view: blueprint, settings, mode, versions, outcome | runs page |
| `GET /api/v2/runs/{run_id}/events` | NDJSON wire messages at the current protocol, migrated on read (ADR 5) | runs page |
| `DELETE /api/v2/runs/{run_id}` | moves the run to a trash folder; returns when it will be purged | runs page (undo) |
| `POST /api/v2/runs/{run_id}/restore` | brings the run back from the trash | runs page (undo) |
| `GET /api/v2/runs/{run_id}/nodes/{node_id}/explanation` | what decided the score, the cascade bucket and the crawl's thresholds, NLP signals by glossary name, and the LLM call: provider, model, prompt id and hash, rendered prompt, raw reply, tokens, latency, cache hit, outcome | why this score |
| `GET /api/v2/runs/{run_id}/nodes/{node_id}/skipped-links` | each skipped link with its reason, deciding score and threshold | skip reasons |
| `GET /api/v2/datasets` | each dataset: blueprint name, site, table, record count, runs | export |
| `GET /api/v2/datasets/{dataset_id}/records` | `total` and one page of records | export |
| `GET /api/v2/datasets/{dataset_id}/export` | a CSV or JSONL file (`format`, optional `run_id`), streamed | export |
| `GET /api/v2/benchmark/arms` | each arm: id, whether it calls the network, estimated tokens, available or why not | run mode |
| `POST /config/effective` (existing) | gains the resolved mode for the blueprint and its overrides (ADR 9) | run mode |

   - The run routes work for the running crawl too, because the recorder writes as it goes.
     That is how a score explanation works the same live and replayed.
   - Explaining a score needs a per-call record with the rendered prompt and the raw reply.
     The LLM layer writes it to `llm_calls.jsonl` in the run folder, the same record that
     holds each call's tokens, cost, latency, attempts, cache hit and outcome, in a versioned
     format under ADR 5. Keys never enter it. Page text in it is data, and the UI renders it
     as text, never as HTML.
   - Skip reasons are one closed list: `below_cutoff`, `not_sampled`, `depth_limit`,
     `duplicate`, `robots_disallowed`, `budget_exhausted`, `unfetched_at_stop`,
     `retries_exhausted`. The wire's `CANDIDATE_EVALUATED` carries the same `skip_reason`
     (ADR 5).
   - Exports stream from SQLite in a worker thread, so they never block the event loop. The
     columns (extracted fields, `url`, `run_id`, `score` on the display scale, `saved_at`)
     are documented in `docs/`.
7. **Paths for the later requirements are reserved.** Each request and response is designed
   and reviewed when its requirement is taken up. They are built after the resources above.

| Requirement | Route |
|---|---|
| Change a setting on the running crawl, for this run or for later runs | `PATCH /api/v2/crawls/{crawl_id}/settings` with `persist` |
| Warn before a start that is larger or costlier than the safe defaults | `POST /api/v2/crawls/preflight` |
| Compare two runs | `GET /api/v2/runs/{a}/compare/{b}` |
| Rerun a past run from its manifest | `POST /api/v2/runs/{run_id}/rerun`; "Edit and run" reuses `GET /api/v2/runs/{run_id}` |
| Replay a recorded run's LLM answers from the cache | `POST /api/v2/runs/{run_id}/replay` with the cache-miss choice |
| Show where each setting's value comes from | `POST /config/effective` gains the source of each field |
| Merge a preset into the settings after a diff, with undo | `POST /api/v2/config/presets/{name}/preview` returns the diff |
| Score with a local model, with a connection test | `POST /api/v2/llm/providers/{provider}/test` |
| Compare benchmark arms in plain words, with cost and uncertainty | designed once the new benchmark results exist |
| End-of-run summary (built last) | no route: the run summary gains the top pages |
| Command line (built last) | no route: console commands over the same services |

   No route serves a dropped candidate: semantic search, coverage gaps, space management,
   weight fitting, a prompt playground beyond today's preview, per-domain rules, an MCP
   server, LLM score explanations, config suggestions, LLM crawl summaries.

## Alternatives considered

- **A separate `services/` layer between routers and domains.** It would mostly forward
  calls. Domain public APIs are already the seam ADR 1 asks for, so the extra layer adds code
  and no capability.
- **Change today's paths in place.** The UI and the API would have to switch in one commit,
  and nothing could be moved one feature at a time.
- **GraphQL.** One client, a fixed set of screens and generated REST types; GraphQL adds a
  schema layer and a library without a requirement for it.
- **Explanations computed in the UI from the stream.** The stream does not carry the rendered
  prompt or the raw reply, and replayed runs would need the same logic twice.
- **Undo by keeping the run and hiding it.** It leaves deleted data in place, and a delete
  that is never purged is a privacy problem: deleting a run has to remove its data.

## Consequences

- `routes/` shrinks to adapters, and its module state moves to `CrawlController`.
- The wire changes (`skip_reason`, mode, board) and the new stored files (`llm_calls.jsonl`,
  manifest mode) are versioned under ADR 5. Where the wire golden moves, the pin update goes
  in its own reviewed commit.
- Recording rendered prompts and raw replies grows the run folder. The size is reported in
  `/api/v2/runs`, and the trash purge frees it.
- The trash keeps a deleted run for `RUN_TRASH_TTL_S` (a named constant, about the toast
  lifetime plus a margin) and is purged at start-up and on each list.
- The new routes need a security review, above all the run and dataset ids used as paths:
  each id is checked so that it cannot point outside its folder.

## Standards affected

- REST endpoints declare their response model; client types are generated, and CI fails on
  drift.
- Every route requires the session token, with Host, Origin and JSON content type checked.
- Untrusted input is bounded: ids used as paths are sanitised.
- Secrets never reach logs, run records or the UI.
- Every error says what happened and what to do next; no raw errors.
- Destructive actions can be undone.
- REST client functions start with a verb that says what they do; `CrawlController` follows
  the pipeline naming of ADR 6.
- The simplest design that meets the need, and only what a requirement asks for.
- No swallowed errors.
- No blocking work on the event loop.
- Structured JSON logs carry `crawl_id` and `trace_id`.
- Every LLM call records tokens, cost, latency, attempts, cache hit and outcome.
- User-facing words come from the UI catalogs, not from the backend.
- Services own data and side effects, routers stay thin, and dependencies point one way.

## Migration and commit plan

Each route comes with its test.

1. `API`: error envelope, `CrawlvizError` and its handler, applied to `/api/v2` routers.
2. `Crawl`: `CrawlController` holds the current crawl; the v1 run routes call it.
3. `API`: `/api/v2/status`, start and stop.
4. `Runs`: `RunStore` lists and loads runs, and `/api/v2/runs` and `/api/v2/runs/{run_id}`
   serve them.
5. `Runs`: the events stream, migrated on read.
6. `Runs`: delete to trash, and restore.
7. `Runs`: `llm_calls.jsonl` is recorded, and the explanation route reads it (after the LLM
   call records exist).
8. `Scoring`: skip reasons are recorded and sent, and the skipped-links route serves them.
9. `Storage`: datasets, records and export.
10. `Benchmark`: the arms route.
11. As each UI feature moves (ADR 10), the v1 routes it used are deleted, one router per
    commit. A test fails if the UI client calls a v1 path.
