# ADR 5: Stored files and wire messages carry a version, migrate on read, and generate their types

Status: proposed, 2026-10-29

## Context

- Nothing the app stores or sends carries a version. `schema_version` and `protocol` appear
  only in the benchmark graph code (`benchmark/graph.py`). The run recording
  (`<export_dir>/<crawl_id>/events.jsonl` and `manifest.json`, `ui_bridge/event_recorder.py:1-10`,
  `core/crawler.py:310-321`), the settings file (`config/settings_store.py:51`, `read_stored`),
  presets, blueprint files and benchmark run records are all unversioned.
- Names are about to change. ADR 6 renames the wire stage `request` to `fetch` and
  `extraction` to `extract`; the pin goldens hold those names
  (`tests/pins/golden/synthetic/wire_messages.jsonl`: 208 `"stage": "request"`). A planned
  runs page has to open a recording made before such a rename, or say why it cannot.
- The wire contract is hand-written TypeScript (`docs/crawl_messages.ts`), checked against the
  bridge by `tests/test_wire_protocol.py`. The UI does not import it; `crawler-ui/src/api/client.js`
  is untyped.
- None of the 44 REST routes declares `response_model` (grep of `routes/`), so the OpenAPI
  document has no response shapes to generate types from.

## Decision

1. **Versions.** Each stored format has an integer `schema_version`: settings file, preset,
   blueprint, run manifest, recording header, benchmark run record. The wire has one integer
   `protocol`, sent in `SNAPSHOT_FULL` and in the recording's first line. A file with no version
   is version 0, today's format.
2. **One migration mechanism.** `crawlviz.shared.versioning` holds a `MigrationChain`: an
   ordered list of pure functions on plain dicts, each from version N to N+1. Each format
   registers its chain in its owning domain (`config`, `runs`, `benchmark`). Loading reads the
   version, applies the chain to the current version, then validates with the pydantic model.
   A version newer than the code is refused with a message that names both versions.
3. **Migrate on read, in the backend.** Old recordings are migrated when the runs API serves
   them (ADR 12). The live wire only ever sends the current protocol, and the UI handles only
   the current protocol, so it keeps one reducer. The alias map for renamed names (stage keys,
   event fields) is the migration from the protocol before the rename.
4. **Writers write the current version only.** A migrated settings file is written back only
   on the next save, never silently on load.
5. **Strict models.** Every config and stored-format model sets `extra="forbid"`. An unknown
   key left after migration fails the load with the key path and the next step, instead of
   being dropped.
6. **What bumps a version.** Renaming or removing a field, or changing its meaning or unit,
   bumps the version and adds a migration with a fixture. Adding an optional field does not.
   A breaking change to a REST resource after the API v2 freeze needs an ADR.
7. **Generated types.** Pydantic models are the source of truth:
   - Wire messages become models in `crawlviz.telemetry.messages`. A generator writes
     `crawler-ui/src/shared/api/wire.ts` from their JSON Schema, and `docs/crawl_messages.ts`
     is replaced by that file.
   - Every route declares `response_model`. `openapi.json` is generated and committed, and
     `crawler-ui/src/shared/api/openapi.ts` is generated from it.
   - The config-fixture types the UI tests use come from the same JSON Schema.
   - CI regenerates all three and fails on any diff.

## Alternatives considered

- **Version in the file name or folder** (`runs/v2/...`). Breaks every path already recorded,
  and a file copied elsewhere loses its version.
- **Migrate in the UI.** The reducer would carry every old protocol forever, and a planned
  command-line export would need a second copy of the migrations.
- **A schema registry or Protobuf.** Built for many services and languages; here one Python
  process feeds one UI, and a version number with a migration list is enough.
- **Hand-written TypeScript kept in sync by tests.** This is today's state. The test catches
  drift in message names, not in field types.

## Consequences

- Each format gets `tests/fixtures/contracts/<format>/v<N>.json` fixtures and a test that every
  fixture loads and migrates.
- Adding `protocol` to `SNAPSHOT_FULL` changes the wire golden. That pin update goes in its own
  reviewed commit; it is not a method change. ADR 6 decides how the rename reaches the pins.
- The generators for TypeScript (`openapi-typescript`, `json-schema-to-typescript`, or
  equivalent) are new development dependencies.
- A new version is one reviewed change: the model, its migration, a fixture and the
  regenerated types land together.

## Standards affected

- Stored files and wire messages carry a version with a migration chain; config models forbid
  unknown keys.
- REST endpoints declare their response model; OpenAPI, wire and config-fixture types are
  generated, and CI fails on drift.
- Strict TypeScript, with API types generated rather than written by hand.
- Test coverage only goes up: every format version has a fixture.
- Every error says what happened and what to do next.
- No logic in two places: one migration mechanism.
- Run manifests are versioned, so a recorded run stays reproducible.

## Migration and commit plan

1. `Contracts`: `MigrationChain` with unit tests; no format uses it yet.
2. `Settings`: the settings file carries `schema_version` 1; version 0 migrates unchanged, with
   a fixture.
3. `Presets` and `Blueprints`: the same, one commit each.
4. `Runs`: the manifest and the recording header carry `schema_version`; old recordings load
   as version 0.
5. `Wire`: wire messages are pydantic models, and the bridge output is unchanged byte for byte
   (pins unchanged).
6. `Wire`: `wire.ts` is generated; `tests/test_wire_protocol.py` checks the generated file, and
   `docs/crawl_messages.ts` is removed in its own commit.
7. `Wire`: `SNAPSHOT_FULL` carries `protocol` 1 (pin update, reviewed).
8. `API`: `response_model` on each router, one router per commit, then `openapi.ts` generation
   and the CI drift check.
9. `Config`: `extra="forbid"` on every section that still lacks it, with fixtures for the
   keys older files used.
