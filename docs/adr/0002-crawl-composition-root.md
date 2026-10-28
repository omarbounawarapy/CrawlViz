# ADR 2: The crawl composition root is a stage registry and self-describing consumers

Status: accepted, 2026-10-28

## Context

`core/crawler.py` is 774 lines, against the 400-line module limit (ARCH-3). Two methods are
far over the 50-line function limit: `_build_pipelines` (about 150 lines, `core/crawler.py:386`)
and `_wire_subscriptions` (about 120 lines, `core/crawler.py:534`). `_build_ui_layer`
(`core/crawler.py:668`) is another 80, most of it a list of event types.

The size is a symptom. The causes are lists that exist in more than one place (ARCH-6,
CODE-1):

1. **Which events a consumer receives is written twice.** Each pipeline has a handler table
   (`handlers`, `state_map`, `_dispatch`) and the crawler has a separate subscription list.
   They have drifted before: `PriorityPipeline` handled `HighScoreLinksEvent` but was never
   subscribed to it, so every high-confidence link was dropped (the fix and its story are in
   `tests/test_event_wiring.py`). They still disagree today: `TelemetryBridge._dispatch` maps
   `ItemExtractionCompletedEvent`, the crawler does not subscribe the bridge to it, and the
   behaviour pins subscribe their bridge to the whole `_dispatch` table
   (`tests/pins/pin_observer.py:46`), so the pins and production wire the bridge differently.
2. **The set of stages is written four times**, each in a different order: construction
   (`_build_pipelines`), subscription (`_wire_subscriptions`), task start (`_collect_tasks`)
   and the queue-depth names (`_QUEUE_STAGES`, `core/crawler.py:225`). A new stage needs four
   edits, and nothing checks that all four were made.
3. **The benchmark copies the stage subscriptions** (`benchmark/runner.py`, `_run`), so a
   wiring fix in the crawler does not reach the benchmark unless someone repeats it there.

The crawler also unpacks the blueprint into a dozen attributes, sets up tracing, and builds
the NLP subsystem. Those parts are short and read well; they are not the problem.

## Decision

1. **Every event consumer says which events it receives**, through a read-only
   `event_types` tuple. Where a consumer has a handler table, `event_types` is derived from it,
   so the two can no longer disagree. `BasePipeline`, `RequestsPipeline` and
   `ExportingPipeline` derive it from `handlers`; consumers that
   dispatch differently (`LoggingPipeline`, `StoppingPipeline`, `FilteringPipeline`,
   `TransformationPipeline`) state it; `SpaceUpdater` derives it from its `handlers` and
   `TelemetryBridge` from `_dispatch`. The structural type is `EventConsumer` in
   `pipelines/contracts.py`.
2. **The composition root subscribes each consumer to its own `event_types`.** It keeps only
   the order. The hand-written subscription lists and the 80 event imports leave
   `core/crawler.py`.
3. **Stages come from one ordered registry**, `STAGES` in `core/stages.py`. Each entry has the
   stage key, the `pipelines.<name>` setting it is shown under (or none), and a builder that
   takes a `StageInputs` value and the stages built so far. The same order is used to build,
   subscribe and start the stages, and `Crawler.queue_depths` reads the setting names from it.
   A new stage is one registry entry plus its builder.
4. **The registry order** is the old subscription order with one change: `retry` moves from
   first to just after `requests`, because its builder needs the requests stage. The
   `SpaceUpdater` and the `TelemetryBridge` are subscribed after the stages.

What stays in `Crawler`: options and defaults, `start()`, blueprint unpacking, tracing setup,
the NLP subsystem, the UI layer, the run manifest, `queue_depths`, `apply_live` and
`_run_until_stopped`.

## Alternatives considered

- **One central subscription table in `core/`** (stage key to event list). It keeps the
  "who reacts to what" view in one file, but it is still a second copy of each handler table,
  which is the copy that caused the `HighScoreLinksEvent` bug. A test can print the full map
  from the live registry when someone needs that view.
- **Build stages from the validated `Blueprint` model** (`config/blueprint_schema.py`)
  instead of the raw dict. Right direction, but the extraction, export and expansion stages
  take dicts today, and the test fixtures are not valid blueprints (`stop_url: None`). It
  belongs with the contract work (CONTRACT-1), not with this split.
- **Keep today's subscription order exactly**, with `retry` first. That needs either a second
  order list or a builder that can reach stages not built yet. Neither is worth it; see
  Consequences for why the order change is safe.
- **Move stage construction into each pipeline class** (`from_config`). That couples every
  pipeline to `RuntimeConfig` and `RuntimePaths`, and the benchmark builds the same pipelines
  with different arguments.

## Consequences

- `core/crawler.py` drops below the module limit and every function below the function limit.
- The subscription set of every consumer is unchanged, except that the `TelemetryBridge`
  now also receives `ItemExtractionCompletedEvent`. Its handler returns no message
  (`ui_bridge/telemetry_bridge.py:472`), so the wire output is unchanged, and production now
  matches what the pins record.
- Dispatch order changes in two places. For `RequestFailedEvent`, `EmptyScoreResultsEvent` and
  `ScoringFailedEvent`, `RetryProcessor` now receives the event after `DebuggingPipeline`
  instead of before. For `StopCrawlEvent`, `SpaceUpdater` now comes after the stages. The
  broker gives each consumer its own task (`core/event_broker.py:48`), and these `put`
  methods only enqueue or set a flag, so no consumer sees different data. The shutdown order
  in `EventBroker._shutdown` follows the same order; each `stop()` only wakes its own workers.
- Task start order follows the registry. Start order only decides which worker loop is
  created first; events already on the bus wait in each stage's queue.
- The behaviour pins run the benchmark runner, not `Crawler`, so they do not cover this
  change. `tests/test_event_wiring.py` and `tests/test_settings_wiring.py` do; the wiring test
  gains a check that every consumer is subscribed to exactly its `event_types`.
- `core/stages.py` holds the cascade and priority arguments that were in `core/crawler.py`, so
  it joins the method files in `.claude/ownership.toml`.

## Standards affected

ARCH-3, ARCH-6, CODE-1, PY-1 (`core/stages.py` is a new module, so it is checked by
`mypy --strict`; `core/crawler.py` stays on the legacy list until it is typed), TEST-2 (pins
unchanged), NAME-5 (the registry is where the planned stage renames become one-line changes).

## Migration and commit plan

1. `Pipelines`: every event consumer names the events it receives (`event_types`), with tests
   that the crawler's current subscriptions equal them.
2. `Crawler`: consumers are subscribed from their own `event_types`.
3. `Crawler`: stages are built, subscribed and started from one registry in `core/stages.py`.
4. `Agents`: `core/stages.py` is a method file.
5. `Benchmark runner`: its stages are subscribed from `event_types`, in its own order. Method
   code, so the research-scientist reviews it; the pins must pass unchanged.
6. `Pins`: `PinObserver` reads `TelemetryBridge.event_types` instead of `_dispatch`.
