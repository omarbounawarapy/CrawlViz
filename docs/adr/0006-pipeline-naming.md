# ADR 6: Every pipeline part has one name and one snake_case key, from class to UI label

Status: proposed, 2026-10-29

## Context

- One stage can carry four names. The fetch stage is the class `RequestsPipeline`, the
  registry key and setting `requests` (`core/stages.py:285`), the wire stage `request`
  (`docs/crawl_messages.ts:48`), and the verb "fetch" in its own event, `PageFetchedEvent`. The
  extraction stage is `ProcessingPipeline`, key `processing`, wire `extraction`. The export
  stage is `ExportingPipeline`, key `exporting`, wire `export`.
- "Pipeline" names parts that are not pipelines: the narrative log writer
  (`pipelines/logging_pipeline.py:21`), the debug log writer (`pipelines/debugging_pipeline.py:80`),
  the stop-condition watcher (`StoppingPipeline`). Others use other suffixes for the same role:
  `RetryProcessor`, `SpaceUpdater`, `TelemetryBridge`.
- Event names follow no pattern: `PageFetchedEvent` and `RequestFailedEvent` come from one
  stage; `ProcessingExtractionFailedEvent`, `FilteringPipelineErrorEvent` and
  `RetryOperationFailedEvent` are three shapes for one kind of event; `NodeAddedEvent` and
  `StorageNodeAddedEvent` both exist (`events/storage_events.py:25`, `:73`).
- Since ADR 2, each stage is one `STAGES` entry, so a key rename is a one-line registry change
  plus its config, wire and UI copies.
- No pin golden stores a class or event name (grep of `tests/pins/golden/`). The wire golden
  stores stage keys: `request`, `extraction`, `filtering`, `scoring`, `priority`,
  `transformation`.

## Decision

1. **Roles and suffixes.**
   - A *stage* does crawl work and publishes the events that drive the crawl: `<Verb>Stage`.
   - A *sink* writes events out (file, database) and publishes only its own outcome:
     `<Noun>Sink`.
   - An *observer* reads events and never publishes or changes crawl state: `<Noun>Observer`.
   - A *controller* decides the crawl's lifecycle or settings: `<Noun>Controller`.
2. **One key.** Each part has one snake_case key, used as the module name, the registry key,
   the `pipelines.<key>` settings section, the wire `stage` value and the UI catalog key. The
   UI label comes from the catalog ("Fetch"), never from the key.

| Today | New name | Key |
|---|---|---|
| `RequestsPipeline` | `FetchStage` | `fetch` |
| `RetryProcessor` | `RetryStage` | `retry` |
| `ProcessingPipeline` | `ExtractStage` | `extract` |
| `CanonicalizationPipeline` | `CanonicalizeStage` | `canonicalize` |
| `ScoringPipeline` | `ScoreStage` | `score` |
| `FilteringPipeline` | `FilterStage` | `filter` |
| `PriorityPipeline` | `PrioritizeStage` | `prioritize` |
| `TransformationPipeline` | `TransformStage` | `transform` |
| `SpaceUpdater` | `UpdateSpaceStage` | `update_space` |
| `StoragePipeline` | `StorageSink` | `storage` |
| `ExportingPipeline` | `ExportSink` | `export` |
| `LoggingPipeline` | `CrawlLogSink` | `crawl_log` |
| `DebuggingPipeline` | `DebugLogSink` | `debug_log` |
| `TelemetryBridge` | `TelemetryObserver` | `telemetry` |
| `StoppingPipeline` | `StopController` | `stop` |
| `apply_live` (`core/live_settings.py`) | `LiveSettingsController` | `live_settings` |
| crawl state in `routes/run.py` | `CrawlController` (ADR 12) | `crawl` |

3. **Events.** `<Stage><Subject?><PastVerb>Event`, where `<Stage>` is the key in PascalCase,
   and every failure is `<Stage>FailedEvent` carrying an `error_type` and the failed input. For
   example `PageFetchedEvent` becomes `FetchCompletedEvent`, `RequestFailedEvent` becomes
   `FetchFailedEvent`, `LinksScoredEvent` becomes `ScoreCompletedEvent`,
   `HighScoreLinksEvent` becomes `ScoreTrustedLinksSelectedEvent`, and
   `FilteringPipelineErrorEvent` becomes `FilterFailedEvent`. Before the event renames start,
   one table lists every event with its new name, and it is reviewed as a whole. That table
   settles the `NodeAddedEvent` and `StorageNodeAddedEvent` pair: either one goes, or the two
   get names that say how they differ.
4. **Not renamed:** wire message types (`NODE_ADDED`, `PIPELINE_EVENT`), which already follow
   their own scheme, and the scoring prompt and its output format (a method change).

## Alternatives considered

- **Keep the class names and only align the keys.** Removes the four-name problem but leaves
  "Pipeline" meaning five roles, so a reader still cannot tell a sink from a stage.
- **Nouns for stages (`FetcherStage`, `ScoringStage`).** Either works. The project's naming
  convention already says `<Verb>Stage`, and a verb key reads as the action in the Pipeline
  Monitor ("fetch", "score").
- **Rename everything in one commit.** No commit would be small enough to review or bisect,
  and one bad rename would hide in a thousand-line diff.

## Consequences

- Class and event renames change no pin. The wire key rename changes the `stage` values in
  `wire_messages.jsonl`. Preferred: the pin comparison migrates each golden through the
  recording migration chain (ADR 5) before comparing, so the goldens stay byte-identical and
  the migration is tested on real data. The fallback is a one-time `--update-pins` with the
  rename as the reason. The choice between them is made when the wire keys are renamed.
- The settings keys `pipelines.requests`, `pipelines.processing`, `pipelines.debugging` and
  the others move through the settings migration (ADR 5), so stored files and presets keep
  loading.
- `core/stages.py` can change scores or visit order, so each registry rename is reviewed as a
  possible method change, with the pins and method guards passing. A rename does not change
  any value.

## Standards affected

- Pipeline parts are named `<Verb>Stage`, `<Noun>Sink`, `<Noun>Observer` or
  `<Noun>Controller`, with one snake_case key from module to UI.
- Names say why a thing exists and what it does.
- Domain terms come from the glossary, which gains stage, sink, observer and controller.
- Each list has one source: the stage registry.
- Stored files and wire messages carry a version with a migration chain.
- Behaviour pins pass unchanged, or change only through a reviewed update.
- Small commits, each green on its own.
- UI labels come from the copy catalogs.

## Migration and commit plan

After the ADR 1 move of the stage domains:

1. Per part, one commit each: the class is renamed, and the old name stays as an alias in the
   same module (`RequestsPipeline = FetchStage`). Callers move in the same commit when there
   are few, otherwise in the next.
2. Events, one module per commit, with aliases, following the event table.
3. `Settings`: migration from the old section keys to the new ones, with fixtures.
4. `Wire`: stage keys match the registry keys. Backend, generated `wire.ts`, the UI catalog and
   the recording migration land in one commit, so no commit has a UI that misreads the stream.
5. `Pipelines`: the aliases are removed, one commit for classes and one for events.
