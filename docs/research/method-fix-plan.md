# Method fixes held for sign-off: the intended changes

Author: research-scientist, 2026-10-30. Code read at `0d21314` (main). Evidence is in
`docs/research/phase-b-method-review.md` (branch `phase-b-discovery`); line numbers below
were re-read at `0d21314`.

This plan says, for each held method fix, what the code should do, where, what it does to
the behaviour pins, and what Omar approves before `uv run pytest -m pins --update-pins` is
run. Nothing here has been run: there is no measurement in this document, only reading.
There is no study protocol yet, so no fix needs an amendment; Phase G records the final
method.

## Rules for every fix below

- The builder writes the failing test first (TEST-1), then the fix, in one commit.
- Every commit runs `uv run pytest -m "pins or method_guard"`. Where this plan says "pins
  unchanged", a moved golden stops the work and comes back to me; it is not updated.
- Where goldens are expected to move, the fix lands in its own commit, test-engineer runs
  `--update-pins` in a separate commit, I review the golden diff against the expectation
  written here, and Omar approves with the sign-off line given for that fix.
- One fix per pin update, in the order at the end, so each golden diff shows one cause.
- Owners: `priority/`, `pipelines/`, `services/`, `nlp/`, `ui_bridge/` are backend-engineer
  (method files, my review); `models/prompts.py`, `services/llm_contracts.py`,
  `services/scoring_service.py`, the provider translators and `offline/scripted_llm.py` are
  llm-engineer; goldens are test-engineer; `benchmark/runner.py` is mine.

Sign-off line Omar gives, filled in per fix:

```
Approved: pin update for <fix>, golden files <list>, reason <one line from this plan>.
Reviewed by research-scientist at <commit>. Omar, <date>.
```

## (a) One 0-1 priority scale

Problem. `priority/strategy.py:99-103` sums raw feature weights that total 0.70
(aggressive, `:66-72`), 0.75 (balanced, `:73-80`) and 0.90 (exploration, `:81-88`). A
trusted link (NLP only, ranked with `(1, 0)`, `pipelines/priority_pipeline.py:155`) tops
out at the strategy's weight sum, while an LLM-scored link tops out at
`0.6 x sum + 0.4`. The depth penalty is inside the mix, so it is scaled by 0.6 for an
LLM-scored link and by 1.0 for a trusted one.

Intended scale. Before the depth penalty, every priority is in [0, 1]. A trusted link with
normalised NLP evidence `x` and an LLM-scored link with the same `x` and an LLM score of
`100 x` get the same priority. Two links at the same depth pay the same penalty.

Change, `priority/strategy.py:99-103`:

```python
def _score(strategy, node, link, nlp_bias, llm_bias, weights) -> float:
    w = weights if weights is not None else DEFAULT_WEIGHTS[strategy]
    feature_weights = {k: v for k, v in w.items() if k != DEPTH_PENALTY_KEY}
    evidence = sum(v * _nlp(link, k) for k, v in feature_weights.items())
    evidence /= sum(feature_weights.values())
    mixed = nlp_bias * evidence + llm_bias * _llm(link)
    penalised = mixed - _depth_penalty(node, w.get(DEPTH_PENALTY_KEY, 0.0))
    return round(min(1.0, max(0.0, penalised)), 6)
```

- `get_strategy` (same file) rejects user weights with a negative feature weight or a
  feature-weight sum of 0, with a message that names the strategy.
