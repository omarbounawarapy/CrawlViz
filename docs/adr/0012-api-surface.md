# ADR 12: API v2 is a thin HTTP layer over domain services, with one error envelope and only the resources the ranked requirements need

Status: proposed, 2026-10-30

## Context

- The crawl lifecycle lives in the router: module globals `_current_task` and
  `_current_crawler` (`routes/run.py:29-30`), offline session building (`:42-52`) and the
  status shape (`:105-121`). A CLI could not reuse any of it (R-CLI acceptance 1).
- None of the 44 routes declares `response_model` (CONTRACT-2). Errors are raw text:
  `detail=str(exc)` (`routes/run.py:83`, `:88`), which UX-1 forbids and the threat model lists
  as an information leak (SECURITY.md, Phase C rank 12).
- Every crawl writes `events.jsonl` and `manifest.json` to `<export_dir>/<crawl_id>/`
  (`ui_bridge/event_recorder.py:1-10`, `core/crawler.py:331`), but no route lists or serves
  them. `/benchmark/runs` covers benchmark runs only. R-RUNS has nothing to read.
- Datasets are reachable only as samples (`/validation/tables`, `/validation/{table}/crawls`,
  `/validation/{table}/sample`). There is no export (R-EXPORT).
- No route explains a score or a skipped link (R-WHY, R-SKIP-REASON). The wire's
  `CANDIDATE_EVALUATED.decision` has two values, `dropped` and `trusted_no_llm`
  (`docs/crawl_messages.ts:70`).
- Scores reach the UI on different scales: NLP and priority 0 to 1, LLM 0 to 100 (R-SCALE;
  H-02).
- Ranked requirements, approved by Omar: P1 R-WHY, R-HEALTH, R-STATE-TRUTH, R-RUNS, R-EXPORT,
  R-COST-LIVE, R-SKIP-REASON, R-SCALE, R-MODE; then P2 and P3 (`docs/ux/requirements.md`).
  The dropped candidates stay dropped (CODE-3).

## Decision

1. **The service layer is each domain's public API**, not a separate package:
   `crawl.CrawlController` (start, stop, state, outcome, the one current crawl),
   `runs.RunStore` (list, load with migration, delete to trash, restore),
   `storage.Datasets` (list, count, rows) and `runs.write_export` (CSV or JSONL rows, shared
   by dataset and run export). They take and return pydantic models and never import FastAPI.
   Routers in `crawlviz.api` parse, call one service and map the result. The CLI (R-CLI, P3)
   calls the same services in-process.
2. **`/api/v2` prefix.** New and changed resources are mounted under `/api/v2`. Today's routes
   stay where they are until the UI no longer calls them (ADR 10), then they are deleted. API v2
   is frozen at the end of Phase E. After that, a breaking change needs an ADR (ADR 5).
3. **Every route** declares `response_model` and an `operation_id` equal to its client function
   name (NAME-3), so the generated client and the UI use the same names. Each router takes the
   token dependency, and the app adds Host and Origin checks and a JSON content-type check
   (SEC-1, SECURITY.md T2).
4. **One error envelope**: `{"error": {"code", "message", "params", "field"}}`. `code` is a
   snake_case value from a generated enum, and the UI turns it into words (ADR 11). `message`
   is plain English for the CLI and the logs. `field` is the settings path for a validation
   error. Domains raise subclasses of `CrawlvizError` that carry a code and an HTTP status, and
   one handler maps them. An unexpected exception is logged with `crawl_id` and `trace_id` and
   returns `internal_error` with no exception text (CODE-5, OBS-1).
5. **One score display scale (R-SCALE).** `crawlviz.scoring.display_scale` defines, once, the
   factor that takes each score kind (`nlp`, `llm`, `priority`) to 0 to 100. APIs and the wire
   keep raw values under names that say what they are. `/ui-config` serves the table
   (ADR 9). The UI applies it in `formatScore` (ADR 11). Exports apply it in Python. The raw
   cosine value stays available, as secondary text, where it matters.
6. **P1 resources:**

