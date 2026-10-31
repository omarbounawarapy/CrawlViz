# Method review before the correctness fixes

Code reviewed at `0d21314` (main, 2026-10-29).

For each known bug, this review answers three questions: does fixing it change the
method (scores, ordering or prompts), does the fix change the behaviour pins, and what
sign-off it needs when it is fixed. It also reviews the stage registry and the NLP service
split (merged PRs #4 and #5).

## Sources and limits

- The review covers the known bugs below and PRs #4 and #5. It is not a full audit of the
  method.
- "Verified" means the check was run. "Read" means the code was read and not run.
- The October pilot run is archived outside the repository and not used. There is no study
  protocol yet, so no fix below needs a protocol amendment. Each method change still needs
  a method review, a reviewed pin update (`uv run pytest -m pins --update-pins`), and the
  maintainer's approval. The study protocol, once written, records the final method.
- Scripts used for the checks were kept outside the repository; the commands and their
  output are quoted below where they matter.

## Summary

| Bug | Changes the method | Pins change | Sign-off for the fix |
|---|---|---|---|
| Priority scale | Yes, ordering | Yes, expected | Method change: intended scale written first, reviewed pin update, maintainer approval |
| Dropped links | Yes, only when an LLM call raises | Probably not (not checked) | Method review, method guards |
| Missing score treated as 0 | Yes, ordering | Only if the scripted LLM omits a link (not checked) | Method change: reviewed pin update, maintainer approval |
| Weight sources | Single source: no. Refit: yes | Single source: no. Refit: yes | Refactor: review, pins unchanged. Refit: maintainer approval, pre-registered in the study protocol |
| Judge `bool` | Not the crawler; it changes ground-truth labels | No | Method review of the benchmark code, before any labelling |
| Multilingual embedder | Yes, every NLP score of a real crawl | No (pins use hashing embeddings) | Method change: maintainer approval; model choice measured and pre-registered in the study protocol |
| NaN on a zero vector | Yes, ordering in the cases below | No golden has a NaN; expected unchanged | Method review defines the value; the fix goes in `nlp/` |

## The bugs

### 1. Priority scale

Status: partly fixed on 2026-10-01 (`1eaec10`). Read.

- Fixed: the biases are normalised to sum to 1 (`pipelines/priority_pipeline.py:47-51`)
  and a link without an LLM score is ranked with `(1, 0)` (`:155`).
- Still open: the strategy weights do not sum to 1. The positive weights sum to 0.70
  (aggressive), 0.75 (balanced) and 0.90 (exploration) (`priority/strategy.py:65-89`). Under
  the default 60/40 split, a balanced link ranked on NLP alone tops out at 0.75 while an
  LLM-scored link tops out at 0.6 x 0.75 + 0.4 = 0.85. The two kinds of link are still not
  on one scale, and the gap depends on the strategy.
- Still open: the exploration strategy's own split, 0.85 NLP and 0.15 LLM
  (`priority/strategy.py:129`), is never used. The pipeline always passes its normalised
  60/40 (`priority_pipeline.py:153`), so the docstring's "LLM score is a weak signal" is
  not true at run time.
- The composite NLP score (`_nlp_score`) does not enter the priority at all; the
  strategies weight the raw features. Bucketing uses one score and ranking another. This
  is a design question, not a bug, but the fix for the scale should say which is meant.

Method: yes, any fix changes priorities and so the fetch order.
Pins: both pins use the balanced strategy and mix trusted and LLM-scored links, so
`link_scores`, `wire_messages` and very likely `fetch_order` change.
Sign-off: method change. The intended scale is written down first (what a trusted link and
an LLM-scored link with the same evidence should get), then the pins are updated and the
maintainer approves.

### 2. Dropped links

Status: the original bug is fixed; two routes remain. Read, not run.

- Fixed: `PriorityPipeline` was never subscribed to `HighScoreLinksEvent`, so every
  high-confidence link was dropped. It is subscribed now, and the consumers name their own
  events (ADR 2, `tests/test_event_wiring.py`).
- Open: when a scoring call raises, the handler emits `ScoringFailedEvent`
  (`pipelines/scoring_pipeline.py:257-266`) and `LinksScoredEvent` is never sent. The
  high-confidence links were already sent (`:196`), so only the LLM-bound links of that
  page are lost: the mid bucket and the samples. With `llm_batch_size` set, the batches that
  had already succeeded are lost too (`:222-225`). Whether the retry processor brings them
  back, and whether a retry sends the high-confidence links a second time, was not checked.
- Open: `EmptyScoreResultsEvent` cannot fire with the real scoring service.
  `ResultMapper.map_results` always returns the list it was given
  (`services/results_mapper.py:36-38`, `:51`), so `scored_links` is never empty when links
  were sent (`scoring_pipeline.py:226`). A malformed answer leaves the scores at `None`, and
  those links are ranked as NLP-only. The empty-answer retry never runs in a real crawl.

Method: yes, but only when an LLM call raises or answers nothing usable.
Pins: probably unchanged, if the scripted LLM never raises; not checked.
Sign-off: a method review and the method guards (`pytest -m "pins or method_guard"`).
A fix that adds retries of malformed answers changes the LLM call count, so it is a method
change and needs the maintainer's approval.

### 3. Missing score treated as 0

Status: confirmed. Read.

- A link the LLM did not answer for gets `link.score = link.score or 0` and
  `relevance_type = "irrelevant"` (`services/results_mapper.py:43-47`). A malformed entry
  gets the same 0 (`:76-79`).
- Since `1eaec10`, a score of 0 is a verdict (`pipelines/priority_pipeline.py:152`). So a link
  the LLM skipped is ranked as if the LLM had judged it worthless: 0.6 x NLP instead of
  1.0 x NLP. Two correct-looking fixes combine into a wrong one.
- The wire does the opposite: `entry.get("score") or None` (`ui_bridge/telemetry_bridge.py:348`)
  shows a real verdict of 0 as "no LLM score".

Method: yes, it changes the priority of every link the LLM skipped or answered badly.
Pins: change only if the scripted LLM omits or malforms an entry; not checked.
Sign-off: method change. The fix keeps `score = None` for missing and malformed entries
(they are already counted in `outcomes`), with a failing test first. The pins are updated
if they move, and the maintainer approves.

### 4. Weight sources

Status: confirmed. Read.

Where the weights come from:

- Composite NLP weights (`config/config.py:95-99`: target 0.80, context 0.05, boilerplate
  -0.35) were fitted with `tools/nlp_eval.py`: 302 links from five English wikiMD pages on
  one topic (diabetes), labelled by an LLM (`groq`, `openai/gpt-oss-120b`, relevant when the
  score is at least 60; 154 of 302 relevant), with a logistic regression on standardised
  features (`tools/nlp_eval.py:179-186`). The constants are applied to raw features, so they
  are not the printed coefficients, and the step from one to the other is not recorded.
- Priority strategy weights (`priority/strategy.py:65-89`) have no recorded source.

Threats to validity, to report with the study's results:

- The labels came from an LLM that scores links the way the cascade's LLM does, so the NLP
  stage was tuned to agree with the LLM it is meant to pre-filter.
- The tuning predates any pre-registration and used one English topic. The ISI benchmark
  graph is French.

One value, several places:

- `target_top_k`: `config/runtime_config.py:662`, `services/nlp_service.py:81`,
  `services/link_features.py:79`, `nlp/feature_extractor.py:16`. `cluster_eps` and
  `cluster_min_samples` the same way.
- `nlp_bias` and `llm_bias`: `config/runtime_config.py:609`, `:619` and
  `pipelines/priority_pipeline.py:33-34`.
- `composite_score` falls back with `or` (`services/link_features.py:282`), so an empty weight
  dict silently means the defaults.

The benchmark runner takes part of its settings from the config and the rest from
constructor defaults:

- `NLPService` is built without the composite weights, `top_k` or cluster settings
  (`benchmark/runner.py:647-657`).
- `PriorityPipeline(storage, broker)` uses its own 60/40 defaults (`:504`).
- `get_strategy(...)` is called without the configured weights (`:727`).
- `ScoringService` is built without the configured prompts (`:669`).
- The cascade constants are imported from `config` (`:17-23`, `:690-695`) instead of read
  from `cfg.scoring_cascade`.
- `ProcessingPipeline` is built without `link_context_length` (`:500`).

The values are equal today only because `default_runtime_config()` returns the code defaults
(`config/runtime_config.py:970-972`). If a default changes in one place, the crawler and the
benchmark measure different methods, and no test notices.

Method: making each value come from one place changes no value, so it is not a method change.
Refitting the weights is a method change.
Pins: a single-source refactor must leave them unchanged. A refit changes them.
Sign-off: the refactor needs a method review with the pins and method guards passing
unchanged. A refit needs the maintainer's approval, must be pre-registered in the study
protocol, and must be fitted on data kept apart from the evaluation graph and its judge.

### 5. Judge `bool`

Status: confirmed by running it.

- `is_valid_label` uses `isinstance(value, int)` (`benchmark/judge.py:44-45`), and `bool` is a
  subclass of `int`. An answer of `{"labels": {"1": true, "2": false}}` is accepted and
  written to the label log as `true` and `false`. A binary "yes" becomes grade 1, never 2.
  Output: `0/1/2 judge on {true, false}: {'a': True, 'b': False}`.
- The legacy binary judge coerces with `bool(...)` (`benchmark/label.py:82`), so the string
  `"false"` is relevant. Output: `legacy binary judge on {"false", "no"}: {'a': True, 'b': True}`.
- No stored data is affected: all 1,462 labels in `benchmark/data/isi.json` are integers
  (1417 zeros, 44 ones, 1 two). `benchmark/data/ball.json` is unlabelled.

Method: it does not touch the crawler's scores, ordering or prompts. It changes the ground
truth that every result is measured against.
Pins: no; the pins do not use the judge.
Sign-off: a method review of the benchmark code, before any labelling for the study. The fix
starts with a test that fails today: an answer with `true` or `false` labels must be
rejected. The legacy `label.py` judge should be removed or made to reject anything but
`true` and `false`. Its constants are imported by `judge.py` and `label_graph.py`, so they
move first.

### 6. Multilingual embedder

Status: confirmed by reading the data. Not measured.

- The default model is `all-MiniLM-L6-v2` (`config/config.py:43`), an English model.
- The ISI graph is French Wikipedia (for example "Association à but non lucratif", "École
  centrale (Révolution française)"), its topic mixes French and English ("institut superieur
  informatique ISI (tunisia / ariana)"), and the `isi.json` template seeds `fr.wikipedia.org`.
- The model name is written in five places: `config/config.py:43`,
  `nlp/embedding_engine.py:49` and `:125`, `services/nlp_service.py:74`, and the docs.
- No model revision is pinned (`nlp/embedding_engine.py:61`), and the run manifest records
  only the name (`core/crawler.py:315`). A reproducible run needs the model revision in the
  manifest, so this falls short.

Method: yes. A new model changes every NLP score of a real crawl. It also invalidates the
fitted composite weights and the threshold and percentile calibration
(`config/config.py:78-86`). Stored spaces are keyed by model name
(`nlp/space_store.py:29-33`), so old spaces are not reused, which is correct.
Pins: no; they use `HashingEmbeddingEngine`.
Sign-off: method change; the maintainer approves. The model is chosen by measuring
candidates on labelled data kept apart from the evaluation graph, and the choice and its
revision are pre-registered in the study protocol. `make model` changes with it. Models
were not compared here: that needs the download and a measurement run.

### 7. NaN on an all-zero vector

Status: confirmed by running it. The earlier description of this bug is partly wrong.

It said `novelty_injection` is NaN when the parent vector is all zeros. A probe run over
the pins and a direct reproduction show two separate cases:

- **All-zero parent vector** (hashing engine, page text with no word characters):
  `semantic_delta` is NaN (`nlp/feature_extractor.py:91`, no guard). `contextual_consistency`
  comes out as 0 only because of the argument order in `max(0.0, sim)` (`:105-106`). The
  exploration strategy weights `semantic_delta` (`priority/strategy.py:86`), so
  `max(0.0, nan)` gives priority 0.0 to every link of that page, with or without an LLM score
  (`priority/strategy.py:103`). Balanced and aggressive are not affected.
- **All-zero vector in the space** (an empty topic, or an expansion with no word characters):
  `novelty_injection` is NaN (`nlp/feature_extractor.py:175-178`). All three strategies weight
  it, so every link scored against that space gets priority 0.0, and the frontier falls back
  to insertion order.
- This second case is what the pins hit: 8 links, all in
  `tests/pins/test_lockstep_passivity.py:69`, whose synthetic graph has no topic
  (`benchmark/graph.py:69` defaults it to `""`). The zero entry was `__target__benchmark`. No
  parent vector was all zero in any pin.
- If a NaN feature had a composite weight, `max(0.0, min(1.0, nan))` would give 1.0
  (`services/link_features.py:286`). The default composite weights avoid it.
- The NaN reaches the wire in `nlp_breakdown` (`ui_bridge/telemetry_bridge.py:347`), and
  `json.dumps` writes `NaN`, which a browser's `JSON.parse` rejects.
- An empty `target_topic` passes the blueprint schema (`config/blueprint_schema.py:208`).

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
normalises its output. The real model was not run to confirm it. Offline mode and the pins
are affected either way.

The value to use: a zero vector carries no information, so a feature compared against one
should take the neutral value the code already uses for a missing input. That means
`semantic_delta` and `contextual_consistency` behave as when `parent_vec` is `None`
(`:89-90`, `:103-104`). Novelty, density and cluster distance are computed over the non-zero
rows of the space, with the empty-space value when none are left (`:171-172`). Separately,
the blueprint schema and the benchmark runner should refuse an empty topic.

Method: yes, but only in the cases above; ordinary crawls with the real model are unchanged.
Pins: no golden contains a NaN, the probe found no zero parent vector, and the NaN case is
in a test that compares visit lists, not goldens. The goldens are expected unchanged; the
fix must confirm it by running the pins.
Sign-off: a method review of the value defined above. The fix itself is in `nlp/`, a method
file, so its diff gets a method review too. The rule that refuses an empty topic goes into
the blueprint schema as a separate change.

## Review of PRs #4 and #5

### `core/stages.py` (PR #4)

- Every builder passes the same arguments as the `_build_pipelines` it replaced: each was
  compared against `core/crawler.py:403-530` at `ccd6c22^1`. The one difference,
  `inputs.fetcher or NetworkClient(...)` (`core/stages.py:136-137`), came later with the
  offline mode and does not touch the method.
- For the method's events (`NodeAddedEvent`, `PageFetchedEvent`, `LinksScoredEvent`,
  `HighScoreLinksEvent`, `PriorityCalculatedEvent`), the order in which consumers receive
  them is unchanged. The only reorderings are the ones ADR 2 lists (retry after debug, space
  updater after the stages). Read, not run.
- Threat: the pins run the benchmark runner, not `Crawler`, so `core/stages.py` and
  `core/crawler.py` are covered by the wiring tests only, not by any behaviour pin. A wrong
  argument in a builder (a swapped threshold, say) would pass every pin. An offline `Crawler`
  pin (scripted LLM, frozen site) would close this.
- The run manifest (`core/crawler.py:310-321`) has the config, model name, git SHA and seed,
  but no prompt hashes, model revision or library versions. A reproducible run needs all
  three in the manifest; adding them is not done yet.

### Benchmark runner (PR #4, `cfc33bc`)

- The subscription sets are unchanged. Each of the eight stages was built and its
  `event_types` compared with the list the commit removed: all equal as sets.
  `StoragePipeline` and `RetryProcessor` list them in a different order. That does not
  change delivery, because the registry keys by event type and the order of the `subscribe`
  calls is unchanged (`benchmark/runner.py:513-518`).
- Extra components are still subscribed from `handlers` (`:516`), not `event_types`. This is
  harmless, but it is the one consumer left on the old pattern.
- The module docstring (`:3-6`) says the LLM stage is a no-op. That is true for `run_policy`
  only, not for `run_cascade`.
- See bug 4 for the settings the runner takes from defaults instead of the config.
- A graph with no topic runs without complaint and, with hashing embeddings, gives every link
  priority 0 (bug 7). The runner should refuse it.

### `services/link_features.py` (PR #5)

- The pins pass unchanged at `0d21314` (78 passed), which supports ADR 3's claim that the
  code was moved, not rewritten, on the hashing path.
- `_floored_similarity` guards zero vectors for the parent's relevance only (`:67-72`). The
  other cosine calls in `nlp/feature_extractor.py` are unguarded (bug 7).
- The composite fallback uses `or` (`:282`, bug 4).
- The tagged link text is built from `link.anchor` and `link.context` directly
  (`:217`). If either is ever `None`, the word "None" is embedded. Whether `None` reaches
  here was not checked.
- Not a method issue: `region_density` and `novelty_injection_score` loop over the whole
  space in Python for every link (`nlp/feature_extractor.py:156`, `:175`). That is links
  times space size per page on a hot path, which should be vectorised, in a change that
  keeps the values within the pin tolerance.

### `services/space_bootstrap.py` (PR #5)

Reviewed on 2026-10-29. Verdict: the method is unchanged. One behaviour changed, and it
does not reach scores or ordering. The module was compared with `build_space` and
`create_expansions` as they were in `services/nlp_service.py:168-275` at `47f991d^`, and
the two later commits that touch it (`a54dfce`, `434ba4f`) were read. Line numbers below
are `services/space_bootstrap.py` unless a file is named.

- The prompt and the LLM call are the same. The same `ExpansionPromptBuilder` builds the
  prompt from the same arguments (`:69`, `:174`). It goes out in an `ExpansionContext` with
  `llm_type` and `llm_model` read from the same keys when the service is constructed
  (`:67-68`, `:188-192`). The prompt text, and with it the `CachedLlm` key (type, model,
  prompt; `benchmark/llm_cache.py:71`), are unchanged, so cached expansion answers still hit.
- The space is built the same way. The topic is embedded first (`:97`). The seeds are
  embedded in the order the LLM gave them (`:146-150`), with the same keys and metadata,
  added in one `add_batch` (one version bump, `nlp/vector_space.py:60`), and the target
  vector goes in last (`:113-118`). A seed that fails to embed is still logged and reported
  as pruned, and the others are kept (`:151-164`).
- Failures are handled the same way. A failed request or a malformed answer gives no
  descriptions and is counted (`:194-205`). The counter moved from
  `NLPService.expansion_outcomes` to `NLPService.bootstrapper.outcomes`. Only tests read
  either one, then and now (`git grep` at `47f991d^` and at `0d21314`).
- `a54dfce` moves the trace fallback into `_bootstrap_trace` (`:132-138`). It returns the
  same pair the inline code built.
- `434ba4f` is formatting only: `ast.dump` of `services/space_bootstrap.py` and of
  `services/nlp_service.py` is identical before and after it. Verified.
- What changed: the old code set `self.space` (empty) and `self.target_vec` before it
  awaited the LLM (`services/nlp_service.py:190-194` at `47f991d^`). Now both stay local
  until the target vector is in, and reach the service through `adopt` (`:96-97`, `:119`,
  `services/nlp_service.py:132-134`). The space is still saved before
  `EXP_SpaceBootstrapped` is emitted. Nothing reads the space during the bootstrap: both
  callers await `start()` before any stage runs (`core/crawler.py:255`,
  `benchmark/runner.py:658`). If the bootstrap raises, `NLPService.space` is now `None`
  instead of a half-built space, and `start()` fails in both versions. Read, not run.
- Coverage: the pins only cover the scripted LLM answering well. `tests/test_space_bootstrap.py`
  checks that the seeds and the target are in the space and adopted before the bootstrap is
  reported. The bootstrap tests in `tests/test_results_mapper.py` cover the failure outcomes.
  Both files were run: 35 passed.

Problems that were there before PR #5 and that the move kept as they were:

1. A failed expansion becomes the blueprint's space for good. A request error or a
   malformed answer gives a space that holds only the target vector (`:194-204`).
   `save_space` writes it on the first run whatever `persist_space` says
   (`services/nlp_service.py:152-155`), and every later run loads it (`:116-117`). One
   transient LLM failure on a blueprint's first crawl changes the NLP features of every
   later crawl of it. Only a log line records it, and the counter that sees it is never
   reported, although the outcome of every LLM call should be recorded. The benchmark does
   not keep the space (each run gets a new temporary store, `benchmark/__main__.py:136`),
   but a failed expansion there still gives that run a target-only space without notice.
   Recommended fix: do not save a space whose expansion failed, and put the expansion
   outcome in the run manifest. This changes the space only after a failure, so it is a
   method change in that case and needs a method review. The pins should not change,
   because the scripted LLM answers.
2. Seed keys use `hash(description)` (`:149`). Python salts string hashes per process, so
   the same seeds get different keys in every run, and a saved space is not byte-identical
   between runs of the same blueprint. No scoring code reads the keys (`git grep`), so
   scores do not change. It does stop a saved space from being checksummed, which a
   reproducible run needs. Use a content hash of the text. Whether any pin compares keys:
   not checked.
3. `create_expansions` takes its trace from `get_trace()` (`:172`), not from
   `_bootstrap_trace()`. Outside a trace, `EXP_PromptBuilt` therefore carries an empty trace
   id, while the other bootstrap events carry the new one. This affects observability only:
   the events of one bootstrap should share one trace id.
4. The expansion prompt's hash is not in the run manifest. This is the same gap noted above
   for `core/crawler.py:310-321`: a run manifest should hold the hash of every rendered
   prompt, and that applies to this second prompt as well.

Sign-off: the move needs none, since the method and the pins are unchanged. Items 1 and 2
should be fixed, with a method review because this is a method file.

## Order of work for the fixes

1. Judge `bool` (bug 5): no pin impact, and it must land before any labelling.
2. NaN on a zero vector (bug 7) and refusing an empty topic: goldens expected unchanged.
3. Weight sources as a single-source refactor (bug 4): pins unchanged.
4. Missing score (bug 3) and dropped links (bug 2): small, separately pinned changes.
5. Priority scale (bug 1): the largest change to the ordering, after the others, so its pin
   diff shows only its own effect.
6. Embedder (bug 6) and any refit of the weights: an open decision for the maintainer,
   pre-registered in the study protocol, and not changed together with the fixes above.
