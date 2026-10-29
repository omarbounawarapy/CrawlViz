# Requirements

Every feature change traces to a requirement here (UX-3); a feature with no requirement and
no ADR is not built (CODE-3). Owner: ux-researcher. Omar approves the priorities.

Sources: the heuristic review in `docs/usability-log.md` (entry 0, findings `H-…`), the
task journeys in `docs/ux/tasks.md` (tasks `T1` to `T8`), the config persona findings
(`docs/config-persona-findings.md`) and the audits named in the standards plan
(wasted potential, observability, configurability, UX copy, AI-native). The audit reports
were read as the plan's summaries, not as full reports.

## Ranked for Omar's approval

Status: **proposed, not approved.** Rank 1 is the most important.

| Rank | Id | In one line | Tasks | Priority |
|---|---|---|---|---|
| 1 | R-WHY | "Why this score" tab: reason, real prompt and reply, cascade bucket | T3 | P1 |
| 2 | R-HEALTH | Health strip: one state per subsystem, with a next step | T1, T2 | P1 |
| 3 | R-STATE-TRUTH | Status, counts and stage states match the backend | T2 | P1 |
| 4 | R-RUNS | Runs page: list past runs, open one into the graph and scrubber | T4 | P1 |
| 5 | R-EXPORT | Export a dataset or run as CSV or JSONL from the UI | T7 | P1 |
| 6 | R-COST-LIVE | Live LLM calls, tokens and budget left during a crawl | T1, T2 | P1 |
| 7 | R-SKIP-REASON | Every skipped link shows why it was skipped | T3 | P1 |
| 8 | R-SCALE | One score scale across the app | T3, T7, T8 | P1 |
| 9 | R-MODE | The app says whether it runs offline, cached or live, and with which provider | T1, T8 | P1 |
| 10 | R-LOCAL-LLM | Local model preset with a connection test | T6 | P2 |
| 11 | R-LIVE | Change a live setting from the running crawl, for this run or for good | T5 | P2 |
| 12 | R-PREFLIGHT | Run page warns on unsafe limits and cost, names blueprints plainly | T1 | P2 |
| 13 | R-RUN-DIFF | Compare two runs side by side | T4 | P2 |
| 14 | R-RERUN | Rerun a past run from its manifest | T4 | P2 |
| 15 | R-PRECEDENCE | Each setting shows where its value comes from | T1, T5 | P2 |
| 16 | R-PRESET-MERGE | Presets merge into settings after a diff, with undo | T5 | P2 |
| 17 | R-REPLAY-CACHE | Replay a recorded run's LLM answers from cache, free | T4, T8 | P2 |
| 18 | R-BENCH-COMPARE | Benchmark results compare arms in plain words with cost and uncertainty | T8 | P2 |
| 19 | R-SUMMARY | End-of-run summary card | T2, T4 | P3 |
| 20 | R-DEMO-LONG | A longer offline demo so live changes can be tried and measured | T5 | P3 |
| 21 | R-CLI | A `crawlviz` CLI for run, status, runs and export | T1, T4, T7 | P3 |

**Dropped** (no core task needs them; see the end of this file for the reason each):
semantic search, coverage gaps, topic to blueprint with an XPath helper, space management,
weight fitting, prompt playground, per-domain rules, the new config fields as a bundle,
MCP server, LLM explain-score, config suggestions, LLM crawl summary.

**Questions for Omar** are at the end of this file.

## How the ranking was done

Each candidate was scored on three things, in this order:

1. **Task blocked or misled.** The worst finding it fixes: severity 4 (task impossible)
   over 3 (wrong conclusion or large detour) over 2.
2. **Who it serves.** Primary users (U1 crawl researcher, U2 score reviewer) over
   secondary ones (U3 developer, U4 demo visitor).
3. **Fit with the product principle** "every decision shown must be explainable", and
   with the constraints in `PRODUCT.md` (LLM caps, politeness, reproducibility).

