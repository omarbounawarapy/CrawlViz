# ADR 3: NLPService keeps its interface and hands bootstrap and link features to two helpers

Status: accepted, 2026-10-28

## Context

`services/nlp_service.py` is 577 lines, against the 400-line module limit (ARCH-3). Three
functions are over the 50-line limit: `build_space` (about 73 lines,
`services/nlp_service.py:168`), `score_links` (about 62, `:325`) and `generate_vector`
(about 62, `:393`).

The class does three jobs that change for different reasons:

1. **Bootstrap.** On a blueprint's first run it asks the LLM for descriptions of the target
   topic ("expansions"), embeds them as seed vectors, and records outcomes and trace events
   (`build_space`, `create_expansions`). This is the part the LLM layer work (LLM-1, LLM-2)
   will change: it moves to `LlmClient` and to a prompt file.
2. **Link features.** For every link it embeds anchor, context and a tagged link text, asks
   `FeatureExtractor` for the feature vector, keeps per-space statistics (boilerplate
   prototypes, vocabulary, density radius, cluster centroids), and combines the features
   into the composite NLP score. This is the scoring hot path the research method depends on.
3. **Space ownership.** Start, load, save, buffered growth (`update_space`, `flush_buffer`)
   and the accessors `SpaceUpdater` uses through the `SpaceOwner` protocol
   (`nlp/space_updater.py:13`).

Callers depend only on the third job's surface plus `score_links`:
`ScoringPipeline` (`score_links`, `update_space`), `SpaceUpdater` (`space`, `save_space`,
`space_size`), the benchmark runner and `tools/nlp_eval.py` (constructor, `start`,
`score_links`), and the `RelevanceScorer` contract (`pipelines/contracts.py:12`). The behaviour
pins run the real `NLPService` (`tests/pins/pin_crawl.py:4`), so any change to its numbers
shows up there.

## Decision

`NLPService` stays the one object callers use, with the same constructor and methods. Two
jobs move out:

- `services/space_bootstrap.py`: `SpaceBootstrapper` builds the first space for a blueprint.
  It owns the expansion prompt builder, the LLM request and its parsing, the expansion
  outcome counts and the bootstrap trace events. It hands the finished space to
  `NLPService` through a callback at the point where the space used to be saved, so the
  trace events keep their order and `duration_ms` keeps covering the save.
- `services/link_features.py`: `LinkFeatureScorer` turns one link into its feature vector and
  composite score. It owns the `FeatureExtractor`, the per-space statistics cache, the
  cluster centroids, the composite weights and the per-link trace events. The values that are
  the same for every link of one parent page travel in a `ParentContext`.

`NLPService.score_links` keeps the loop and the per-link error handling, so a link that fails
still gets an empty vector and a score of 0.0 and the rest of the page is scored.

The moved code is moved, not rewritten: the same encode calls in the same order, the same
feature arguments, the same arithmetic. Function splits only separate trace emission and the
seed loop from the logic around them.

## Alternatives considered

- **Split by state: a space object and a scorer object that callers hold separately.**
  Cleaner on paper, but it changes `ScoringPipeline`, `SpaceUpdater`, the benchmark runner,
  `tools/nlp_eval.py` and the contracts at once, which is a bulk change across four areas.
  `NLPService` can still be removed later, one caller at a time.
- **Move the code into `nlp/`.** `nlp/` must not import `services/` or the LLM handler, and
  the bootstrap needs both (`services/llm_contracts.py`, `infrastructure`). The link features
  could live there, but they emit trace events that `nlp/` does not use today. When the
  backend moves to `src/crawlviz/<domain>/`, both helpers move with the NLP domain.
- **Only shorten the long functions.** Leaves the module over 400 lines and keeps the
  bootstrap and the hot path in one file, where the LLM layer work would touch method code.

## Consequences

- Each module is under 400 lines and each function under 50.
- `NLPService.expansion_outcomes`, `create_expansions` and `prompt_builder` move to
  `NLPService.bootstrapper`. Only `tests/test_results_mapper.py` used them; it now tests
  `SpaceBootstrapper` directly instead of building a half-initialised `NLPService`.
- The per-space statistics move from private `NLPService` attributes to
  `LinkFeatureScorer`; nothing outside the class read them.
- Both new modules are method files and are checked by `mypy --strict`.
- The pins must pass unchanged; a difference in any golden means the move changed the
  method and the commit is wrong.

## Standards affected

ARCH-3, ARCH-5 (`nlp/` still does not import `services/`), PY-1, TEST-2, LLM-1 (the bootstrap
is now one module to move onto `LlmClient`).

## Migration and commit plan

1. `NLP service`: building the first space moves to `SpaceBootstrapper`.
2. `NLP service`: link features and the composite score move to `LinkFeatureScorer`.
3. `NLP service`: the bootstrap's trace ids come from one helper, so `build` fits the limit.
4. `Agents`: both new modules are method files.
5. `NLP service`: a parent page with no words gets relevance 0 by an explicit check, not by
   `max(0.0, nan)` happening to return 0. Same value, no NaN warning.

Each commit runs the pins and the method guards (`make check-changed` adds them for method
files) and needs research-scientist review.