| Route | Returns | Requirements |
|---|---|---|
| `GET /api/v2/ui-config` | ADR 9 | R-MODE, R-SCALE |
| `GET /api/v2/status` | crawl state, crawl id, mode, status board (ADR 8), pages fetched and found, LLM calls used of budget, tokens in and out, cache hits, cost estimate or null, outcome | R-HEALTH, R-STATE-TRUTH, R-COST-LIVE, R-MODE |
| `POST /api/v2/crawls` | 202 with `crawl_id`; `crawl_already_running`, blueprint and settings codes | R-STATE-TRUTH |
| `POST /api/v2/crawls/{crawl_id}/stop` | 202; the outcome becomes `stopped` | R-STATE-TRUTH |
| `GET /api/v2/runs` | run summaries: blueprint name, topic, start time, mode, pages fetched, relevant pages, LLM calls, tokens, end reason, whether it opens and why not; paged with `limit` and `offset` | R-RUNS, R-COST-LIVE, R-MODE |
| `GET /api/v2/runs/{run_id}` | manifest view: blueprint, settings, mode, versions, outcome | R-RUNS |
| `GET /api/v2/runs/{run_id}/events` | NDJSON wire messages at the current protocol, migrated on read (ADR 5) | R-RUNS |
| `DELETE /api/v2/runs/{run_id}` | moves the run to a trash folder; returns when it will be purged | R-RUNS (undo) |
| `POST /api/v2/runs/{run_id}/restore` | brings the run back from the trash | R-RUNS (undo) |
| `GET /api/v2/runs/{run_id}/nodes/{node_id}/explanation` | what decided the score, the cascade bucket and the crawl's thresholds, NLP signals by glossary name, and the LLM call: provider, model, prompt id and hash, rendered prompt, raw reply, tokens, latency, cache hit, outcome | R-WHY |
| `GET /api/v2/runs/{run_id}/nodes/{node_id}/skipped-links` | each skipped link with its reason, deciding score and threshold | R-SKIP-REASON |
| `GET /api/v2/datasets` | each dataset: blueprint name, site, table, record count, runs | R-EXPORT |
| `GET /api/v2/datasets/{dataset_id}/records` | `total` and one page of records | R-EXPORT |
| `GET /api/v2/datasets/{dataset_id}/export` | a CSV or JSONL file (`format`, optional `run_id`), streamed | R-EXPORT |
| `GET /api/v2/benchmark/arms` | each arm: id, whether it calls the network, estimated tokens, available or why not | R-MODE |
| `POST /config/effective` (existing) | gains the resolved mode for the blueprint and its overrides (ADR 9) | R-MODE |

   - The run routes work for the running crawl too, because the recorder writes as it goes.
     That is how R-WHY works the same live and replayed.
   - R-WHY needs a per-call record with the rendered prompt and the raw reply. The LLM layer
     writes it to `llm_calls.jsonl` in the run folder (LLM-3, a versioned format under ADR 5).
     Keys never enter it (SEC-3). Page text in it is data, and the UI renders it as text,
     never as HTML.
   - Skip reasons are one closed list: `below_cutoff`, `not_sampled`, `depth_limit`,
     `duplicate`, `robots_disallowed`, `budget_exhausted`, `unfetched_at_stop`,
     `retries_exhausted`. The wire's `CANDIDATE_EVALUATED` carries the same `skip_reason`
     (ADR 5).
   - Exports stream from SQLite in a worker thread (PERF-3). The columns (extracted fields,
     `url`, `run_id`, `score` on the display scale, `saved_at`) are documented in `docs/`.
7. **P2 and P3 paths are reserved.** Each request and response is designed in its
   requirement's brief and checked by the architect. They are built after the P1 resources.

| Requirement | Route |
|---|---|
| R-LIVE | `PATCH /api/v2/crawls/{crawl_id}/settings` with `persist` |
| R-PREFLIGHT | `POST /api/v2/crawls/preflight` |
| R-RUN-DIFF | `GET /api/v2/runs/{a}/compare/{b}` |
| R-RERUN | `POST /api/v2/runs/{run_id}/rerun`; "Edit and run" reuses `GET /api/v2/runs/{run_id}` |
| R-REPLAY-CACHE | `POST /api/v2/runs/{run_id}/replay` with the cache-miss choice |
| R-PRECEDENCE | `POST /config/effective` gains the source of each field |
| R-PRESET-MERGE | `POST /api/v2/config/presets/{name}/preview` returns the diff |
| R-LOCAL-LLM | `POST /api/v2/llm/providers/{provider}/test` |
| R-BENCH-COMPARE | designed with the Phase G results |
| R-SUMMARY (P3) | no route: the run summary gains the top pages |
| R-CLI (P3) | no route: console commands over the same services |

   No route serves a dropped candidate: semantic search, coverage gaps, space management,
   weight fitting, a prompt playground beyond today's preview, per-domain rules, an MCP
   server, LLM score explanations, config suggestions, LLM crawl summaries.

## Alternatives considered

- **A separate `services/` layer between routers and domains.** It would mostly forward
  calls. Domain public APIs are already the seam ADR 1 asks for (CODE-2).
- **Change today's paths in place.** The UI and the API would have to switch in one commit,
  and nothing could be moved one feature at a time.
- **GraphQL.** One client, a fixed set of screens and generated REST types; GraphQL adds a
  schema layer and a library without a requirement for it.
- **Explanations computed in the UI from the stream.** The stream does not carry the rendered
  prompt or the raw reply, and replayed runs would need the same logic twice.
- **Undo by keeping the run and hiding it.** It leaves deleted data in place, and a delete
  that is never purged is a privacy problem (the requirements' "delete-run privacy" goes with
  R-RUNS).

## Consequences

- `routes/` shrinks to adapters, and its module state moves to `CrawlController`.
- The wire changes (`skip_reason`, mode, board) and the new stored files (`llm_calls.jsonl`,
  manifest mode) go through the contracts-steward under ADR 5, with pin updates reviewed by the
  research-scientist where the wire golden moves.
- Recording rendered prompts and raw replies grows the run folder. The size is reported in
  `/api/v2/runs`, and the trash purge frees it.
- The trash keeps a deleted run for `RUN_TRASH_TTL_S` (a named constant, about the toast
  lifetime plus a margin) and is purged at start-up and on each list.
- The security-reviewer reviews the new routes, especially the run and dataset ids used as
  paths (SEC-2, SECURITY.md Phase C rank 9).

## Standards affected

CONTRACT-2, SEC-1, SEC-2, SEC-3, UX-1, UX-2, NAME-3, NAME-5, CODE-2, CODE-3, CODE-5, PERF-3,
OBS-1, LLM-3, I18N-1, ARCH-4, ARCH-5.

## Migration and commit plan

Phase E (E5), backend-engineer; contracts-steward for models and wire; a test per route.

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
