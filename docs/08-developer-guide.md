# Developer Guide

Practical setup and operation. This reflects what's verified to work in this review (dependencies installed and the test suite run directly), not just what the README asserts.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (the project's dependency/run manager, see `Makefile`)
- Node 18+ (for `crawler-ui/`)

## Install

```bash
git clone <repository-url>
cd CrawlViz
make install
```

### API keys

Link relevance scoring and topic expansion call an LLM through OpenRouter. Copy the example key file and fill in real keys. `keys.json` is gitignored:

```bash
cp keys.example.json keys.json
```

`infrastructure/key_manager.py` supports multiple keys in this file and rotates between them with a cooldown policy, so listing more than one key here is meaningful, not just for redundancy. It's read as a small pool the manager can draw from under load.

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
4. `POST /stop` to end early. This hard-cancels the crawl task and lets `ExportingPipeline` flush its buffer before teardown.

## Backend API surface

| Group | Endpoints |
|---|---|
| Templates | `GET /templates`, `GET /templates/{name}`, `POST /templates?name=`, `PUT /templates/{name}`, `DELETE /templates/{name}` |
| Crawl control | `POST /run`, `POST /stop`, `GET /status` |
| Validation (read-only) | `GET /validation/tables`, `GET /validation/{table}/crawls`, `GET /validation/{table}/sample` |
| Config (read-only) | schema/introspection endpoints over `RuntimeConfig` — see note below |

**Config is read-only from the API in the current build.** `config/runtime_config.py`'s own module docstring states this directly: it's a Pydantic mirror of the constants in `config/config.py`, meant for introspection (so the UI can render what the current configuration *is*), not a write path pipelines actually read from. There is no `PUT`/`PATCH` config endpoint. If you need to change scoring thresholds, the embedding model, or other tuning constants, edit `config/config.py` directly and restart. The schema render shows you what those constants currently are, not a way to set them from the browser yet.

## Testing

**Backend:** 123 tests across 7 files (`test_base_pipeline.py`, `test_blueprint_schema.py`, `test_blueprint_translator.py`, `test_event_wiring.py`, `test_item_extractor.py`, `test_priority_strategy.py`, `test_results_mapper.py`), run and verified passing during this review:

```bash
pip install pytest pytest-asyncio
pytest tests/
```

Note: `test_event_wiring.py` constructs an `LlmHandler`, which requires `keys.json` to exist (even with placeholder values. It doesn't make a real network call in these tests, it just needs the file present). Copy `keys.example.json` to `keys.json` before running the full suite.

`test_event_wiring.py` is worth reading even if you're not modifying this codebase — it's a regression suite that specifically encodes findings from the project's own `docs/V2_ARCHITECTURE.md` audit (e.g. `TestCascadeSubscriptionGap`, asserting `PriorityPipeline` actually receives `HighScoreLinksEvent`). Turning an architecture audit's findings directly into tests is a genuinely useful pattern for preventing the same class of bug from recurring.

**Frontend:** `crawler-ui/` has `vitest` and `@testing-library/react` configured, with tests present for the reducer (`state/reducer.test.js`) and the app shell (`App.test.jsx`):

```bash
cd crawler-ui && npm test
```



## Configuration reference

| Variable | Where | Default |
|---|---|---|
| `CRAWLVIZ_CORS_ORIGINS` | backend env | `http://localhost:5173` |
| `VITE_API_BASE_URL` | `crawler-ui/.env.local` | `http://localhost:8000` |
| `VITE_WS_URL` | `crawler-ui/.env.local` | `ws://localhost:8765` |
| `TRACE_MODE` / `TRACE_SAMPLE_RATE` | backend env | `full` / `0.1`, see `traceability/emitter.py` |

Scoring thresholds (`LOW`/`HIGH` bucket cutoffs), the embedding model name, and export batching live as constants in `config/config.py`.

## Development workflow

```bash
make lint   # ruff (backend) + eslint (frontend)
```

`pyproject.toml` targets `py312` and uses `ruff` at 100-char line length. There's no CI configuration in the repository as reviewed. Linting and testing are developer-invoked, not automated on push.

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
| `config/` | Tuning constants + read-only runtime config schema |
| `services/` | `NLPService`, `ScoringService`, `ResultMapper`, the stable interfaces pipelines call into |
| `templates/` | JSON blueprint examples (`wikiMD.json`, `isi.json`) |
| `tests/` | pytest suite |
| `docs/` | `V2_ARCHITECTURE.md` (the project's own audit) and `crawl_messages.ts` (WS wire protocol) |
| `crawler-ui/` | React/Vite frontend |
