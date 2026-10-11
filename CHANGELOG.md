# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project does not yet use semantic version tags (`pyproject.toml` is pinned at `0.1.0`), so entries are grouped under `[Unreleased]` until the first tagged release.

## [Unreleased]

### Added
- Multi-provider LLM support: OpenRouter, OpenAI, Anthropic, Gemini, NVIDIA (NIM), and Groq, selectable per blueprint via `scoring.params.scoring_type` / `expansion.llm_type`, behind a shared `LlmHandler` abstraction.
- Full documentation set under `docs/` (architecture, execution walkthrough, event-pipeline/semantic-scoring/resilience deep dives, algorithms, research & evaluation, developer guide, design decisions).
- Frontend V2: IDE-style shell with activity bar and docked inspector, Node Inspector with scoring breakdown, Pipeline Monitor with per-stage throughput/errors, traversal-funnel overview, filterable timeline replay, and a schema-driven configuration viewer.
- Checkpoint-based event replay in the frontend reducer, so the UI can scrub to any past point in a crawl without replaying the full event log.
- `RuntimeConfig` Pydantic schema exposed read-only via `/config` and `/config/schema` for UI introspection of tunable scoring/priority constants.
- Pydantic schema validation for assembled blueprints (`routes/blueprint_schema.py`), with translator-level tests.
- Vitest frontend test suite (reducer replay-checkpoint coverage, cross-section smoke tests) and an expanded backend `pytest` suite (248 tests).
- `.github/workflows/ci.yml` running backend (`ruff`, `pytest`) and frontend (`eslint`, `vitest`, `vite build`) checks on every push/PR.
- `CONTRIBUTING.md`, `SECURITY.md`.

### Stabilization (2026-10-01)
Runtime defects were fixed before any crawl-policy comparison. Full list with commit hashes: [`docs/10-stabilization.md`](docs/10-stabilization.md).
- Priority: one scale for trusted and LLM-scored links; an LLM score of 0 is a score; higher-priority nodes are fetched first.
- Termination: `node.ready` resolves on every terminal failure; natural stop completes; time limits fire on a timer; shutdown is bounded.
- Budget: `max_nodes` counts fetched pages; `max_depth` limits admission.
- Isolation: a space is keyed by blueprint and model, stored as npz and json, and read-only unless `persist_space` is set; `items.db` rows are keyed by `(crawl_id, id)`.
- Contracts: blueprints are validated at load (422 on malformed input); LLM responses are typed; decision events carry plain values and a sequence number; the wire protocol lists every emitted message.
- Requests: 429 backoff keys on the HTTP status; `robots.txt` is honoured; URL identity normalizes fragments, trailing slashes and percent-encoding.
- Determinism: seeded RNG streams and explicit concurrency; the same seed gives byte-identical decision records.
- Observability: a run manifest and the UI wire stream are written to `export/<crawl_id>`; the narrative log is JSON lines.
- Export: `POST /stop` keeps rows already buffered; the exporter flushes when its task is cancelled.
- CORS: the origin regex is configurable with `CRAWLVIZ_CORS_ORIGIN_REGEX`.
- Testing: `Crawler` can be built with injectable paths and no `keys.json`; NLP scoring is testable without MiniLM through a hashing embedding engine.

### Changed
- All backend crawl pipelines migrated onto a shared `BasePipeline` (queue + worker-pool + start/stop lifecycle), replacing ad hoc per-pipeline concurrency handling.
- `TemplateManager` renamed to `BlueprintManager` to match the declarative-blueprint terminology used throughout the docs and report.
- Node-state palette and lifecycle states unified into a single 5-state enum shared by backend and frontend.

### Fixed
- Several event-subscription wiring bugs (`RetryProcessor` not subscribed to `RequestFailedEvent`, `PriorityPipeline` not subscribed to `HighScoreLinksEvent`, `LoggingPipeline`'s `StopCrawlEvent` handling, orphaned failure-event subscriptions), caught by regression tests added alongside each fix.
- `StoragePipeline` and `ExportingPipeline` correctly using their own queues/keys instead of silently dropping data.
- `Node.__lt__` guarded against comparison with non-`Node` objects.
- Unused imports flagged by `ruff` across `pipelines/canonicalization_pipeline.py`, `routes/blueprint_schema.py`, `routes/blueprint_translator.py`, and `tests/test_blueprint_schema.py`.

---

Earlier history (pre-changelog) is available via `git log`.
