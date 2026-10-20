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
cp keys.example.json keys.json
```

`infrastructure/key_manager.py` supports multiple keys in this file and rotates between them with a cooldown policy. Listing more than one key gives the manager a small pool to draw from under load.

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
make dev-backend   # uvicorn main:app --reload --port 8000
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

**Config is editable from the API and the Config page.** `config/runtime_config.py` is a validated Pydantic model; the effective values are code defaults, then `settings.json` (only the difference from the defaults is stored), then per-run overrides sent with `POST /run`. Pipelines copy their values at construction, so a saved change applies from the next crawl. Fields flagged `ui_apply: live` (fetch delay and jitter, backoff cap, retry limits, per-pipeline worker counts) can also be pushed to the crawl in progress with `PATCH /config/live`; anything else is rejected with 422. Prompt wording (`prompts`) and provider request URLs (`providers.endpoints`) are settings too; the scoring output format is not editable because the response parser depends on it. Keys added or removed through `/keys` reach a running crawl immediately. Set `CRAWLVIZ_API_TOKEN` to require `Authorization: Bearer <token>` on the config and key routes (the UI sends `VITE_API_TOKEN`); unset, the API is open and should stay bound to localhost. The logging and canonicalization pipelines stay single-worker on purpose, to preserve output order.

## Testing

**Backend:** 248 tests across 26 files, all passing. A full run takes about 70 seconds on the development machine:

```bash
uv run pytest
```

Tests write only under pytest's `tmp_path`. A `Crawler` can be constructed without `keys.json` (`test_construction_needs_no_keys_and_writes_only_under_tmp` in `test_event_wiring.py`).

`test_event_wiring.py` is worth reading even if you're not modifying this codebase. It is a regression suite that encodes earlier defects (e.g. `TestCascadeSubscriptionGap`, which asserts that `PriorityPipeline` receives `HighScoreLinksEvent`). `test_runtime_invariants.py` covers the runtime guarantees fixed during the stabilization phase; see [`10-stabilization.md`](10-stabilization.md).

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

## Development workflow

```bash
make check-changed    # lint, mypy and the fast tests for the files your branch changed
make check            # what CI runs, plus the hook tests
make lint             # ruff (backend) + eslint (frontend)
make typecheck        # mypy --strict
make check-baselines  # the mypy legacy list and ruff baseline did not grow
```

`pyproject.toml` targets `py312` and uses `ruff` at 100-char line length, with the rule sets E, W, F, I, UP, B, SIM, N, RUF, C90 (complexity 10) and PL. mypy runs in strict mode. Violations that existed when a rule was switched on are listed in `[tool.ruff.lint.per-file-ignores]` and in the legacy module list under `[[tool.mypy.overrides]]`. Those lists may only shrink, and a listed file hides new violations of the same kind, so clean a file and remove its entry when you touch it.

pytest reads `pytest.ini`: it imports from the repo root (no `PYTHONPATH`), rejects unregistered markers (`slow`, `pins`, `e2e`, `method_guard`) and fails a test after 300 seconds. `make check-changed` skips tests marked `slow`, and runs the pins and method guards when a method file changed. The full pins take about five minutes.

### CI

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests. The backend job installs with `uv sync --locked --extra dev` (it fails if `uv.lock` is out of date), then runs ruff, mypy, `pytest -m "not pins"`, `pytest -m pins`, and a check that `tests/pins` is unchanged after the run. On pull requests it also runs `tools/check_baselines.py --base origin/main`. The frontend job runs `npm ci`, lint, tests and the build.

## Project layout

| Path | Contents |
|---|---|
| `main.py` | FastAPI entrypoint, mounts the three router groups |
| `routes/` | REST endpoints: templates, run control, validation, config |
| `core/` | Crawler orchestration, event broker/registry, bootstrap |
| `models/` | Domain objects: `Node`, `Link`, `Domain`, `Storage`, extractors, prompt/context builders |
| `pipelines/` | The ~13 event-driven processing stages |
| `nlp/` | Embedding engine, vector space, feature extraction, expansion buffering |
| `infrastructure/` | Network client, LLM handler, key manager, provider translators, async file I/O |
| `priority/` | The three named priority strategies |
| `ui_bridge/` | WebSocket gateway, telemetry bridge, server-side state snapshot |
| `traceability/` | Correlation-ID-based causal tracing, two-tier logging |
| `config/` | Tuning constants, runtime config schema, persisted settings |
| `services/` | `NLPService`, `ScoringService`, `ResultMapper`, the stable interfaces pipelines call into |
| `templates/` | JSON blueprint examples (`wikiMD.json`, `isi.json`) |
| `tests/` | pytest suite |
| `docs/` | These guides and `crawl_messages.ts` (WS wire protocol) |
| `crawler-ui/` | React/Vite frontend |
