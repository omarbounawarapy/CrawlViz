# Method review before the correctness fixes

Reviewer: research-scientist. Code reviewed at `0d21314` (main, 2026-10-29). The method
files are unchanged between that commit and the tip of `phase-b-discovery`.

Paths and line numbers were updated on 2026-11-05 to the tree at `ab20ea0`
(`phase-d-architecture` at `afbe710` plus a docstring fix in `benchmark/`), after the stage renames (for example `PriorityPipeline` became
`PrioritizeStage` in `pipelines/prioritize_stage.py`) and the moves of `nlp/`, `priority/`
and `models/link.py` into `src/crawlviz/`. The findings and verdicts are the ones made at
`0d21314`. A finding fixed since then is kept as it was found, in the past tense, with its
citation at `0d21314` and the commit that fixed it. Fixed since this review: the judge
`bool` (bug 5, `cb371f5`), the node detail's LLM score of 0 (bug 3, `235a4ff`), an empty
topic in a blueprint (bug 7, `be02dd6`) and, when asked, in the benchmark runner (bug 7,
`83971ef`), the missing `Crawler` pin (`2626576`) and the runner's module docstring
(`ab20ea0`).

This review answers three questions for each known bug: does fixing it change the
method (scores, ordering or prompts), does the fix change the behaviour pins, and what
sign-off it needs when it is fixed. It also holds the review of the stage registry and the
NLP service split (merged PRs #4 and #5) that was deferred on 2026-10-29.

## Sources and limits

- The audit plans in `~/.claude/plans/` could not be read: the session's permission setting
  blocks reads outside the repository, and I did not work around it. The bug list comes
  from the task brief, `.left-undone.json` and the code. A detail the plans add is not
  covered here.
- "Verified" means I ran it. "Read" means I read the code and did not run it.
- The October pilot is archived and not used. There is no study protocol yet, so no fix
  below needs an amendment. Each method change still needs research-scientist sign-off, a
  pin update reviewed by me and made by test-engineer (`--update-pins`), and Omar's
  approval. Phase G records the final method in the protocol.
- Scripts used for the checks were kept outside the repository; the commands and their
  output are quoted below where they matter.

## Summary

| Bug | Changes the method | Pins change | Phase C sign-off |
|---|---|---|---|
| Priority scale | Yes, ordering | Yes, expected | Method change: research-scientist design, test-engineer pin update, Omar |
| Dropped links | Yes, only when an LLM call raises | Probably not (not checked) | research-scientist review, method guards |
| Missing score treated as 0 | Yes, ordering | Only if the scripted LLM omits a link (not checked) | Method change: research-scientist, test-engineer, Omar |
| Weight sources | Single source: no. Refit: yes | Single source: no. Refit: yes | Refactor: review, pins unchanged. Refit: Omar, pre-registered in Phase G |
| Judge `bool` | Not the crawler; it changes ground-truth labels | No | research-scientist (benchmark area), before any labelling |
| Multilingual embedder | Yes, every NLP score of a real crawl | No (pins use hashing embeddings) | Method change: Omar; model choice measured and pre-registered in Phase G |
| NaN on a zero vector | Yes, ordering in the cases below | No golden has a NaN; expected unchanged | research-scientist defines the value; backend-engineer fixes `src/crawlviz/nlp/` |

## The bugs

### 1. Priority scale

Status: partly fixed on 2026-10-01 (`1eaec10`). Read.

- Fixed: the biases are normalised to sum to 1 (`pipelines/prioritize_stage.py:46-50`)
  and a link without an LLM score is ranked with `(1, 0)` (`:154`).
- Still open: the strategy weights do not sum to 1. The positive weights sum to 0.70
  (aggressive), 0.75 (balanced) and 0.90 (exploration)
  (`src/crawlviz/priority/strategy.py:65-89`). Under the default 60/40 split, a balanced
  link ranked on NLP alone tops out at 0.75 while an LLM-scored link tops out at
  0.6 x 0.75 + 0.4 = 0.85. The two kinds of link are still not on one scale, and the gap
  depends on the strategy.
- Still open: the exploration strategy's own split, 0.85 NLP and 0.15 LLM
  (`src/crawlviz/priority/strategy.py:129`), is never used. The stage always passes its
  normalised 60/40 (`pipelines/prioritize_stage.py:152`), so the docstring's "LLM score is
  a weak signal" is not true at run time.
- The composite NLP score (`_nlp_score`) does not enter the priority at all; the
  strategies weight the raw features. Bucketing uses one score and ranking another. This
  is a design question, not a bug, but the fix for the scale should say which is meant.

Method: yes, any fix changes priorities and so the fetch order.
Pins: both pins use the balanced strategy and mix trusted and LLM-scored links, so
`link_scores`, `wire_messages` and very likely `fetch_order` change.
Sign-off: method change. I write down the intended scale first (what a trusted link and an
LLM-scored link with the same evidence should get), then test-engineer updates the pins
and Omar approves.

### 2. Dropped links

Status: the original bug is fixed; two routes remain. Read, not run.

- Fixed: `PriorityPipeline` (now `PrioritizeStage`) was never subscribed to
  `HighScoreLinksEvent`, so every high-confidence link was dropped. It is subscribed now,
  and the consumers name their own events (ADR 2, `tests/test_event_wiring.py`).
- Open: when a scoring call raises, the handler emits `ScoringFailedEvent`
  (`pipelines/score_stage.py:257-266`) and `LinksScoredEvent` is never sent. The
  high-confidence links were already sent (`:196`), so only the LLM-bound links of that
  page are lost: the mid bucket and the samples. With `llm_batch_size` set, the batches that
  had already succeeded are lost too (`:222-225`). Whether the retry stage brings them
  back, and whether a retry sends the high-confidence links a second time, I did not check.
- Open: `EmptyScoreResultsEvent` cannot fire with the real scoring service.
  `ResultMapper.map_results` always returns the list it was given
  (`services/results_mapper.py:36-38`, `:51`), so `scored_links` is never empty when links
  were sent (`score_stage.py:226`). A malformed answer leaves the scores at `None`, and
  those links are ranked as NLP-only. The empty-answer retry never runs in a real crawl.

Method: yes, but only when an LLM call raises or answers nothing usable.
Pins: probably unchanged, if the scripted LLM never raises; not checked.
Sign-off: research-scientist review and the method guards (`pytest -m "pins or method_guard"`).
A fix that adds retries of malformed answers changes the LLM call count, so it is a method
change and needs Omar.

### 3. Missing score treated as 0

Status: confirmed. Read.

- A link the LLM did not answer for gets `link.score = link.score or 0` and
  `relevance_type = "irrelevant"` (`services/results_mapper.py:43-47`). A malformed entry
  gets the same 0 (`:76-79`).
- Since `1eaec10`, a score of 0 is a verdict (`pipelines/prioritize_stage.py:151`). So a link
  the LLM skipped is ranked as if the LLM had judged it worthless: 0.6 x NLP instead of
  1.0 x NLP. Two correct-looking fixes combine into a wrong one.
- The wire did the opposite: `entry.get("score") or None` (`ui_bridge/telemetry_bridge.py:348`
  at `0d21314`) showed a real verdict of 0 as "no LLM score". Fixed in `235a4ff`: the node
  detail takes the link's own score (`ui_bridge/telemetry_bridge.py:358`).

Method: yes, it changes the priority of every link the LLM skipped or answered badly.
Pins: change only if the scripted LLM omits or malforms an entry; not checked.
Sign-off: method change. The fix keeps `score = None` for missing and malformed entries
(they are already counted in `outcomes`), with a failing test first. Test-engineer updates
the pins if they move; Omar approves.

### 4. Weight sources

Status: confirmed. Read.

Where the weights come from:

- Composite NLP weights (`config/config.py:114-118`: target 0.80, context 0.05, boilerplate
  -0.35) were fitted with `tools/nlp_eval.py`: 302 links from five English wikiMD pages on
  one topic (diabetes), labelled by an LLM (`groq`, `openai/gpt-oss-120b`, relevant when the
  score is at least 60; 154 of 302 relevant), with a logistic regression on standardised
  features (`tools/nlp_eval.py:180-187`). The constants are applied to raw features, so they
  are not the printed coefficients, and the step from one to the other is not recorded.
- Priority strategy weights (`src/crawlviz/priority/strategy.py:65-89`) have no recorded
  source.

Threats to validity, for the Phase G write-up:

- The labels came from an LLM that scores links the way the cascade's LLM does, so the NLP
  stage was tuned to agree with the LLM it is meant to pre-filter.
- The tuning predates any pre-registration and used one English topic. The ISI benchmark
  graph is French.

One value, several places:

- `target_top_k`: `config/runtime_config.py:718`, `services/nlp_service.py:86`,
  `services/link_features.py:77`, `src/crawlviz/nlp/feature_extractor.py:16`. `cluster_eps` and
  `cluster_min_samples` the same way.
- `nlp_bias` and `llm_bias`: `config/runtime_config.py:665`, `:675` and
  `pipelines/prioritize_stage.py:32-33`.
- `composite_score` falls back with `or` (`services/link_features.py:280`), so an empty weight
  dict silently means the defaults.

The benchmark runner takes part of its settings from the config and the rest from
constructor defaults:

- `NLPService` is built without the composite weights, `top_k` or cluster settings
  (`benchmark/runner.py:678-688`).
- `PrioritizeStage(storage, broker)` uses its own 60/40 defaults (`:528`).
- `get_strategy(...)` is called without the configured weights (`:758`).
- `ScoringService` is built without the configured prompts (`:700`).
- The cascade constants are imported from `config` (`:21-27`, used at `:711-714` and
  `:725-726`) instead of read from `cfg.scoring_cascade`.
- `ExtractStage` (at `0d21314`, `ProcessingPipeline`) is built without
  `link_context_length` (`:524`).

The values are equal today only because `default_runtime_config()` returns the code defaults
(`config/runtime_config.py:1026-1028`). If a default changes in one place, the crawler and the
benchmark measure different methods, and no test notices.

Method: making each value come from one place changes no value, so it is not a method change.
Refitting the weights is a method change.
Pins: a single-source refactor must leave them unchanged. A refit changes them.
Sign-off: the refactor needs research-scientist review with the pins and method guards
passing unchanged. A refit needs Omar, must be pre-registered in Phase G, and must be fitted
on data kept apart from the evaluation graph and its judge.

### 5. Judge `bool`

Status: confirmed by running it.

- At `0d21314`, `is_valid_label` used `isinstance(value, int)` (`benchmark/judge.py:44-45`),
  and `bool` is a subclass of `int`. An answer of `{"labels": {"1": true, "2": false}}` was
  accepted and written to the label log as `true` and `false`. A binary "yes" became grade
  1, never 2.
  Output: `0/1/2 judge on {true, false}: {'a': True, 'b': False}`.
- The legacy binary judge coerced with `bool(...)` (`benchmark/label.py:82` at `0d21314`),
  so the string `"false"` was relevant.
  Output: `legacy binary judge on {"false", "no"}: {'a': True, 'b': True}`.
- No stored data is affected: all 1,462 labels in `benchmark/data/isi.json` are integers
  (1417 zeros, 44 ones, 1 two). `benchmark/data/ball.json` is unlabelled.

Method: it does not touch the crawler's scores, ordering or prompts. It changes the ground
truth that every result is measured against.
Pins: no; the pins do not use the judge.
Sign-off: research-scientist (benchmark area), before any Phase G labelling. The test goes in
`tests/test_benchmark_judge.py`, because `tests/test_judge.py` is in backend-engineer's area.
The legacy `label.py` judge should be removed or made to reject anything but `true` and
`false`. Its constants are imported by `judge.py` and `label_graph.py`, so they move first.

Fixed in `cb371f5`, with its tests in `tests/test_benchmark_judge.py`: `as_grade` accepts
only an exact `int` of 0, 1 or 2 (`benchmark/judge.py:44-52`), and the legacy judge's
`as_binary_label` accepts only a JSON boolean (`benchmark/label.py:71-76`).

### 6. Multilingual embedder

Status: confirmed by reading the data. Not measured.

- The default model is `all-MiniLM-L6-v2` (`config/config.py:61`), an English model.
- The ISI graph is French Wikipedia (for example "Association à but non lucratif", "École
  centrale (Révolution française)"), its topic mixes French and English ("institut superieur
  informatique ISI (tunisia / ariana)"), and the `isi.json` template seeds `fr.wikipedia.org`.
- The model name is written in five places: `config/config.py:61`,
  `src/crawlviz/nlp/embedding_engine.py:49` and `:125`, `services/nlp_service.py:79`, and
  the docs.
- No model revision is pinned (`src/crawlviz/nlp/embedding_engine.py:61`), and the run
  manifest records only the name (`RunManifestWriter.build`, `core/run_manifest.py:31`; at
  `0d21314`, `core/crawler.py:315`). That falls short of REPRO-1.

Method: yes. A new model changes every NLP score of a real crawl. It also invalidates the
fitted composite weights and the threshold and percentile calibration
(`config/config.py:97-105`). Stored spaces are keyed by model name
(`src/crawlviz/nlp/space_store.py:30-34`), so old spaces are not reused, which is correct.
Pins: no; they use `HashingEmbeddingEngine`.
Sign-off: method change for Omar. I choose the model by measuring candidates on labelled
data kept apart from the evaluation graph and pre-register the choice and revision in Phase G.
Platform-engineer updates `make model`. I did not compare models here: that needs the
download and a measurement run.

### 7. NaN on an all-zero vector

Status: confirmed by running it. The tracker entry is partly wrong.

The tracker says `novelty_injection` is NaN when the parent vector is all zeros. A probe
run over the pins and a direct reproduction show two separate cases:

- **All-zero parent vector** (hashing engine, page text with no word characters):
  `semantic_delta` is NaN (`src/crawlviz/nlp/feature_extractor.py:91`, no guard).
  `contextual_consistency` comes out as 0 only because of the argument order in
  `max(0.0, sim)` (`:105-106`). The exploration strategy weights `semantic_delta`
  (`src/crawlviz/priority/strategy.py:86`), so `max(0.0, nan)` gives priority 0.0 to every
  link of that page, with or without an LLM score (`src/crawlviz/priority/strategy.py:103`).
  Balanced and aggressive are not affected.
- **All-zero vector in the space** (an empty topic, or an expansion with no word characters):
  `novelty_injection` is NaN (`src/crawlviz/nlp/feature_extractor.py:175-178`). All three
  strategies weight it, so every link scored against that space gets priority 0.0, and the
  frontier falls back to insertion order.
- This second case is what the pins hit: 8 links, all in
  `test_extra_components_hear_the_run_they_are_given_to`
  (`tests/pins/test_lockstep_passivity.py:71`), whose synthetic graph has no topic
  (`benchmark/graph.py:80` defaults it to `""`). The zero entry was `__target__benchmark`. No
  parent vector was all zero in any pin.
- If a NaN feature had a composite weight, `max(0.0, min(1.0, nan))` would give 1.0
  (`services/link_features.py:284`). The default composite weights avoid it.
- The NaN reaches the wire in `nlp_breakdown` (`ui_bridge/telemetry_bridge.py:355`), and
  `json.dumps` writes `NaN`, which a browser's `JSON.parse` rejects.
- An empty `target_topic` passed the blueprint schema (`config/blueprint_schema.py:208` at
  `0d21314`). Fixed in `be02dd6`: `_require_word_in_target_topic`
  (`config/blueprint_schema.py:241-249`) rejects a topic with no word character.

Reproduction output (hashing engine):

```
== parent with no words: parent vector all zero = True
   NaN features: ['semantic_delta']
   exploration priority: NLP-only=0.0  with LLM score 80=0.0
== empty topic: NaN features: ['novelty_injection']
   aggressive  priority: NLP-only=0.0  with LLM 80=0.0
   balanced    priority: NLP-only=0.0  with LLM 80=0.0
   exploration priority: NLP-only=0.0  with LLM 80=0.0
```

Pins probe: `NAN PROBE: {'links': 1383, 'nan:novelty_injection': 8}`, with
`78 passed, 587 deselected in 133.92s`.

With the sentence-transformers model a zero vector should not occur, because the model
normalises its output. I did not run the real model to confirm it. Offline mode and the pins
are affected either way.

The value to use: a zero vector carries no information, so a feature compared against one
should take the neutral value the code already uses for a missing input. That means
`semantic_delta` and `contextual_consistency` behave as when `parent_vec` is `None`
(`:89-90`, `:103-104`). Novelty, density and cluster distance are computed over the non-zero
rows of the space, with the empty-space value when none are left (`:171-172`). Separately,
the blueprint schema and the benchmark runner should refuse an empty topic. The schema does
since `be02dd6`. The runner does since `83971ef` when `run_cascade` is called with
`allow_empty_topic=False` (`require_topic`, `benchmark/runner.py:398`); its default is still
`True`.

Method: yes, but only in the cases above; ordinary crawls with the real model are unchanged.
Pins: no golden contains a NaN, the probe found no zero parent vector, and the NaN case is
in a test that compares visit lists, not goldens. The goldens are expected unchanged; the
fix must confirm it by running the pins.
Sign-off: research-scientist (this definition). Backend-engineer fixes `src/crawlviz/nlp/`,
which is a method file I review. Contracts-steward adds the topic length rule to the schema
(landed in `be02dd6`, see above).

## Deferred review: PRs #4 and #5

### `core/stages.py` (PR #4)

- Every builder passes the same arguments as the `_build_pipelines` it replaced: I compared
  each against `core/crawler.py:403-530` at `ccd6c22^1`. The one difference,
  `inputs.fetcher or NetworkClient(...)` (`core/stages.py:136-142`), came later with the
  offline mode and does not touch the method.
- For the method's events (`NodeAddedEvent`, `PageFetchedEvent`, `LinksScoredEvent`,
  `HighScoreLinksEvent`, `PriorityCalculatedEvent`), the order in which consumers receive
  them is unchanged. The only reorderings are the ones ADR 2 lists (retry after debug, space
  updater after the stages). Read, not run.
- Threat: the pins ran the benchmark runner, not `Crawler`, so `core/stages.py` and
  `core/crawler.py` were covered by the wiring tests only, not by any behaviour pin. A wrong
  argument in a builder (a swapped threshold, say) would pass every pin. An offline `Crawler`
  pin (scripted LLM, frozen site) would close this. Closed by `2626576`: the offline
  `Crawler` run is pinned (`tests/pins/test_crawler_pin.py`, goldens in
  `tests/pins/golden/crawler/`).
- The run manifest (`RunManifestWriter.build`, `core/run_manifest.py:26-37`; at `0d21314`,
  `core/crawler.py:310-321`) has the config, model name, git SHA and seed, but no prompt
  hashes, model revision or library versions (REPRO-1, a later phase).

### Benchmark runner (PR #4, `cfc33bc`)

- The subscription sets are unchanged. I built each of the eight stages and compared its
  `event_types` with the list the commit removed: all equal as sets. `StoragePipeline` and
  `RetryProcessor` (now `StorageSink` and `RetryStage`) list them in a different order. That
  does not change delivery, because the registry keys by event type and the order of the
  `subscribe` calls is unchanged (`benchmark/runner.py:537-542`).
- Extra components are still subscribed from `handlers` (`:540`), not `event_types`. This is
  harmless, but it is the one consumer left on the old pattern.
- The module docstring (`:3-6` at `0d21314`) said the LLM stage is a no-op. That was true
  for `run_policy` only, not for `run_cascade`. Fixed in `ab20ea0`: the docstring says which
  of the two runs makes LLM calls, and names `core.stages.build_stages` in place of the
  removed `Crawler._build_pipelines`.
- See bug 4 for the settings the runner takes from defaults instead of the config.
- A graph with no topic runs without complaint and, with hashing embeddings, gives every link
  priority 0 (bug 7). The runner should refuse it. Since `83971ef` it does when
  `run_cascade` gets `allow_empty_topic=False`; the default is still `True`.

### `services/link_features.py` (PR #5)

- The pins pass unchanged at `0d21314` (78 passed), which supports ADR 3's claim that the
  code was moved, not rewritten, on the hashing path.
- `_floored_similarity` guards zero vectors for the parent's relevance only (`:65-70`). The
  other cosine calls in `src/crawlviz/nlp/feature_extractor.py` are unguarded (bug 7).
- The composite fallback uses `or` (`:280`, bug 4).
- The tagged link text is built from `link.anchor` and `link.context` directly
  (`:215`). If either is ever `None`, the word "None" is embedded. I did not check whether
  `None` reaches here.
- Not a method issue: `region_density` and `novelty_injection_score` loop over the whole
  space in Python for every link (`src/crawlviz/nlp/feature_extractor.py:156`, `:175`).
  That is links times space size per page (PERF-3), and it should be vectorised in a change
  that keeps the values within the pin tolerance.

### `services/space_bootstrap.py` (PR #5)

Reviewed on 2026-10-29, after the rest of this document. Verdict: the method is unchanged.
One behaviour changed, and it does not reach scores or ordering. I compared the module with
`build_space` and `create_expansions` as they were in `services/nlp_service.py:168-275` at
`47f991d^`, and read the two later commits that touch it (`a54dfce`, `434ba4f`). Line
numbers below are `services/space_bootstrap.py` unless a file is named. Since the review,
`9f12ff2` moved the `EXP_SeedsGenerated` emit into `_emit_seeds_generated` (`:123-133`) with
the same arguments, so the lines after it moved.

- The prompt and the LLM call are the same. The same `ExpansionPromptBuilder` builds the
  prompt from the same arguments (`:69`, `:177`). It goes out in an `ExpansionContext` with
  `llm_type` and `llm_model` read from the same keys when the service is constructed
  (`:67-68`, `:191-195`). The prompt text, and with it the `CachedLlm` key (type, model,
  prompt; `benchmark/llm_cache.py:86`), are unchanged, so cached expansion answers still hit.
- The space is built the same way. The topic is embedded first (`:97`). The seeds are
  embedded in the order the LLM gave them (`:149-153`), with the same keys and metadata,
  added in one `add_batch` (one version bump, `src/crawlviz/nlp/vector_space.py:59`), and
  the target vector goes in last (`:104-109`). A seed that fails to embed is still logged
  and reported as pruned, and the others are kept (`:154-167`).
- Failures are handled the same way. A failed request or a malformed answer gives no
  descriptions and is counted (`:197-208`). The counter moved from
  `NLPService.expansion_outcomes` to `NLPService.bootstrapper.outcomes`. Only tests read
  either one, then and now (`git grep` at `47f991d^` and at the branch tip).
- `a54dfce` moves the trace fallback into `_bootstrap_trace` (`:135-141`). It returns the
  same pair the inline code built.
- `434ba4f` is formatting only: `ast.dump` of `services/space_bootstrap.py` and of
  `services/nlp_service.py` is identical before and after it. Verified.
- What changed: the old code set `self.space` (empty) and `self.target_vec` before it
  awaited the LLM (`services/nlp_service.py:190-194` at `47f991d^`). Now both stay local
  until the target vector is in, and reach the service through `adopt` (`:96-97`, `:110`,
  `services/nlp_service.py:143-145`). The space is still saved before
  `EXP_SpaceBootstrapped` is emitted. Nothing reads the space during the bootstrap: both
  callers await `start()` before any stage runs (`core/crawler.py:281`,
  `benchmark/runner.py:689`). If the bootstrap raises, `NLPService.space` is now `None`
  instead of a half-built space, and `start()` fails in both versions. Read, not run.
- Coverage: the pins only cover the scripted LLM answering well. `tests/test_space_bootstrap.py`
  checks that the seeds and the target are in the space and adopted before the bootstrap is
  reported. The bootstrap tests in `tests/test_results_mapper.py` cover the failure outcomes.
  I ran both files: 35 passed.

Problems that were there before PR #5 and that the move kept as they were:

1. A failed expansion becomes the blueprint's space for good. A request error or a
   malformed answer gives a space that holds only the target vector (`:197-207`).
   `save_space` writes it on the first run whatever `persist_space` says
   (`services/nlp_service.py:163-166`), and every later run loads it (`:121-122`). One
   transient LLM failure on a blueprint's first crawl changes the NLP features of every
   later crawl of it. Only a log line records it, and the counter that sees it is never
   reported (LLM-3). The benchmark does not keep the space (each run gets a new temporary
   store, `benchmark/__main__.py:134`), but a failed expansion there still gives that run a
   target-only space without notice. Recommended fix for Phase C: do not save a space whose
   expansion failed, and put the expansion outcome in the run manifest. This changes the
   space only after a failure, so it is a method change in that case and needs my sign-off.
   The pins should not change, because the scripted LLM answers.
2. Seed keys use `hash(description)` (`:152`). Python salts string hashes per process, so
   the same seeds get different keys in every run, and a saved space is not byte-identical
   between runs of the same blueprint. No scoring code reads the keys (`git grep`), so
   scores do not change. It does stop a saved space from being checksummed (REPRO-1). Use a
   content hash of the text. Whether any pin compares keys: not checked.
3. `create_expansions` takes its trace from `get_trace()` (`:175`), not from
   `_bootstrap_trace()`. Outside a trace, `EXP_PromptBuilt` therefore carries an empty trace
   id, while the other bootstrap events carry the new one. This affects observability only
   (OBS-1).
4. The expansion prompt's hash is not in the run manifest. This is the same gap noted above
   for the run manifest (`core/run_manifest.py:26-37`), and it applies to this second prompt
   as well (LLM-2, REPRO-1).

Sign-off: the move needs none, since the method and the pins are unchanged. Items 1 and 2
are Phase C fixes for the backend-engineer, with my review because this is a method file.

## Order of work for Phase C

1. Judge `bool` (bug 5): no pin impact, and it must land before any labelling.
2. NaN on a zero vector (bug 7) and refusing an empty topic: goldens expected unchanged.
3. Weight sources as a single-source refactor (bug 4): pins unchanged.
4. Missing score (bug 3) and dropped links (bug 2): small, separately pinned changes.
5. Priority scale (bug 1): the largest change to the ordering, after the others, so its pin
   diff shows only its own effect.
6. Embedder (bug 6) and any refit of the weights: decided with Omar and pre-registered in
   Phase G, not changed during Phase C.