Cost of building was used only to break ties. Dependencies on later work (Phase E
backend, Phase G results) do not lower a rank; they are noted per requirement.

- **P1:** Phase E builds its backend and Phase F its UI. The E exit gate checks each one.
- **P2:** built in E and F after the P1 items.
- **P3:** built only after every P2 item, or when Omar promotes it.

## Requirements

### R-WHY: "Why this score" tab (rank 1, P1)

- **Story:** As a score reviewer, I want to see the evidence behind a page's score, so that
  I can judge whether the crawler's decision was sound.
- **Acceptance criteria:**
  1. The node inspector has a "Why" tab, first among the scoring tabs.
  2. It opens with one sentence in plain words: what decided the score (for example "The LLM
     rated it 91 of 100; the NLP score alone would have ranked it low").
  3. It shows the cascade bucket the link fell into (dropped, sampled, sent to the LLM,
     trusted without the LLM), with the thresholds in force for that crawl.
  4. When the LLM scored it: the rendered prompt and the raw reply, the model id, tokens,
     latency and whether it came from cache. Untrusted page text in the prompt is shown
     as data, never rendered as HTML.
  5. NLP signals use their glossary names, each with a `Term` explanation.
  6. Works the same on a live crawl and on a replayed one.
  7. Reachable in at most 3 actions from the graph (usability goal T3).
- **Source:** wasted-potential audit ("Why this score" panel with the real prompt and
  response); H-01.
- **Depends on:** per-node explain data (plan E5), prompt hashes and `LlmCallRecord` (E1).

### R-HEALTH: health strip (rank 2, P1)

- **Story:** As a crawl researcher, I want to see at a glance whether each part of the crawl
  is working, so that I notice rate limits, a missing model or a stall before they waste
  the run.
- **Acceptance criteria:**
  1. A strip, visible on the Graph page during a crawl, shows one state per subsystem:
     embedder (model, device, loading or ready), space, LLM (in flight, backing off,
     budget, keys), fetch backoff, robots, export.
  2. Each state is a word and a shape, not colour alone (A11Y-1).
  3. A state that needs action says what happened and what to do next (UX-1), for example
     "LLM rate limited by Groq, waiting 40 s. Lower the call rate or add a key."
  4. From "Start crawl" until the first page, the UI shows a "Starting" state that names
     the step (loading the model, building the space), not "No crawl yet" or "Waiting for
     backend".
  5. The strip reads the same data as `/status` and the `SUBSYSTEM_STATUS` message, and
     the polling duplicate is removed.
- **Source:** observability audit (health strip, `SUBSYSTEM_STATUS`); H-09, H-11.
- **Depends on:** E3 (`SUBSYSTEM_STATUS`, gateway starts before the NLP build), ADR 8.

### R-STATE-TRUTH: what the UI says matches the crawl (rank 3, P1)

- **Story:** As a crawl researcher, I want every count and state on screen to be true, so
  that I can trust what I see without checking the logs.
- **Acceptance criteria:**
  1. The header shows pages fetched and pages found as two labelled numbers; throughput
     counts fetched pages.
  2. When a crawl ends, no stage shows "Running" or work in flight.
  3. Before any crawl, the status reads "Idle" and no "disconnected" warning is shown.
  4. The end state distinguishes "Stopped by you", "Finished: <limit reached>" and
     "Failed: <what happened, what to do>".
  5. The Pipeline Monitor lists stages in pipeline order.
  6. A test drives each end state through the reducer and checks the words shown.
- **Source:** observability audit; plan C UI bugs (missing completed ticks, `IDLE` state,
  `CRAWL_STOPPED.detail`); H-07, H-08, H-10, H-13.
- **Depends on:** Phase C UI bug fixes, D3 stage names.

### R-RUNS: runs page with replay (rank 4, P1)

- **Story:** As a score reviewer, I want to open a past run, so that I can study a crawl
  after it has finished, in another session.
- **Acceptance criteria:**
  1. A Runs page lists recorded runs: blueprint name, topic, start time, mode (offline,
     cached, live), pages fetched, relevant pages, LLM calls, end reason.
  2. Opening a run loads it into the same graph, inspector and timeline as a live crawl.
  3. A run opens in at most 4 actions from any page (usability goal T4).
  4. A run whose recording is from an older format either opens through the migration
     chain or says why it cannot, and what to do.
  5. Deleting a run uses `ConfirmButton` and offers undo while the toast is visible.
- **Source:** wasted-potential audit (runs page and replay); H-04.
- **Depends on:** `/runs` list, manifest and events (E5); read-side alias map (D4).

### R-EXPORT: export from the UI (rank 5, P1)

- **Story:** As a crawl researcher, I want to download what the crawl extracted, so that I
  can analyse it in other tools.
- **Acceptance criteria:**
  1. The Data page has "Export CSV" and "Export JSONL" for the chosen dataset, and for one
     run when a run is selected.
  2. The export includes the extracted fields, URL, run id, score on the app's one scale
     (R-SCALE) and saved time; the columns are documented.
  3. Datasets are named by blueprint and site, with the table name as secondary text.
  4. The list says "Showing 25 of 39 records", not "25 pages from …".
  5. A failed export says why and what to do; no raw error.
- **Source:** wasted-potential audit (item export); H-05, H-17, H-22.
- **Depends on:** item export as CSV/JSONL (E5), export paths config field.

### R-COST-LIVE: live cost figures (rank 6, P1)

- **Story:** As a crawl researcher on a capped LLM plan, I want to see the calls and
  tokens a crawl has used and has left, so that I stop or adjust before the cap is hit.
- **Acceptance criteria:**
  1. During a crawl, the Measurements drawer and the health strip show LLM calls used of
     the crawl budget, tokens in and out, and cache hits.
  2. When a cost table exists for the model, an estimated cost is shown and labelled as an
     estimate.
  3. When the budget runs out, the strip says so and that links now get NLP-only scores.
  4. After the run, the same figures appear in the Runs list (R-RUNS).
- **Source:** wasted-potential audit (live cost and quality figures); config persona
  findings rows 15 and 16 (cost not a first-class quantity); H-12.
- **Depends on:** `LlmCallRecord` aggregation and the `token_usage` fix (E1).

### R-SKIP-REASON: why a link was skipped (rank 7, P1)

- **Story:** As a score reviewer, I want to know why a link was not followed, so that I can
  tell a sound skip from a mistake.
- **Acceptance criteria:**
  1. Every link that was not followed has one recorded reason: off-topic score below the
     cut-off, not sampled, depth limit, duplicate, robots disallowed, budget exhausted,
     unfetched at stop, give-up after retries.
  2. The inspector lists a page's skipped links with their reason in plain words and the
     score that decided it.
  3. The graph's skipped-link marks open the same reason.
- **Source:** observability audit (`skip_reason` per candidate, drop events); H-03.
- **Depends on:** E3 (`skip_reason`, drop events for depth-cut, dedup, give-up and
  unfetched-at-stop).

### R-SCALE: one score scale (rank 8, P1)

- **Story:** As a score reviewer, I want every score on the same scale, so that I can compare
  them without knowing the code.
- **Acceptance criteria:**
  1. One display scale (0 to 100) for NLP score, LLM score and final priority, in the
     inspector, the graph labels, the Data page, exports and the Benchmark page.
  2. Where a raw value matters (cosine similarity), it is shown as secondary text with its
     name.
  3. The inspector headline never contradicts the signal bars (H-02).
- **Source:** configurability and copy audits; plan F1 (one score display scale); H-02.
- **Depends on:** the one 0-1 priority scale (Phase C method fix, research-scientist
  sign-off). The display scale is UI only and does not change the method.

### R-MODE: say which mode and provider a crawl uses (rank 9, P1)

- **Story:** As a crawl researcher, I want to know before and during a crawl whether it uses
  a live LLM, a cache or the offline doubles, so that I do not spend my cap by mistake, and
  do not mistake demo results for real ones.
- **Acceptance criteria:**
  1. The Run page and the health strip show the mode (offline, cached, live) and, for live,
     the provider and model that will actually be called.
  2. In offline mode the blueprint's provider fields are shown as "not used offline".
  3. The Benchmark Runs form states, for each arm, whether it calls the network and
     roughly how many tokens it will spend; in offline mode live arms are disabled with a
     reason.
  4. Runs recorded offline are marked as such in the Runs list and the export.
- **Source:** observability audit; H-14, H-24.
- **Depends on:** `/ui-config` or `/status` exposing the mode (E5, ADR 9).

### R-LOCAL-LLM: local model (rank 10, P2)

- **Story:** As a crawl researcher, I want to score with a model on my own machine, so that I
  have no daily cap and no data leaves the machine.
- **Acceptance criteria:**
  1. A "Local model" preset for Ollama, with endpoint and model fields; LM Studio, vLLM and
     llama.cpp work through the same OpenAI-compatible fields.
  2. A "Test connection" action reports success, or what failed (no server, model not
     pulled, wrong endpoint) and what to do.
  3. No API key is asked for a keyless provider.
  4. The LLM timeout is a setting, with a longer default for local providers.
  5. A crawl with the preset records the local model id in its manifest.
- **Source:** wasted-potential audit (local LLM); H-06.
- **Depends on:** E1 keyless local providers and `LlmConfig.timeout_s`.

### R-LIVE: change a setting on the running crawl (rank 11, P2)

- **Story:** As a crawl researcher, I want to slow down or cut spend on a running crawl, so
  that I do not have to restart it.
- **Acceptance criteria:**
  1. From the running Graph page, the live fields (min delay, jitter, backoff max, workers,
     retries) can be changed in at most 4 actions.
  2. The user chooses "This run only" or "This run and future runs"; "This run only" does
     not change the stored settings.
  3. The change appears in the event stream and the timeline ("Min delay 1 s → 3 s"), so a
     replay shows when it happened.
  4. A value the backend rejects shows the field's own message.
- **Source:** configurability audit; H-19.
- **Depends on:** `PATCH /config/live` without persistence (E4), a live-change event.

### R-PREFLIGHT: safe start (rank 12, P2)

- **Story:** As a crawl researcher, I want the Run page to warn me before I start a crawl
  that is larger or costlier than I meant, so that I do not overload a site or my budget.
- **Acceptance criteria:**
  1. Blueprints are listed by name and topic, not file name.
  2. A limit above the safe defaults (500 pages, depth 5, 1 h) shows a warning with the
     default beside it.
  3. The LLM estimate is compared with the crawl budget and the provider cap when known.
  4. The chosen blueprint survives a reload.
  5. Numbers use one format through `format.ts` (I18N-1).
  6. A preflight failure from `POST /run` (no model, bad blueprint) says what is wrong
     and what to do.
- **Source:** configurability and copy audits; plan C (safe default limits, preflight);
  H-15, H-16, H-17, H-27.
- **Depends on:** C preflight and `last_error` on `/status`.

### R-RUN-DIFF: compare two runs (rank 13, P2)

- **Story:** As a score reviewer, I want to compare two runs, so that I can see what a
  setting or prompt change did.
- **Acceptance criteria:**
  1. Choose two runs from the Runs page and open a comparison.
  2. It shows the settings and prompt-hash differences, then pages fetched, relevant pages,
     LLM calls and tokens side by side, and pages found by one run only.
  3. Reachable in at most 6 actions (usability goal T4).
- **Source:** wasted-potential audit (run diff).
- **Depends on:** `/runs/{a}/diff/{b}` or equivalent (E5), manifests with prompt hashes.

### R-RERUN: rerun from a manifest (rank 14, P2)

- **Story:** As a researcher, I want to rerun a past run with exactly its settings, so that
  I can reproduce it or change one thing.
- **Acceptance criteria:**
  1. "Run again" on a past run starts a crawl with its blueprint, settings and random seed.
  2. "Edit and run" opens the Run page with those values as overrides, showing what
     differs from the stored settings.
  3. The new run's manifest links to the run it came from.
- **Source:** wasted-potential audit (re-run from manifest); configurability audit
  (load config from manifest).
- **Depends on:** load-config-from-manifest (E4), `/runs/{id}/rerun` (E5).

### R-PRECEDENCE: where a value comes from (rank 15, P2)

- **Story:** As a crawl researcher, I want to see where each setting's value comes from, so
  that I know what to change when a crawl does not use the value I expected.
- **Acceptance criteria:**
  1. Each field on the Config page and in the Run drawer shows its source: built-in
     default, stored settings, preset, blueprint or run override.
  2. A field overridden by a later source says which one wins.
  3. The Run page lists the run's effective values that differ from the defaults.
- **Source:** configurability audit (precedence display); H-20.
- **Depends on:** precedence chain with per-field provenance (E4).

### R-PRESET-MERGE: presets merge, with a diff and undo (rank 16, P2)

- **Story:** As a crawl researcher, I want applying a preset to change only the fields it
  names, after I see what changes, so that I do not lose my other settings.
- **Acceptance criteria:**
  1. Applying or importing a preset merges it into the draft and shows the diff before
     anything is saved.
  2. Nothing uses `window.confirm`; confirmation is `ConfirmButton` (UX-2).
  3. After saving, an undo toast restores the previous settings.
  4. Single-preset import and export as a file.
- **Source:** configurability audit (preset merge with diff); plan C config bug (a preset
  replaces settings); H-21.
- **Depends on:** C merge fix, E4 single-preset import and export.

### R-REPLAY-CACHE: replay from cache (rank 17, P2)

- **Story:** As a researcher, I want to replay a recorded run's LLM answers from the cache,
  so that I can test a setting change without spending my cap.
- **Acceptance criteria:**
  1. "Replay with cache" on a past run starts a crawl that reads LLM answers from that
     run's cache and makes no live calls.
  2. Calls missing from the cache are counted and shown, and are either skipped or sent
     live only if the user chose that before starting.
  3. The run is marked "cached" in its mode (R-MODE).
- **Source:** wasted-potential audit (free replay from cache).
- **Depends on:** replay from cache (E5), `CachedLlm`.

### R-BENCH-COMPARE: benchmark comparison in plain words (rank 18, P2)

- **Story:** As a score reviewer, I want to compare benchmark arms with their cost and
  uncertainty, so that I can judge the paper's claim.
- **Acceptance criteria:**
  1. Arms have plain names with the code id as secondary text ("Every link to the LLM
     (`llm_all`)").
  2. Results show harvest per arm with run counts and the intervals the study protocol
     defines, and tokens per relevant page.
  3. Labels 0, 1 and 2 are named on screen; no reference to a repository file as the only
     explanation.
  4. Valid, invalid and replay runs are separated, and the reason a run is invalid is shown.
- **Source:** copy audit; H-17, H-23.
- **Depends on:** Phase G protocol and results (G2, G6). Until then only criteria 1, 3
  and 4 can be built.

### R-SUMMARY: end-of-run summary (rank 19, P3)

- **Story:** As a crawl researcher, I want a short summary when a crawl ends, so that I know
  what it achieved without reading the graph.
- **Acceptance criteria:**
  1. When a crawl ends, a card shows pages fetched, relevant pages, LLM calls and tokens,
     end reason, and the five best pages with links into the inspector.
  2. Computed from recorded data, not written by an LLM.
  3. The same card heads a run on the Runs page.
- **Source:** AI-native audit (crawl summary), kept without the LLM.

### R-DEMO-LONG: a longer offline demo (rank 20, P3)

- **Story:** As a tester (or a measurement flow), I want an offline crawl that runs long
  enough to try live changes and watch health, so that tasks T2 and T5 can be measured
  without keys.
- **Acceptance criteria:**
  1. An offline blueprint runs for at least two minutes at default pacing.
  2. It can produce a rate-limit episode and a budget run-out on demand, so the health strip
     can be exercised.
- **Source:** entry 0 ("T5 not observed: the demo crawl ends in about ten seconds").
- **Depends on:** offline doubles (test-engineer), no method change.

### R-CLI: command line (rank 21, P3)

- **Story:** As a developer or researcher scripting crawls, I want `crawlviz run`, `status`,
  `runs` and `export`, so that I can run and collect crawls without the browser.
- **Acceptance criteria:**
  1. The CLI calls the same service layer as the API (ADR 12); no logic of its own.
  2. Every error says what happened and what to do; exit codes are documented.
  3. `crawlviz export <run> --format csv` writes the same file as R-EXPORT.
- **Source:** AI-native audit (CLI).
- **Depends on:** D2 console script, ADR 12 service layer.

## Dropped

Dropped under CODE-3: no core task needs them now. They are not kept for later; a new
requirement, with a task it serves, is needed to bring one back. The plan's E5 and F4
lists shrink accordingly.

| Candidate | Source audit | Why dropped |
|---|---|---|
| Semantic search | wasted potential | T3 starts from the graph or a URL, which exists ("Find a URL"); no task needs searching page text by meaning |
| Coverage gaps | wasted potential | No task asks "what did the crawl miss"; the benchmark's unreachable-pages figure covers the research need |
| Topic to blueprint, XPath helper | wasted potential | Creating a blueprint is not a core task; the Blueprints wizard exists |
| Space management | wasted potential | No task; the semantic space is an internal artefact. Delete-run privacy goes with R-RUNS |
| Weight fitting | wasted potential | A method change, not a user task; belongs to the research-scientist and the study protocol |
| Prompt playground | wasted potential | The Config page already has a prompt preview built from the real code (`POST /config/prompts/preview`) |
| Per-domain rules | configurability | No task needs different rules per site; per-host rate limiting is a politeness fix in Phase C, not a UI feature |
| New config fields, as a bundle | configurability | Each field must trace to a requirement or bug fix. Kept only where one needs it: LLM timeout (R-LOCAL-LLM), export paths (R-EXPORT), WebSocket host (the `ui_port` bug) |
| MCP server | AI-native | No core task is done by an agent on the user's behalf; ask Omar (question 3) |
| LLM explain-score | AI-native | An LLM explaining another LLM's score is not evidence; R-WHY shows the real prompt and reply instead |
| Config suggestions | AI-native | Rule-based suggestions already exist on the Config page (`SuggestionsStrip`) |
| LLM crawl summary | AI-native | R-SUMMARY gives the same facts from recorded data, with no cost and no invented content |

## Questions for Omar

1. **Order of P1.** Is R-WHY first right, or should R-HEALTH or R-RUNS lead? R-WHY is first
   because it is the product's stated purpose ("see and trust why the crawler went where it
   did") and today it cannot be answered.
2. **Local LLM rank.** R-LOCAL-LLM is P2, rank 10, although T6 is fully blocked today. Move
   it into P1 if the Groq cap is what limits your studies.
3. **MCP server and CLI.** Dropped and P3. Do you want CrawlViz to be driven by agents
   (an MCP server), for example for the agent team's own testing? If so, it needs a task
   added to the context of use first.
4. **Score scale.** R-SCALE proposes 0 to 100 on screen everywhere. Is that the scale you
   want readers of the paper to see?
5. **Testers.** Who can take part in SUS sessions besides you (a supervisor, a colleague),
   and how many? Five or more makes the score more than an anecdote.