- `balanced` (`:118`) and `exploration` (`:129`) lose their default biases (0.5/0.5 and
  0.85/0.15). They are never used at run time: the pipeline always passes its normalised
  split (`pipelines/priority_pipeline.py:153`). The docstring claim at `:125` ("LLM score is
  a weak signal") goes. If Omar wants exploration to trust the LLM less, that becomes a
  per-strategy config value, decided as a method question, not restored silently.
- The composite NLP score (`_nlp_score`) keeps its one job, bucketing. Priority stays on
  the strategy's features. docs-writer records both in `docs/06-algorithms.md`.

Pins: goldens move. Both pins use balanced and mix trusted and LLM-scored links, so
`link_scores` (priority), `wire_messages` (priority fields) and very likely `fetch_order`
change. Check for the review, on balanced, with `N` the weighted feature sum, `L` the LLM
score on 0-1 and `d` the depth: a trusted link gets `N / 0.75 - 0.05 d` instead of
`N - 0.05 d`, and an LLM-scored link gets `0.6 N / 0.75 + 0.4 L - 0.05 d` instead of
`0.6 (N - 0.05 d) + 0.4 L`, both clamped to [0, 1]. Any golden that moves in another way
is a defect.

Sign-off: method change. Reason line: "priorities of trusted and LLM-scored links on one
0-1 scale, depth penalty outside the mix".

## (b) A missing LLM score stays missing

Problem. A link the LLM did not answer for gets `link.score = link.score or 0` and
`relevance_type = "irrelevant"` (`services/results_mapper.py:45-46`); a malformed entry gets
0 and `"ambiguous"` (`:77-78`). Since a score of 0 is a verdict
(`pipelines/priority_pipeline.py:152`), a skipped link is ranked as judged worthless.

Change.

1. `services/results_mapper.py:45` and `:77`: delete the score assignment, so a link never
   answered keeps `score = None`. `:46` stops writing `"irrelevant"`; the link keeps its
   default relevance type. The outcome counters (`:44`, `:76`) stay; they are the record.
   `priority_pipeline.py:152-155` then ranks the link on NLP alone, which is the existing
   rule for a link with no verdict.
2. Separate commit: `pipelines/priority_pipeline.py:160` records `getattr(link, "score",
   None)` instead of `... or 0`, and `ui_bridge/telemetry_bridge.py:348` passes the score
   through instead of `or None`, so a real verdict of 0 shows as 0 and no verdict as null.
   If `docs/crawl_messages.ts` does not allow null there, contracts-steward changes it first.

Pins: step 1 moves goldens only if `ScriptedLlm` omits or malforms an entry; not checked.
Step 2 moves `wire_messages` wherever the scripted LLM answers 0 (shown as 0 instead of
null) and `link_scores` records for trusted links (null instead of 0). Expected, and the
review checks that nothing else moves.

Sign-off: method change for step 1 if goldens move; step 2 is a record-format change.
Reason lines: "a link the LLM did not score is ranked on NLP alone, not as a 0 verdict";
"records keep a 0 verdict apart from no verdict".

## (c) No links lost when an LLM call raises; exploration budget rounding

Problem 1. All LLM batches of a page run in one `try` (`pipelines/scoring_pipeline.py:
220-225`). If one raises, control jumps to `:257-266`, `ScoringFailedEvent` is sent and
`LinksScoredEvent` never is. The high-confidence links already went out (`:195-203`), so
the page's LLM-bound links are lost, including batches that had already succeeded.
`RetryProcessor` reacts to `ScoringFailedEvent` with a node-level retry
(`pipelines/retry_processor.py:66`, `:91`), which can send the high-confidence links twice
(not checked).

Change 1, the floor: no LLM-bound link is ever lost; at worst it is ranked on NLP alone.

- Move the `try` inside the batch loop at `:222-225`. A batch that raises is logged with the
  node id, batch index and exception (CODE-5), counted as
  `scoring_service.outcomes["call_failed"]` (LLM-3), and its links are appended to
  `scored_links` unchanged, so their score stays `None` (fix (b) ranks them on NLP alone).
- `LinksScoredEvent` is then always sent with every sampled link.
- `ScoringFailedEvent` stays for failures outside the LLM call (NLP scoring, bucketing),
  where the node-level retry is right. A failed batch does not send it, so the retry cannot
  duplicate the high-confidence links.
- The empty-answer branch (`:226-232`) cannot fire with the real mapper (review, bug 2). It
  is left as it is; changing the retry count of malformed answers is a separate method
  change and not part of this fix.

Problem 2. The exploration and re-check budgets are floored: `int(len(low) *
low_score_sample_fraction)` and `int(len(high) * high_score_llm_fraction)`
(`:313-316`). A page with fewer low links than `1 / fraction` never samples one, so the
exploration rate depends on page size and small pages never explore.

Change 2: stochastic rounding, unbiased per page.

```python
def _rounded_budget(count: int, fraction: float, rng: random.Random) -> int:
    exact = count * fraction
    whole = math.floor(exact)
    return min(count, whole + (1 if rng.random() < exact - whole else 0))
```

The draws use their own stream, `StageInputs.rng("scoring_budget")` (`core/stages.py:75-78`),
passed in beside the existing `rng`, so the existing sample stream (`:322`) is not shifted
and the pin diff shows only the rounding. The same for `high_budget` and
`high_random_budget`.

Pins: change 1 leaves goldens unchanged if `ScriptedLlm` never raises (expected; the fix
must show it). Change 2 moves goldens: more low links are sampled on small pages, so
`link_scores`, `wire_messages` and `fetch_order` change.

Sign-off: change 1 needs my review and the method guards, pins unchanged. Change 2 is a
method change. Reason line: "exploration and re-check budgets rounded without bias, so small
pages sample at the configured rate".

## (d) One weight source; features on [0, 1]

Problem. The same value lives in several places and the benchmark reads part of its
settings from constructor defaults (review, bug 4): `target_top_k` in four places, the
biases in `config/runtime_config.py:608-624` and `pipelines/priority_pipeline.py:33-34`,
the composite fallback `self.settings.composite_weights or NLP_COMPOSITE_WEIGHTS`
(`services/link_features.py:282`), and `benchmark/runner.py:500`, `:504`, `:647-657`,
`:669`, `:690-695`, `:727`.

Change 1, single source (no value changes):

- `RuntimeConfig` is the only source of every method value. Constructors that hold method
  values (`PriorityPipeline`, `NLPService`, `LinkFeatures` settings, `FeatureExtractor`,
  `ScoringService`, `ProcessingPipeline`) take them without defaults; the module constants
  in `config/config.py` feed `RuntimeConfig` only.
- `services/link_features.py:282` uses `self.settings.composite_weights` with no `or`;
  `config/runtime_config.py` rejects an empty `composite_weights` with a message.
- `benchmark/runner.py` (mine) builds every stage from `cfg`, including `strategy_weights`,
  the composite weights, `target_top_k`, cluster settings, prompts, cascade values and
  `link_context_length`.

Change 2, normalised features. Strategy weights assume features on [0, 1]; two are not.
`semantic_delta` and `distance_to_nearest_cluster` are cosine distances in [0, 2]
(`nlp/feature_extractor.py:91`, `:119-120`), and `target_similarity` is a mean cosine
similarity in [-1, 1] (`:137`). Clip, do not rescale: distances to `min(1.0, d)`
(opposite and orthogonal both mean unrelated) and similarities to `max(0.0, s)`, as
`contextual_consistency` already does (`:106`). Clipping changes only values outside
[0, 1], so a weight fitted on today's features keeps its meaning.

Pins: change 1 leaves them unchanged (the values are equal today because
`default_runtime_config()` returns the code defaults). Change 2 leaves them unchanged on the
hashing path: `HashingEmbeddingEngine` counts tokens into non-negative vectors
(`nlp/embedding_engine.py:95-99`), so cosine similarity is in [0, 1] and distance in [0, 1].
It does change real crawls where a similarity is negative.

Sign-off: change 1 is a refactor, my review, pins unchanged. Change 2 is a method change for
real crawls with no pin update; Omar approves the clipping rule (no `--update-pins`). Any
refit of the weights is not part of Phase C: it is pre-registered in Phase G and fitted on
data kept apart from the evaluation graph and its judge.

## (e) The embedding dimension comes from the model

Problem. `SentenceTransformerEngine.dim` returns `self._dim`, which is the literal 384
(`nlp/embedding_engine.py:52`) until `encode` has loaded the model (`:54-63`). The space is
created from `engine.dim` before anything is encoded (`services/space_bootstrap.py:96`,
`services/nlp_service.py:138`), so any model that is not 384-d gets a 384-d space.

Change. `dim` (`:73-75`) calls `self._load()` and returns the model's
`get_sentence_embedding_dimension()`. `self._dim` starts as `None`; the 384 literal and the
docstring's "384d" go. `VectorSpace.__init__` (`nlp/vector_space.py:36`) loses its `dim=384`
default so no caller can get a space of the wrong size silently.

Pins: unchanged (they use `HashingEmbeddingEngine`, which sets its own dimension). Real
crawls with the default 384-d model are unchanged.

Sign-off: correctness fix, my review, no pin update. It is a precondition for the
multilingual embedder (review, bug 6), which stays held for Phase G.

## (f) Seed keys are stable across processes

Problem. `services/space_bootstrap.py:149` builds the key with `hash(description)`, which
Python salts per process, so a saved space differs between identical runs and cannot be
checksummed (REPRO-1).

Change.

```python
digest = hashlib.sha1(description.encode("utf-8"), usedforsecurity=False).hexdigest()
key = f"seed::{self.blueprint_id}::{digest}"
```

No scoring code reads the keys. Identical descriptions still share a key, as before.

Pins: unchanged. No golden can hold today's keys, because they change with every process.

Sign-off: my review, no pin update. Spaces saved before the change still load, because
spaces are found by blueprint and model (`nlp/space_store.py:29-33`), not by seed key.

## (g) A zero vector gives the neutral value, not NaN

Problem. Cosine against an all-zero vector is NaN. `semantic_delta` has no guard
(`nlp/feature_extractor.py:91`); `contextual_consistency` gives 0 only by the argument order
of `max(0.0, sim)` (`:106`); `novelty_injection_score` is NaN when the space holds a zero
row (`:175-178`); `region_density` (`:156`) and `distance_to_nearest_cluster` (`:119`) share
the risk. `max(0.0, nan)` then gives priority 0 to every affected link.

The value. A zero vector carries no information, so a feature compared against one takes
the value the code already uses for a missing input.

Change.

- One helper, `_has_direction(vec) -> bool` (`vec is not None and bool(np.any(vec))`), used
  in place of the `is None` checks at `:89`, `:103`, `:117`, `:129`, `:154` and `:171`.
- `semantic_delta` and `contextual_consistency` return 0.0 when either vector has no
  direction, as for `None` (`:89-90`, `:103-104`).
- `region_density`, `novelty_injection_score` and `distance_to_nearest_cluster` drop the
  zero rows (or centroids) before the cosine, and return the empty-space value (`:155`,
  `:172`, `:118`) when none are left. The row filter is one boolean mask on
  `space_matrix`, done once per call.
- Tests assert every feature is finite for a zero link vector, a zero parent vector and a
  space with a zero row.

Pins: goldens expected unchanged; the review's probe found NaN only in
`tests/pins/test_lockstep_passivity.py:69`, which compares visit lists between runs, not
goldens. The fix must confirm it by running the pins.

Sign-off: my review (this definition), no pin update. Refusing an empty topic in the
benchmark runner is done separately (benchmark area); the blueprint schema rule is a
contracts-steward change.

## (h) Prompt hardening

Problem. The system prompt is the first block of the user message
(`models/prompts.py:180-181`, `services/scoring_service.py:89-91`); the `ScoringContext`
carries one prompt string, so no provider receives a system role. Page data (URL, anchor,
context) goes into the prompt as JSON with no delimiter and no cap on the anchor
(`models/link.py:41-42`). Expansions from the LLM are taken in any number and length
(`services/llm_contracts.py:36-41`) and every one is embedded into the space
(`services/nlp_service.py:207-217`), so one page can steer the space.

Change, each its own commit:

1. System role. `ScoringContext` and `ExpansionContext` carry `system_prompt` and
   `user_prompt`; the translators send the first as the provider's system message. The
   prompt texts move to `prompts/<id>.md` with front matter (LLM-2). The output format
   block is unchanged (locked).
2. Delimited untrusted data. The candidates block becomes
   `<untrusted_page_data>` ... `</untrusted_page_data>`, and the system prompt says that
   text inside it is data from web pages and that instructions in it are never followed.
   `<` and `>` inside the JSON are written as `<` and `>`, so a page cannot
   close the tag.
3. Anchor cap. `Link.to_dict` for the prompt cuts the anchor to `ANCHOR_PROMPT_CHARS = 200`.
   The context is already cut by `link_context_length`; the builder checks it is.
4. Expansion caps, `services/llm_contracts.py:38-41`: at most
   `MAX_EXPANSIONS_PER_LINK = 4` per link, each cut to `MAX_EXPANSION_CHARS = 300`. The
   same character cap applies to the bootstrap seed descriptions (`ExpansionSeeds`).
5. Per-node cap. `NLPService.update_space` (`services/nlp_service.py:207`) accepts at most
   `max_expansions_per_node` expansions from one page (a `RuntimeConfig` field, default 20),
   taken from links in order of LLM score, then URL, so the cut is deterministic. Today one
   page can add `MAX_LLM_LINKS_PER_NODE x expansions` vectors (60 x any number).

The numbers 200, 4, 300 and 20 are proposals; Omar confirms them, and Phase G records them.

Pins: goldens move. The rendered prompts change, so any golden that holds prompt text or a
prompt hash moves, and `ScriptedLlm` must be updated to read the delimited block (llm-engineer,
before the pin update). Caps 4 to 5 move goldens only if the scripted answers exceed them.
The golden replay (LLM-2) runs for steps 1 to 3. Every `CachedLlm` entry is keyed on the
prompt (`benchmark/llm_cache.py:71`), so all cached benchmark answers miss afterwards. That
is acceptable now, because no experiment is running; after Phase G starts it would not be.

Sign-off: method change (prompt edits). Reason line: "untrusted page data delimited and
capped, system role sent as a system message, expansions capped per link and per page".

## Order

1. (f), (e), (g): no pin update.
2. (d) change 1 (refactor), then (d) change 2 (no pin update; Omar approves the rule).
3. (b) step 1, then step 2.
4. (c) change 1, then change 2.
5. (h) steps 1 to 5.
6. (a), last, so its golden diff shows only the new scale.

Held, not in Phase C: the multilingual embedder and any refit of the weights (Phase G,
pre-registered), and not saving a space whose expansion failed (review, PR #5 item 1),
which I sign off separately.

## Threats to validity this plan does not remove

- The composite weights were fitted on labels from an LLM of the same kind as the cascade's,
  on one English topic, before any pre-registration. Clipping keeps them meaningful; it does
  not make them valid for the French ISI graph.
- The strategy weights have no recorded source. Normalising them fixes the scale, not the
  choice.
- The pins cover the hashing embedder and the scripted LLM only, so fixes (d) change 2 and
  (e) are checked by unit tests, not by any behaviour pin.
