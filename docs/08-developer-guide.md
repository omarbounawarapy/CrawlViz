# Developer Guide

Setup and operation, as run on the development machine.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (the project's dependency/run manager, see `Makefile`)
- Node 22.12+ (for `crawler-ui/`; running the frontend test suite specifically needs Node 22.22.2+/24.15.0+, per `jsdom`'s `engines` field)

## Install

```bash
git clone <repository-url>
cd CrawlViz
make install
```

### API keys

Link relevance scoring and topic expansion call an LLM. Six providers are supported through the same `LlmHandler` abstraction: OpenRouter, OpenAI, Anthropic, Google Gemini, NVIDIA (NIM), and Groq. Pick one per blueprint with `scoring.params.scoring_type` and `expansion.llm_type`. Copy the example key file and fill in real keys for whichever provider(s) you plan to use. `keys.json` is gitignored:

```bash
install -m 600 keys.example.json keys.json
```

`src/crawlviz/llm/key_manager.py` supports multiple keys in this file and rotates between them with a cooldown policy. Listing more than one key gives the manager a small pool to draw from under load.

### Pre-cache the embedding model

The NLP layer loads `sentence-transformers/all-MiniLM-L6-v2` with `local_files_only=True`. It must already be cached locally before the first crawl, or the process will fail to start the NLP service:

```bash
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

## Running it

```bash
make dev
```

Starts the FastAPI backend on `:8000` and the Vite dev server on `:5173`. The WebSocket gateway (`:8765`) is *not* started by this. It's started per-crawl, inside `core.Crawler.start()`, and only exists while a crawl is running. Open `http://localhost:5173`.

Or separately:

```bash
make dev-backend   # uvicorn main:app --reload --reload-exclude <repo>/.claude --port 8000
make dev-frontend  # cd crawler-ui && npm run dev
```

## Running a crawl

1. Select or create a blueprint via the UI's configuration screen, or drop a JSON file into `templates/` directly (see `templates/wikiMD.json` for a complete worked example matching the project report's case study, or `templates/isi.json` for a second reference).
2. `POST /run` with the template name (or use the Run screen in the UI).
3. Watch it live in the UI, or query `GET /status` from the REST API.
4. `POST /stop` to end early. This cancels the crawl task. The exporter flushes its buffer when cancelled, so rows already collected are kept. The graceful `StopCrawlEvent` path (stop conditions) takes the same flush.

## Backend API surface

| Group | Endpoints |
|---|---|
| Templates | `GET /templates`, `GET /templates/{name}`, `POST /templates?name=`, `PUT /templates/{name}`, `DELETE /templates/{name}` |
| Crawl control | `POST /run`, `POST /stop`, `GET /status` |
| Validation (read-only) | `GET /validation/tables`, `GET /validation/{table}/crawls`, `GET /validation/{table}/sample` |
| Config | schema, values, save, presets, live apply, keys over `RuntimeConfig`, see note below |

**Config is editable from the API and the Config page.** `config/runtime_config.py` is a validated Pydantic model; the effective values are code defaults, then `settings.json` (only the difference from the defaults is stored), then per-run overrides sent with `POST /run`. Pipelines copy their values at construction, so a saved change applies from the next crawl. Fields flagged `ui_apply: live` (fetch delay and jitter, backoff cap, retry limits, per-pipeline worker counts) can also be pushed to the crawl in progress with `PATCH /config/live`; anything else is rejected with 422. Prompt wording (`prompts`) and provider request URLs (`providers.endpoints`) are settings too; the scoring output format is not editable because the response parser depends on it. `POST /config/validate` and `PUT /config/replace` both accept a copy of `settings.json` that carries `schema_version` and the old pipeline section names, and read it at the current version. A `schema_version` newer than this build is refused: `PUT /config/replace` answers 422 with a message telling the user to update CrawlViz, and `POST /config/validate` reports the same message with `valid: false`. Keys added or removed through `/keys` reach a running crawl immediately. Set `CRAWLVIZ_API_TOKEN` to require `Authorization: Bearer <token>` on the config and key routes (the UI sends `VITE_API_TOKEN`); unset, the API is open and should stay bound to localhost. The logging and canonicalization pipelines stay single-worker on purpose, to preserve output order.

## Testing

**Backend:** 248 tests across 26 files, all passing. A full run takes about 70 seconds on the development machine:

```bash
uv run pytest
```

Tests write only under pytest's `tmp_path`. A `Crawler` can be constructed without `keys.json` (`test_construction_needs_no_keys_and_writes_only_under_tmp` in `test_event_wiring.py`).

`test_event_wiring.py` is worth reading even if you're not modifying this codebase. It is a regression suite that encodes earlier defects (e.g. `TestCascadeSubscriptionGap`, which asserts that `PrioritizeStage` receives `HighScoreLinksEvent`). `test_runtime_invariants.py` covers the runtime guarantees fixed during the stabilization phase; see [`10-stabilization.md`](10-stabilization.md).

**Frontend:** `crawler-ui/` has `vitest` and `@testing-library/react` configured, with tests present for the reducer (`state/reducer.test.js`) and the app shell (`App.test.jsx`):

```bash
cd crawler-ui && npm test
```



## Configuration reference

| Variable | Where | Default |
|---|---|---|
| `CRAWLVIZ_CORS_ORIGINS` | backend env | `http://localhost:5173` (exact origins, comma-separated) |
| `CRAWLVIZ_CORS_ORIGIN_REGEX` | backend env | any `localhost` or `127.0.0.1` port, so Vite's fallback ports work. Set to an empty string for a deployment that should allow only `CRAWLVIZ_CORS_ORIGINS` |
| `VITE_API_BASE_URL` | `crawler-ui/.env.local` | `http://localhost:8000` |
| `VITE_WS_URL` | `crawler-ui/.env.local` | `ws://localhost:8765` |
| `TRACE_MODE` / `TRACE_SAMPLE_RATE` | backend env | `full` / `0.1`, see `traceability/emitter.py` |

Scoring thresholds (`LOW`/`HIGH` bucket cutoffs), the embedding model name, and export batching are the defaults in `config/config.py`; the Config page overrides them without editing the file.

### Stored files and their versions

Every file CrawlViz writes carries an integer `schema_version`, currently 1 for all of them (`src/crawlviz/contracts/stored_formats.py`).

| File | Shape |
|---|---|
| `settings.json` | the settings patch, plus `schema_version` |
| `presets.json` | `{"schema_version": 1, "presets": {"<name>": <settings patch>}}` |
| saved blueprints in `templates/` | the blueprint, plus `schema_version` |
| `manifest.json` of a run | the manifest, plus `schema_version` |

- A file without `schema_version` is version 0. It loads and is migrated in memory; nothing is written back until the file is saved again. An old `presets.json`, which was `{"<name>": <patch>}`, is read as the `presets` object.
- A file with a newer version than the running build is refused. The message names both versions and says to update CrawlViz.
- A refused or damaged `settings.json` stops the settings from loading. A full settings reset from the Config page replaces it without reading it.

### Settings sections and unknown keys

The `pipelines.<key>` sections are `extract`, `fetch`, `score`, `storage`, `filter`, `prioritize`, `transform`, `debug_log` and `retry`. The older names `processing`, `requests`, `scoring`, `filtering`, `priority`, `transformation` and `debugging` are still read in `settings.json`, in presets, in REST patches and in live patches, and are stored under the new names. A patch that holds one section under both its old and new name is refused, and the message names both keys. The `queues` object of `GET /status` uses the new keys.

Settings models reject keys they do not define. The error names the path, for example `pipelines.fetchh`, so a misspelt setting is reported instead of ignored.

## Logging and health checks

Logs go to stderr, configured once by `traceability/logging_setup.py` when the API or a crawl starts. Two environment variables control them:

| Variable | Values | Default |
|---|---|---|
| `CRAWLVIZ_LOG_FORMAT` | `json` (one JSON object per line) or `text` (one readable line) | `json` |
| `CRAWLVIZ_LOG_LEVEL` | a level name such as `DEBUG`, `INFO` or `WARNING` | `INFO` |

Any other value stops startup with an error that names the variable. uvicorn's own loggers use the same format.

A JSON line has `ts` (UTC, ISO 8601, milliseconds), `level`, `logger` and `message`. An `exception` field holds the traceback when the record has one. `crawl_id`, `node_id` and `trace_id` are added when they are set for the code that logged and left out otherwise. `crawl_id` is bound for the whole run; `trace_id` and `node_id` are bound per node by the stages. In `text` format the ids are appended as `[crawl_id=... node_id=... trace_id=...]`.

`src/crawlviz/shared/log_redaction.py` removes secrets from the message and the traceback before a line is written, in two ways:

- Registered values: the session token at startup, and provider keys when a crawl starts or a key is added through `/keys`. Every exact occurrence becomes `[redacted]`. Values shorter than 8 characters are not registered.
- Credential shapes: `Authorization: Bearer ...` and `key=`, `token:`, `secret=` or `password=` pairs with a value of 8 or more characters, such as a `?key=` in a provider URL, are redacted even if never registered.

Two probe routes report on the process:

| Route | Answers |
|---|---|
| `GET /health` | `{"status": "ok"}` whenever the process runs. It reads and writes nothing. |
| `GET /ready` | 200 with `{"ready": true, "checks": [...]}` when the stored settings load and every folder a crawl writes to exists or can be created and is writable. Otherwise 503 with the same shape, and each failed check has `ok: false` and a `detail` saying what to fix. |

The checks are named `settings`, `settings_dir`, `items_db_dir`, `export_dir`, `log_dir`, `debug_dir`, `space_store_dir` and `presets_dir`. `/ready` never creates a folder. Both routes need the session token (`Authorization: Bearer <token>`) and pass the Host and Origin checks like every other route. The behaviour is covered by `tests/test_logging_pipeline.py`, `tests/test_logging_wiring.py`, `tests/test_traceability_logging_setup.py` and `tests/test_health_routes.py`.

## Development workflow

```bash
make check-changed    # lint, mypy and the fast tests for the files your branch changed
make check            # what CI runs
make lint             # ruff (backend) + eslint (frontend)
make typecheck        # mypy --strict
make check-baselines  # the mypy legacy list and ruff baseline did not grow
```

`pyproject.toml` targets `py312` and uses `ruff` at 100-char line length, with the rule sets E, W, F, I, UP, B, SIM, N, RUF, C90 (complexity 10) and PL. mypy runs in strict mode. Violations that existed when a rule was switched on are listed in `[tool.ruff.lint.per-file-ignores]` and in the legacy module list under `[[tool.mypy.overrides]]`. Those lists may only shrink, and a listed file hides new violations of the same kind, so clean a file and remove its entry when you touch it.

pytest reads `pytest.ini`: it imports from the repo root (no `PYTHONPATH`), rejects unregistered markers (`slow`, `pins`, `e2e`, `method_guard`) and fails a test after 300 seconds. `make check-changed` skips tests marked `slow`, and runs the pins and method guards when a method file changed. The 36 pins took 43 seconds on a quiet machine, and several minutes when other jobs shared it.

### CI

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests. The backend job installs with `uv sync --locked --extra dev` (it fails if `uv.lock` is out of date), then runs ruff, mypy, `pytest -m "not pins"`, `pytest -m pins`, and a check that `tests/pins` is unchanged after the run. On pull requests it also runs `tools/check_baselines.py --base origin/main`. The frontend job runs `npm ci`, lint, tests and the build.

## Project layout

| Path | Contents |
|---|---|
| `main.py` | FastAPI entrypoint, mounts the three router groups |
| `routes/` | REST endpoints: templates, run control, validation, config |
| `core/` | Crawler orchestration, event broker/registry, bootstrap |
| `models/` | `Storage`, extractors, prompt/context builders |
| `pipelines/` | The ~13 event-driven processing stages |
| `src/crawlviz/nlp/` | Embedding engine, vector space, feature extraction, expansion buffering |
| `src/crawlviz/shared/` | `Link`, `Node`, `Domain`, guarded network client, URL guard, fetch errors, trace context, log redaction, atomic writes, hashing and HTML helpers |
| `infrastructure/` | Async file handler and log writer |
| `src/crawlviz/priority/` | The three named priority strategies |
| `src/crawlviz/llm/` | LLM handler, six provider translators, key manager, endpoints, call budget, token usage, and the typed layer (`LlmClient`, request and response types, JSON output validation, prompt registry, call recorder, cost table) |
| `src/crawlviz/contracts/` | Stored-format versions and the pipeline settings migration |
| `ui_bridge/` | WebSocket gateway, telemetry bridge, server-side state snapshot |
| `traceability/` | Correlation-ID-based causal tracing, two-tier logging |
| `config/` | Tuning constants, runtime config schema, persisted settings |
| `services/` | `NLPService`, `ScoringService`, `ResultMapper`, the stable interfaces pipelines call into |
| `templates/` | JSON blueprint examples (`wikiMD.json`, `isi.json`) |
| `src/crawlviz/events/` | Event types, one module per stage |
| `src/crawlviz/offline/` | Offline doubles: scripted LLM, demo session, site script |
| `tests/` | pytest suite |
| `docs/` | These guides and `crawl_messages.ts` (WS wire protocol) |
| `crawler-ui/` | React/Vite frontend |

**Where things moved.** The backend is moving into `src/crawlviz/` one package at a time. `contracts`, `events`, `llm`, `nlp`, `priority` and `offline` are there now, so import them as `from crawlviz.llm import ...` and the same form for the others. The other packages in the table still sit at the repository root and import as before.
