# ADR 4: Backend layers import downwards only, and import-linter enforces the order

Status: proposed, 2026-10-29

## Context

- `tests/test_import_cycles.py` blocks cycles between top-level packages, lazy imports
  included. It does not say which way a dependency may point, so a new `nlp -> routes`
  import passes as long as `routes` does not import `nlp` back.
- Today's package graph (AST walk of every backend module, 2026-10-29):
  `routes -> benchmark config core infrastructure models offline`,
  `core -> config events infrastructure models nlp pipelines services traceability ui_bridge utils`,
  `pipelines -> config events infrastructure models priority traceability utils`,
  `config -> models priority`, `infrastructure -> config`, `ui_bridge -> config events`,
  `offline -> benchmark config models`.
- `config` sits both above and below the domains. It imports `priority.strategy` for the
  strategy registry and weights (`config/blueprint_schema.py:42`, `config/runtime_config.py:46`),
  while stages, the LLM layer and the UI bridge import `config` for `RuntimeConfig` and loose
  constants (`LLM_DEFAULT_ENDPOINTS`, `NLP_COMPOSITE_WEIGHTS`, `ITEMS_DB_PATH`, `BASE_DIR`).
  That two-way pull is why weights and defaults exist in several places (ADR 7 lists them).
- The coding standards (`docs/standards.md`) already plan import-linter in CI to check that
  dependencies point one way.

## Decision

The packages of ADR 1 form these layers, highest first. A package may import any package in
a lower layer, never one in its own layer unless listed, and never one above.

| Layer | Packages | Same-layer imports |
|---|---|---|
| 1 | `app` | |
| 2 | `api` | |
| 3 | `offline` | |
| 4 | `benchmark` | |
| 5 | `crawl` | |
| 6 | `config` | |
| 7 | `telemetry`, `runs` | none (independent) |
| 8 | `fetch`, `extract`, `scoring`, `priority`, `storage` | none: stages talk through events only |
| 9 | `nlp` | |
| 10 | `llm` | |
| 11 | `events` | |
| 12 | `shared` | |

1. **Stage domains do not import `config`.** Each domain defines its settings section model
   in its own `settings.py` (ADR 7), and its classes take that section, or plain values, as
   constructor arguments. `config` composes `RuntimeConfig` from the sections, which is why it
   sits above them. Loose constants move, as named constants, to the module that owns them.
2. **Paths are injected.** `RuntimePaths` is built in `crawl` or `app` and passed down; no
   domain reads `BASE_DIR`.
3. **Enforced by import-linter** in `make lint` and CI: one `layers` contract for the table and
   one `independence` contract for each multi-package layer. Its graph includes imports inside
   functions and under `TYPE_CHECKING`, so neither hides a violation. Once it runs,
   `tests/test_import_cycles.py` is deleted, because two checks of one rule drift apart.
4. **No exceptions without an ADR.** A violation is fixed by moving code to the right layer,
   or by injecting a protocol defined in the lower layer (as `SpaceOwner` in `nlp/space_updater.py:13`
   already does for the NLP service), never by a lazy import or an `ignore_imports` entry.

The UI follows the same rule: `app` imports `features`, features import `shared` and
other features' `index.ts`, and `shared` imports nothing from either. ADR 10 gives the lint
rules.

## Alternatives considered

- **Keep the cycle test only.** It forbids loops but not wrong-way edges, which is how
  `config` came to depend on `priority` and be depended on by everything else.
- **`config` at the bottom, with the strategy registry moved below it.** It breaks the
  two-way pull for strategies only. Every stage would still read the whole `RuntimeConfig`,
  and constructor defaults would keep shadowing the configured values.
- **A hand-written AST test instead of import-linter.** The current test shows this is
  possible, but layers, independence and clear failure messages are what import-linter already
  does, so a library is simpler than writing them again.

## Consequences

- Removing the `config` imports from stages, `llm` and `telemetry` is real work, and it is
  the same work as ADR 7's single-source settings. The two land together, one domain at a time.
- `benchmark` builds stages through `crawl`'s registry builders (ADR 7) because it sits above
  `crawl`.
- `offline` sits above `benchmark` because its fetcher replays a `FrozenGraph`
  (`offline -> benchmark` today).
- Adding import-linter is a new development dependency and a CI change.

## Standards affected

- Dependencies point one way, with no cycles and no lazy imports to dodge one.
- Other domains are used only through their `__init__.py`.
- No logic in two places.
- No magic numbers: named constants live in the module that owns them.
- `mypy --strict` and ruff stay clean.

## Migration and commit plan

1. `CI`: import-linter runs with today's packages and a contract that matches the current
   graph, so it passes.
2. Per domain, in the ADR 1 move series: the domain's contract line is added at its target
   layer, and the violations it reports are fixed in the same series (settings section,
   injected paths, constants moved).
3. `Config`: once no stage imports `config`, the full layers contract replaces the starting
   one.
4. `Tests`: `tests/test_import_cycles.py` is deleted in its own commit.
