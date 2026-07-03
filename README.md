# CrawlViz

CrawlViz is a topic-focused ("semantically guided") web crawler with a
live graph visualizer. Rather than exploring a site exhaustively, it
scores each discovered link against a target topic (via a cheap local
NLP pass, then selectively an LLM call) and prioritizes the crawl
frontier accordingly.

It provides:
- A FastAPI backend to manage crawl templates, start/stop crawling, and expose validation data
- A crawler engine with template-driven domain bootstrapping, extraction, filtering, scoring, and export pipelines
- A WebSocket-driven UI integration layer for live crawl state updates
- A React frontend in `crawler-ui/` for visualization and control

## Repository structure

- `main.py` — FastAPI application entrypoint
- `routes/` — REST API endpoints for templates, crawl control, and validation
- `core/` — crawler bootstrap and main crawler runtime logic
- `models/` — domain, node, storage, extraction, and scoring models
- `pipelines/` — event-driven processing, request handling, filtering, scoring, storage, export, and stop logic
- `nlp/` — embedding, vector store, feature extraction, and expansion support
- `infrastructure/` — network, LLM handling, key management, and async file support
- `ui_bridge/` — WebSocket gateway and snapshot translator for frontend UI
- `traceability/` — trace event instrumentation for LLM, network, and NLP activity
- `config/` — typed runtime configuration constants
- `docs/` — the WebSocket message contract, for reference when touching either side of it
- `crawler-ui/` — React/Vite frontend application

## Quick start

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node 18+.

```bash
git clone <this repo>
cd crawlviz
make install
```

### API keys

The crawler calls an LLM (via [OpenRouter](https://openrouter.ai)) for
relevance scoring and topic expansion. Copy the example key file and
fill in your own key(s) -- `keys.json` is gitignored and never
committed:

```bash
cp keys.example.json keys.json
```

### Pre-cache the embedding model (first run only)

The NLP layer loads `sentence-transformers/all-MiniLM-L6-v2` with
`local_files_only=True`, so it needs to already be cached before the
first crawl:

```bash
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### Run it

```bash
make dev
```

This starts the FastAPI backend on `:8000` and the Vite dev server on
`:5173` together (Ctrl+C stops both). The WebSocket gateway
(`:8765`) is started separately, per crawl, by the crawler itself --
see "How the system works" below. Open `http://localhost:5173`.

Or run each half separately:

```bash
make dev-backend   # uvicorn main:app --reload --port 8000
make dev-frontend  # cd crawler-ui && npm run dev
```

## How the system works

- `main.py` mounts three router groups:
  - `routes/templates.py` for CRUD operations over JSON crawl templates
  - `routes/run.py` for starting, stopping, and checking crawl status
  - `routes/validation.py` for inspecting extraction tables from `items.db`
- Templates (blueprints) are stored as JSON in `templates/` -- see
  `templates/isi.json` or `templates/wikiMD.json` for worked examples,
  the latter matching the topic and parameters used to validate this
  project.
- A crawl is started by posting a template name to `/run`. `core.Crawler`
  reads the blueprint, builds ~16 concurrent pipeline objects, and
  wires them together through a single in-process pub/sub event bus
  (`core.EventBroker`) -- pipelines never call each other directly.
- The cascade per discovered link: cheap NLP similarity scoring first,
  then a budgeted subset gets an LLM relevance call, then a weighted
  priority function ranks the frontier.
- Live state updates are pushed to the browser over WebSocket via
  `ui_bridge.UIWebSocketGateway`, started fresh on `:8765` for each
  crawl (started inside `core.Crawler.start()`, not by `main.py`).

## Backend API

### Templates
- `GET /templates` — list available JSON templates
- `GET /templates/{name}` — retrieve a named template
- `POST /templates?name={name}` — create a new template
- `PUT /templates/{name}` — update an existing template
- `DELETE /templates/{name}` — delete a template

### Crawl control
- `POST /run` — start a crawl using a template name
- `POST /stop` — stop the current crawl (hard-cancels the crawl task)
- `GET /status` — return crawl running state

### Validation
- `GET /validation/tables` — list crawler output tables in `items.db`
- `GET /validation/{table}/crawls` — list crawl groups for a table
- `GET /validation/{table}/sample` — return sample rows from a table

## Configuration

Everything below has a working default; set these only to change it.

| Variable | Where | Default |
|---|---|---|
| `CRAWLVIZ_CORS_ORIGINS` | backend env | `http://localhost:5173` |
| `VITE_API_BASE_URL` | `crawler-ui/.env.local` | `http://localhost:8000` |
| `VITE_WS_URL` | `crawler-ui/.env.local` | `ws://localhost:8765` |
| `TRACE_MODE` / `TRACE_SAMPLE_RATE` | backend env | `full` / `0.1` -- see `traceability/emitter.py` |

Scoring thresholds, embedding model, and other tuning constants live
in `config/config.py`.

## Notes

- The crawler uses `sentence_transformers` for embeddings by default
  (see `nlp/embedding_engine.py`); the LLM provider is OpenRouter
  (`infrastructure/open_router_translator.py`), configured per-blueprint.
- `items.db` (SQLite, WAL mode) holds extracted items; it's created on
  first export and gitignored.
- No automated test suite exists yet -- see suggestions in the PR/issue
  tracker for what to prioritize.

## Development

```bash
make lint   # ruff (backend) + eslint (frontend)
```
