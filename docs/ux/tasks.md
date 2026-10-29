# Core tasks and journeys

The eight core tasks from the context of use (`PRODUCT.md`, Context of use). Each task has
its users, goal, success criterion, the journey as it works today and the journey it
should become. "Today" comes from a walkthrough of the running app in offline mode on
2026-10-29 (`CRAWLVIZ_OFFLINE=1`, `offline_demo.json`, Chrome on a 1568 px wide window).
Steps marked **(not observed)** were read from code or the plan, not seen in the app.

Requirement ids (`R-…`) point to `docs/ux/requirements.md`. Usability goals and the
baseline are in `docs/usability-log.md`.

## T1. Start a crawl from a blueprint

- **Users:** U1, U3, U4.
- **Goal:** a crawl runs for the right topic, with limits and LLM cost the user expects.
- **Success:** the graph shows the first pages, and the user could have said beforehand
  how many pages and LLM calls the crawl may use.

**Today**
1. Landing page, "Open the plate" (term not explained).
2. Graph page empty state, "Start a crawl".
3. Run page: pick a blueprint from a select of file names (`isi.json`, `wikiMD.json`,
   `offline_demo.json`). The default is `isi.json`, not the offline blueprint, even in
   offline mode.
4. Read "What this will run": topic, strategy (`PATHFINDING`, a raw enum), page limit,
   LLM call estimate, depth.
5. "Start crawl". The app jumps to the Graph page, which shows "No crawl on the plate yet"
   and "Waiting for backend" for several seconds while the crawl starts.
6. Pages appear.

**Pain points:** nothing says the run is offline (scripted LLM, frozen site) although the
blueprint names OpenRouter and a model; the `isi.json` defaults read "Stops after 120 000
pages", "up to 120,000" LLM calls and "6 000 links from a seed" with no warning; numbers
use two formats on one screen; the start gap looks like a failure.

**Should become:** pick a blueprint by name and topic, see mode (offline or live, which
provider), limits and an LLM cost estimate with a warning over a safe default, start, and
see a "starting: loading model, building space" state until the first page (R-HEALTH,
R-PREFLIGHT).

## T2. Watch progress and system health

- **Users:** U1, U3.
- **Goal:** know whether the crawl is healthy, slowed down, rate limited, off topic or
  stuck, and why it ended.
- **Success:** the user can say, within a few seconds of looking, what the crawl is doing
  and whether any subsystem needs action.

**Today**
1. Header line: "311 pages · 55 links skipped", a status word, "Live feed: disconnected"
   or "connected".
2. "Measurements" opens a drawer: pages discovered, throughput, elapsed, links skipped,
   errors, slowest stage, "How far pages got", Pipeline Monitor, recent activity.

**Pain points:** before any crawl the header says "Waiting for backend" and "Live feed:
disconnected" although the API is up (the WebSocket exists only during a crawl); "pages" in
the header counts discovered links (311) while 40 were fetched; after "Finished (max nodes
reached)" the Pipeline Monitor still showed Request "Running, 4 in flight, queue 269",
Filtering "Running, 39 in flight" and Priority "Running, 23 in flight"; the monitor lists
stages out of pipeline order; no LLM calls, tokens, budget left, backoff, embedder or
robots state is shown anywhere.

**Should become:** a health strip with one state per subsystem (embedder, space, LLM,
fetch backoff, robots, export) and a plain next step when one needs action; pages fetched
vs found; LLM calls and budget left; an ending that says "stopped by you", "finished: page
limit" or "failed: <reason, next step>" (R-HEALTH, R-COST-LIVE, R-STATE-TRUTH).

## T3. Understand why a page scored X, or why a link was skipped

- **Users:** U2 first, U1.
- **Goal:** for one page, the evidence behind its score and its place in the queue; for a
  skipped link, the reason.
- **Success:** the user can state the reason in one sentence and point at the evidence
  (the prompt and reply, or the NLP signals), on one score scale.

**Today**
1. Click a node (or find it by URL). An inspector opens: "The LLM rated this link 91/100,
   after NLP similarity 0.00."
