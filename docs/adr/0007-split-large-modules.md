# ADR 7: Each setting has one definition in its domain, and the large backend modules split by responsibility

Status: proposed, 2026-10-29

## Context

- Backend modules over the 400-line module limit, `wc -l` on 2026-10-29:
  `config/runtime_config.py` 972, `ui_bridge/telemetry_bridge.py` 767, `benchmark/runner.py`
  736, `config/blueprint_translator.py` 546, `pipelines/debugging_pipeline.py` 528,
  `routes/benchmark.py` 504, `benchmark/audit.py` 471, `benchmark/analyze.py` 408.
  `core/crawler.py` and `services/nlp_service.py` were split by ADRs 2 and 3.
- One value, several definitions: `target_top_k` in four places
  (`config/runtime_config.py:662`, `services/nlp_service.py:81`, `services/link_features.py:79`,
  `nlp/feature_extractor.py:16`); `nlp_bias` and `llm_bias` in three
  (`config/runtime_config.py:608`, `pipelines/priority_pipeline.py:33-34`,
  `priority/strategy.py:118`); the embedding model name in five (`config/config.py:43`,
  `nlp/embedding_engine.py:49` and `:125`, `services/nlp_service.py:74`, and the docs);
  composite weights fall back to defaults through `or` (`services/link_features.py:282`).
- The benchmark runner builds its stages by hand and leaves values to constructor defaults:
  `NLPService` without the composite weights or `top_k` (`benchmark/runner.py:647-657`),
  `PriorityPipeline(storage, broker)` with its own 60/40 (`:504`), `get_strategy(...)` without
  the configured weights (`:727`), cascade constants imported from `config` (`:17-23`). The
  crawler and the benchmark measure the same method only while every default happens to agree
  (`config/runtime_config.py:970-972`).
- `RuntimeConfig` holds every section of every domain in one module, which is also why stages
  import `config` (ADR 4).

## Decision

1. **A setting is defined once**, as a field of its domain's section model in
   `crawlviz/<domain>/settings.py`. The field default is the only default. `crawlviz.config`
   composes `RuntimeConfig` from the sections and keeps the cross-section validators, the
   migration hook (ADR 5) and the UI schema hints.
2. **Constructors have no defaults for configured values.** A class that uses a setting takes
   it as a required keyword argument, or takes its section. A builder that forgets a value
   fails at construction instead of using a second default. Constants that are not settings
   live, named, in their owning module.
3. **The benchmark runner uses the crawler's stage builders** (`STAGES`, ADR 2) with its own
   order, its frozen-graph fetcher and its own LLM double. One set of builders means one method.
4. **Splits**, one responsibility per module:
   - `runtime_config.py`: sections move to their domains (1), and the aggregate stays under
     400 lines.
   - `telemetry_bridge.py`: one translator module per stage family. The bridge keeps the
     `_dispatch` table, which stays the source of its `event_types` (ADR 2), and the snapshot
     update.
   - `routes/benchmark.py`: logic moves into `crawlviz.benchmark` functions, and the router
     keeps only HTTP (ADR 12).
   - `benchmark/runner.py`: shrinks once (3) removes its hand-built stages; the arm policies
     move to an arm registry, the one list of arms.
   - `debugging_pipeline.py`: the per-event formatters become a table of small functions, so
     the sink keeps only file handling.
   - `blueprint_translator.py`, `benchmark/audit.py` and `benchmark/analyze.py` follow the
     same rule, each in its own change, with the split agreed before the code moves.
5. **A test guards the single source.** It builds the crawler's stages and the benchmark's
   stages from a `RuntimeConfig` in which every numeric setting differs from its default, and
   checks that each stage holds the configured value. A forgotten argument or a hidden default
   fails it.

## Alternatives considered

- **Keep one `RuntimeConfig` module and only remove the duplicates.** Fixes the duplicated
  values but keeps the 972-line module and the stage-to-config imports ADR 4 removes.
- **Each stage reads `RuntimeConfig` itself** (`from_config`). Rejected in ADR 2: it couples
  every stage to the whole config and the benchmark passes different values.
- **A dependency-injection container.** It would wire the same builders the registry already
  has, with more machinery and no gain.

## Consequences

- Moving defaults changes no value, so it is not a method change. The pins and method guards
  must pass unchanged, and each commit that touches a file that can change scores or visit
  order is reviewed as a possible method change.
- The benchmark switch to the crawler's builders is method code. It must leave the pins
  unchanged. If it does not, a default differed, and that difference is reported and reviewed
  as a method question before anything else changes.
- The non-default config test will fail first on the duplicated values listed above. Those
  are fixed one value per commit, and each fix turns a failing case of that test green.
- Frontend components over 250 lines (`GraphView.jsx` 1389, `BlueprintManager.jsx` 1161) are
  ADR 10's subject.

## Standards affected

- Size limits: a module at most 400 lines, split by responsibility.
- Dependencies point one way: stage domains do not import `config` (ADR 4).
- Each list has one source: the stage builders and the arm registry.
- No logic, and no value, in two places.
- No magic numbers: named constants live in the module that owns them.
- A bug fix starts with a test that fails before the fix.
- Behaviour pins pass unchanged.

## Migration and commit plan

Benchmark commits are reviewed as possible method changes.

1. `Tests`: the non-default config test, marked `xfail` with the list of values that fail
   today.
2. Per duplicated value, one commit each: one definition, the other copies become arguments,
   and the value leaves the `xfail` list.
3. Per domain: its section moves to `<domain>/settings.py`, and `RuntimeConfig` imports it
   (with the ADR 1 move of that domain).
4. `Benchmark runner`: stages come from the registry builders, and the pins stay unchanged.
5. `Telemetry`: translators move out of the bridge, one stage family per commit.
6. The remaining splits, one module per short series.
