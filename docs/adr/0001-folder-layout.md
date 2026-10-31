# ADR 1: Code is grouped by domain in `src/crawlviz/` and by feature in `crawler-ui/src/features/`

Status: proposed, 2026-10-29

## Context

- The backend is 16 top-level packages at the repository root, grouped by technical type:
  `pipelines/`, `events/`, `services/`, `infrastructure/`, `models/`, `utils/`. They import
  only because uvicorn runs from the root (`main.py:5-8`). One feature is spread over many of
  them. Scoring lives in `pipelines/scoring_pipeline.py`, `services/scoring_service.py`,
  `services/llm_contracts.py`, `services/results_mapper.py`, `events/scoring_events.py`,
  `models/scoring_context.py` and `models/prompts.py`. Fetching lives in
  `pipelines/requests_pipeline.py`, `pipelines/robots.py`, `pipelines/retry_processor.py`,
  `infrastructure/network_client.py` and `events/requests_events.py`.
- Code and runtime data share the root: `items.db`, `logs/`, `debug/`, `export/`, `report/`.
- The UI already has `crawler-ui/src/features/` (14 folders), but shared code is grouped by
  type (`src/hooks/`, `src/state/`, `src/utils/`, `src/api/`, `src/theme/`), and 17 feature
  files import `api/client.js` directly. None of the 14 features has an `index` entry point.
- The coding standards (`docs/standards.md`) refer to an ADR 1 for the folder layout, which
  had not been written.

## Decision

**Backend.** One installable package, `src/crawlviz/`, with one subpackage per domain. Each
domain's `__init__.py` is its public API (`__all__`); other domains import only from it, never
from a module inside it. Dependency direction between them is ADR 4.

| Package | Holds | From today |
|---|---|---|
| `app` | entry points: `create_app()`, the console script, later the CLI | `main.py` |
| `api` | HTTP routers and their request and response models (ADR 12) | `routes/` |
| `crawl` | composition root, stage registry, event broker, live settings, bootstrap, `CrawlController` | `core/`, crawl state in `routes/run.py` |
| `config` | `RuntimeConfig` aggregate, settings store, blueprint schema and translator, paths | `config/` |
| `telemetry` | telemetry observer, WebSocket gateway, crawl snapshot, subsystem status (ADR 8), crawl and debug logs | `ui_bridge/`, logging and debugging pipelines |
| `runs` | run recorder, manifest, run store and export | `ui_bridge/event_recorder.py` |
| `fetch` | fetch and retry stages, robots, politeness | requests and retry pipelines, `pipelines/robots.py` |
| `extract` | link and item extraction, canonicalisation, filtering, transformation | processing, canonicalization, filtering, transformation pipelines; extractors in `models/` |
| `scoring` | scoring stage and service, results mapping, LLM output models, cascade | `pipelines/scoring_pipeline.py`, `services/` scoring files |
| `priority` | priority stage, strategies, frontier queue | `priority/`, `pipelines/priority_pipeline.py`, `pipelines/frontier_queue.py` |
| `storage` | storage and export sinks, item store | storage and exporting pipelines, `models/storage.py` |
| `nlp` | embeddings, vector space, features, space store, updater and bootstrap, NLP service | `nlp/`, `services/nlp_service.py`, `services/link_features.py`, `services/space_bootstrap.py` |
| `llm` | `LlmClient`, provider adapters, keys, call budget, token usage, prompts | `infrastructure/` LLM files, `traceability/traced_llm_handler.py` |
| `events` | event types (the contract between stages), consumer protocol, `BasePipeline` | `events/`, `pipelines/base_pipeline.py`, `pipelines/contracts.py` |
| `shared` | `Link`, `Node`, `Domain`, utilities, HTTP client, trace context | `models/` kernel types, `utils/`, `infrastructure/network_client.py`, `traceability/` core |
| `benchmark` | frozen-graph benchmark, judges, audit, analysis | `benchmark/` |
| `offline` | offline doubles and session | `offline/` |

- Event types stay in one `events` package, one module per stage, and do not move into the
  stage domains. Stages form a loop (fetch, extract, score, prioritise, fetch), so a stage
  importing the events of the stage before it would make a cycle.
- Inside a domain: `__init__.py`, one module per responsibility, and `settings.py` for its
  settings section (ADR 7). Tests move to `tests/<domain>/`.
- `main.py` stays at the root as a one-line shim (`from crawlviz.app import app`) until the
  Makefile, docs and Docker use the console script, then it is removed.
- Runtime data is not package content. Its location stays with `RuntimePaths`
  (`config/paths.py`); this ADR does not move it.

**Frontend.** `crawler-ui/src/` has three top folders: `app/` (shell, routing, providers),
`features/<feature>/` and `shared/`. Each feature exposes `index.ts`; nothing imports a path
inside another feature. `shared/` holds `ui/` (design system), `api/` (generated types and the
one HTTP client), `lib/` (`format.ts` and other pure helpers) and generic hooks. The inside of
a feature, containers and the crawl session store are ADR 10.

## Alternatives considered

- **Keep the type-based packages and add `src/`.** It satisfies packaging, but code would still
  be grouped by file type: a change to scoring would still touch six packages.
- **One distribution per domain** (workspace packages). Real boundaries, but separate builds,
  versions and lockfile entries for a single-process app that one package serves.
- **Events inside each domain.** Reads well per domain but creates cycles along the stage loop,
  as above.
- **Move the whole tree in one commit.** Too large to review, and it leaves no green commit to
  bisect.

## Consequences

- A change to one feature touches one backend package and one UI feature folder.
- `tests/test_import_cycles.py` walks `src/crawlviz/` and gains a check that cross-domain
  imports name only `crawlviz.<domain>`. ESLint `no-restricted-imports` does the same for
  `features/*/*` paths.
- Files that can change scores or visit order keep their extra checks: the pins and method
  guards still run when they change. The list of those files moves with each domain, in the
  same series.
- `uv run` and the Makefile use the installed package. `CRAWLVIZ_OFFLINE=1 make dev` must keep
  working at every commit.

## Standards affected

- Code is grouped by domain or feature, not by file type.
- Other areas use a domain or feature only through its `__init__.py` or `index.ts`.
- Dependencies point one way (ADR 4).
- The simplest design that meets the need.
- Small commits, each green on its own; package moves go one domain at a time.
- Behaviour pins pass unchanged: a move changes no behaviour.
- Docs change with the code: the package table in `docs/08-developer-guide.md` changes with
  each domain.

## Migration and commit plan

One domain per short series. Pins pass unchanged at every commit.

1. `Packaging`: `crawlviz` builds from `src/` with a console script; `main.py` imports from it.
2. Per domain, leaves first (`shared`, `events`, `llm`, `nlp`, then the stage domains,
   `telemetry`, `runs`, `config`, `crawl`, `api`, `app`; `offline` and `benchmark` last):
   1. `git mv` into `src/crawlviz/<domain>/`, with a generated re-export module at each old
      import path so the commit is green.
   2. Import fix: callers move to `crawlviz.<domain>` (mechanical).
   3. The re-export modules are deleted, and the list of score-affecting files and the
      developer guide's package table are updated.
3. `Tests`: the cross-domain import check is added once the first two domains have moved.
4. Frontend: one feature per series, after the backend moves (ADR 10).