2. Overview tab: queue priority 0.455, LLM score 91, parent `101` (an id), depth.
3. Scoring tab: eleven NLP signal bars with code names ("novelty injection", "region
   density", "boilerplate score"), NLP score 0.000, final priority 0.455, strategy.
4. Activity tab: stage history, ending "scoring completed: 0 sent to LLM".
5. "Show 3 links the crawler skipped" toggles skipped links on the graph.

**Pain points:** three scales on one panel (91/100, 0.455, 0.00); the headline says the
NLP similarity was 0.00 while the target similarity bar shows 0.09; the LLM's prompt and
reply are not shown, so "why 91" cannot be answered; the activity line "0 sent to LLM"
contradicts the headline for a reader who does not know it refers to the page's own links;
the title is percent-encoded (`/Universit%C3%A9_de_Leipzig`); no skip reason per link
(the skip reason is not recorded by the backend yet, plan E3).

**Should become:** a "Why this score" tab with the plain-words reason, the real prompt and
reply, the cascade bucket and thresholds that sent it there, NLP signals with glossary
terms, one score scale, and for a skipped link its skip reason (R-WHY, R-SKIP-REASON,
R-SCALE).

## T4. Replay or compare past runs

- **Users:** U2, U1.
- **Goal:** reopen a finished run, scrub through it, compare two runs, rerun one with the
  same settings.
- **Success:** a past run opens from a list in a few steps, and two runs can be compared
  on pages found, relevant pages and LLM cost.

**Today**
1. Within the session, the timeline bar scrubs the current crawl ("Event 198 of 198").
2. The landing page offers "Load a sample replay" and the Graph empty state "Load a
   synthetic sample" (not tried in this walkthrough).
3. There is no list of past runs. The Data page lists runs of a dataset only as a filter
   for extracted records.

**Pain points:** no runs page, no diff, no rerun from manifest; recorded runs exist on disk
(`events.jsonl`, manifests) but the UI cannot open them.

**Should become:** a Runs page listing past runs with blueprint, date, mode, pages, cost
and end reason; open one into the same graph and scrubber; compare two; rerun from its
manifest (R-RUNS, R-RUN-DIFF, R-RERUN).

## T5. Change a setting live

- **Users:** U1.
- **Goal:** slow down, cut LLM spend or change a limit on a running crawl without losing it.
- **Success:** the change applies to the running crawl, the user sees that it did, and
  knows whether it was also saved for later crawls.

**Today (partly observed)**
1. Config page, a section (Fetch), fields with a `LIVE` badge (min delay, jitter max,
   backoff max; also workers and retries).
2. Edit a value. **(not observed)** An "apply live" action calls `PATCH /config/live` and
   then saves to the stored settings too (`ConfigPage.jsx:181-193`).

**Not observed:** the offline demo finishes in about ten seconds, too short to change a
setting while it runs. The live path was not exercised in the browser.

**Pain points (from code):** applying live also persists the value, so "for this run
only" is not possible from the Config page; the Run drawer's overrides apply only at start;
no feedback in the graph that a live change took effect; the Config page is not reachable
from the running graph without leaving it.

**Should become:** change a live field from the running crawl (drawer or health strip),
choose "this run" or "this run and future runs", and see the change acknowledged in the
event stream (R-LIVE). Needs a longer offline fixture to measure (R-DEMO-LONG).

## T6. Run with a local LLM

- **Users:** U1, U3.
- **Goal:** score with a model on the user's own machine (Ollama, LM Studio, vLLM,
  llama.cpp), with no key and no daily cap.
- **Success:** the user picks a local preset, checks that the endpoint answers, and runs a
  crawl that uses it.

**Today (not observed in the app):** no local provider exists in the backend (no keyless
provider, no Ollama endpoint; plan E1). The Config page has a Providers section and API
keys; a user could try an OpenAI-compatible base URL, but this was not tried.

**Should become:** a "Local model" preset with endpoint, model name and a connection test
that says what is wrong and what to do (R-LOCAL-LLM).

## T7. Export results

- **Users:** U1, U2.
- **Goal:** take the extracted items, and the scores, out as CSV or JSONL.
- **Success:** a download from the UI, of one run or all runs, with a known schema.

**Today**
1. Data page: choose a dataset from table names (`fr_wikipedia_org_offline_demo`), optional
   run filter, per-page count.
2. Records list: title, URL, first paragraph, saved time, score out of 100 on some,
   "Open in graph".

**Pain points:** no export or download control in the UI; the export files are written to
disk by the export sink, so the user must know where to look; dataset names are internal
table names; "25 pages from fr_wikipedia_org_offline_demo" reads as a total but is the page
size.

**Should become:** "Export CSV" and "Export JSONL" for a dataset or a run, plus the
scores and skip reasons as a second table (R-EXPORT).

## T8. Compare benchmark arms

- **Users:** U2, Omar.
- **Goal:** see whether the cascade beats the baselines, by how much, at what token cost,
  with the uncertainty.
- **Success:** the user reads harvest and cost per arm on one chart and table, with run
  counts and confidence intervals, and knows which runs are valid.

**Today**
1. Benchmark page, tabs Overview, Results, Runs, Graph, Audit.
2. Overview: "No study protocol has been written yet", then graph statistics for
   `ball.json` and `isi.json` (labels 0/1/2 not explained; refers to `GRAPH_RULE.md`).
3. Results: "No valid runs yet." (no runs exist after the pilot was archived).
4. Runs: a form to start an arm (`Cascade (live LLM)`, `llm_all`, `no_llm`, baselines),
   budget, repeats, LLM cache, recorded runs file; a token estimate note about Groq's cap.

**Not observed:** comparison itself, because there are no runs. Starting an arm was not
tried: in offline mode the form still offers live-LLM arms and nothing says whether the job
would use the network.

**Should become:** arms named in plain words with the code name as secondary text; the
Results chart with run counts, intervals and tokens per relevant page; a clear mode line
(live, cached, offline); valid and invalid runs separated (R-BENCH-COMPARE). Real data
arrives with Phase G.

## Task to requirement map

| Task | Requirements |
|---|---|
| T1 | R-PREFLIGHT, R-HEALTH, R-MODE, R-PRECEDENCE |
| T2 | R-HEALTH, R-COST-LIVE, R-STATE-TRUTH, R-SUMMARY |
| T3 | R-WHY, R-SKIP-REASON, R-SCALE, R-EXPLAIN-LLM |
| T4 | R-RUNS, R-RUN-DIFF, R-RERUN, R-REPLAY-CACHE |
| T5 | R-LIVE, R-DEMO-LONG |
| T6 | R-LOCAL-LLM |
| T7 | R-EXPORT |
| T8 | R-BENCH-COMPARE |
