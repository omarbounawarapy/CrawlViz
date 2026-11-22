# Usability log

Append-only (enforced by `.claude/hooks/append_only.py`). Each entry is one measurement
round under ISO 9241-11: effectiveness, efficiency and satisfaction on the core tasks in
`docs/ux/tasks.md`. Never edit an earlier entry; correct it in a later one.

---

## Entry 0: baseline heuristic review (2026-10-29)

**Build:** `main` at `0d21314`, on branch `phase-b-discovery`.
**Method:** expert heuristic review against ISO 9241-110:2020 (interaction principles) and
Apple HIG principles (hierarchy, consistency, agency, feedback, progressive disclosure,
familiarity), plus a task walkthrough by the ux-researcher agent. Inputs: the running app,
the config persona findings (`docs/config-persona-findings.md`), the config pass archive,
and the audit summaries in the standards plan.
**Environment:** offline mode, `offline_demo.json`, Chrome, window about 1568 px wide.

### What was not measured

Said plainly, because entry 0 is a baseline and later entries compare against it:

- **No step counts, task times or success rates were measured.** There is no browser test
  harness yet (`make e2e` does not exist). The flows to measure are listed below.
- **No satisfaction score.** No SUS session has been run. The script is `docs/ux/sus.md`;
  Omar runs it, not an agent.
- **No real users.** The findings come from one agent walkthrough and code reading. They
  are hypotheses to check with Omar and testers.
- **Not observed in the app:** T5 live change (the demo crawl ends in about ten seconds,
  too short to change a setting while it runs), T6 local LLM (no local provider exists),
  T8 comparison (no benchmark runs exist), starting a benchmark arm (not tried, because in
  offline mode the form still offers live-LLM arms and the network use is not stated), the
  sample replay, keyboard-only use, 360 px width, 400% zoom, screen readers.
- The audit reports themselves were not available as files; only their summaries in the
  standards plan were. Findings cite the plan's audit names.

### Environment note

`make dev` runs `uvicorn --reload`, which watches `.claude/worktrees/`. While another agent
worked in a worktree, the API restarted repeatedly: the Benchmark page stayed on "Loading…"
and state was lost between pages. The review continued with the API started without
`--reload`. This also affects any future measured session (CHANGE-REQUEST to the
platform-engineer in the phase B report).

### Findings

Severity: 4 blocks the task, 3 major (wrong conclusion or large detour), 2 minor (slows or
confuses), 1 cosmetic. Source: **O** observed in the app, **C** read from code, **A** from an
audit or persona finding.

| Id | Task | Principle | Finding | Sev | Src | Requirement |
|---|---|---|---|---|---|---|
| H-01 | T3 | Suitability for the task; self-descriptiveness | The inspector cannot answer "why 91": the LLM prompt and reply are not shown, only a number and eleven signal bars with code names ("novelty injection", "region density") | 4 | O | R-WHY |
| H-02 | T3 | Conformity with expectations; consistency | Three scales on one panel: LLM 91/100, queue priority 0.455, NLP score 0.000; the headline says "NLP similarity 0.00" while the target similarity bar reads 0.09 | 3 | O | R-SCALE |
| H-03 | T3 | Suitability for the task | A skipped link has no reason; "Show 3 links the crawler skipped" shows that they were skipped, not why | 3 | O | R-SKIP-REASON |
| H-04 | T4 | Suitability for the task | No way to open a past run: no runs list, no diff, no rerun; recorded runs on disk are not reachable from the UI | 4 | O | R-RUNS, R-RUN-DIFF, R-RERUN |
| H-05 | T7 | Suitability for the task | No export or download in the UI; the user has to find the export files on disk | 4 | O | R-EXPORT |
| H-06 | T6 | Suitability for the task | No local LLM provider or preset | 4 | C | R-LOCAL-LLM |
| H-07 | T2 | Self-descriptiveness; feedback | After "Finished (max nodes reached)" the Pipeline Monitor still showed Request "Running, 4 in flight, queue 269", Filtering "Running, 39 in flight", Priority "Running, 23 in flight" | 3 | O | R-STATE-TRUTH |
| H-08 | T2 | Self-descriptiveness | The header "311 pages" counts found links; 40 pages were fetched. Throughput "30.36 pages/s" uses the same count | 3 | O | R-STATE-TRUTH |
| H-09 | T1, T2 | Feedback; use error robustness | For several seconds after "Start crawl" the graph says "No crawl on the plate yet" and "Waiting for backend", which reads as a failure | 3 | O | R-HEALTH |
| H-10 | T2 | Self-descriptiveness | Before any crawl the header says "Waiting for backend" and "Live feed: disconnected" although the API is up; there is no idle state | 2 | O | R-STATE-TRUTH |
| H-11 | T2 | Suitability for the task | No subsystem health: embedder, LLM (in flight, backoff, budget, keys), fetch backoff, robots and export state are invisible; a rate-limited crawl and a stalled one look the same | 3 | C, A | R-HEALTH |
| H-12 | T1, T2 | Suitability for the task | LLM cost is only an estimate before the run; no live count of calls, tokens or budget left during it | 3 | O, A | R-COST-LIVE |
| H-13 | T2 | Conformity with expectations | A crawl the user stopped also shows "Finished" (`Shell.jsx:45` maps STOPPED to "Finished") | 2 | C | R-STATE-TRUTH |
| H-14 | T1 | Self-descriptiveness | Nothing says the crawl runs offline (scripted LLM, frozen site); the blueprint names OpenRouter and a model, so the user cannot tell which provider is used | 3 | O | R-MODE |
| H-15 | T1 | Use error robustness | `isi.json` shows "Stops after 120 000 pages", "up to 120,000" LLM calls and "6 000 links from a seed" with no warning; the Run page defaults to it even in offline mode | 3 | O | R-PREFLIGHT |
| H-16 | T1, T7, T8 | Consistency (I18N-1) | Number formats differ on one screen: "120 000 pages" and "up to 120,000"; "5 865" beside "5865" on Benchmark | 1 | O | R-PREFLIGHT (copy) |
| H-17 | T1, T7 | Self-descriptiveness; familiarity | Internal names shown as labels: blueprint file names (`isi.json`), dataset table names (`fr_wikipedia_org_offline_demo`), `PATHFINDING`, arm ids (`llm_all`, `no_llm`, `anchor_lexical`), percent-encoded titles, parent shown as id `101` | 2 | O | R-PREFLIGHT, R-EXPORT, R-BENCH-COMPARE |
| H-18 | all | Learnability | Product jargon in primary copy: "Open the plate", "No crawl on the plate yet", "Vermilion marks…" | 2 | O | none (copy fix, CHANGE-REQUEST) |
| H-19 | T5 | Controllability | Applying a live change also saves it for future crawls; "this run only" is not offered from Config, and the running graph gives no sign the change took effect | 3 | C | R-LIVE |
| H-20 | T5 | Controllability | The Config page does not show where a value comes from (default, stored, preset, blueprint, run override) | 2 | C, A | R-PRECEDENCE |
| H-21 | config | Agency (HIG); use error robustness | Applying or importing a preset replaces the stored settings, guarded only by `window.confirm` (`PresetsPanel.jsx:63,125`); no undo anywhere in the app | 3 | C, A | R-PRESET-MERGE |
| H-22 | T7 | Self-descriptiveness | "25 pages from fr_wikipedia_org_offline_demo" is the page size, not the total | 1 | O | R-EXPORT |
| H-23 | T8 | Self-descriptiveness | Benchmark labels 0/1/2 are not explained; the page refers to `GRAPH_RULE.md`; "Found @30" is unexplained | 2 | O | R-BENCH-COMPARE |
| H-24 | T8 | Use error robustness | In offline mode the Runs form offers "Cascade (live LLM)" with no statement of whether it calls the network or spends the Groq cap | 3 | O | R-MODE |
| H-25 | config | Familiarity; ethics | Fetch offers header sets that impersonate browsers ("Desktop Chrome… Fewer pages refuse it"); this contradicts ETH-1 | 3 | O | none (plan C removes them) |
| H-26 | nav | Self-descriptiveness | Navigation tabs carry their purpose only in `title=` tooltips, unreachable by keyboard and touch (`Shell.jsx:76`) | 2 | C, A | none (F5 accessibility pass) |
| H-27 | T1 | Controllability | The blueprint chosen on the Run page resets to `isi.json` after a reload | 1 | O | R-PREFLIGHT |

What works well and should be kept: the Config page's grouping by intent ("Be gentler",
"Look like a browser"), effect lines on every field, the politeness summary and backoff
chart that use the draft values, the "Start here" goal cards with a preview before apply,
the graph's legend and shape-plus-word status marks, `ConfirmButton` on blueprint delete and
reset, and "Showing the 159 most important of 311 pages… Show all".

### Usability goals for later entries

Targets for the measured rounds (agent flows for steps and time, Omar and testers for
SUS). They are goals, not results.

| Task | Effectiveness | Efficiency | Satisfaction |
|---|---|---|---|
| T1 start | 100% start the intended blueprint; 100% can state mode and LLM cap before starting | at most 4 actions from the Graph empty state to a running crawl | |
| T2 watch | 90% name the fetched count and any unhealthy subsystem | answer within 10 s of looking | |
| T3 why | 90% state a reason grounded in the prompt, reply or signals | at most 3 actions from the graph | |
| T4 replay | 90% open a past run; 80% compare two | at most 4 actions to open, 6 to compare | |
| T5 live | 90% change a live field and see it acknowledged | at most 4 actions, crawl not restarted | |
| T6 local LLM | 80% run with a local model when one is installed | under 3 minutes from the Config page | |
| T7 export | 100% get a CSV of a run | at most 3 actions from the Data page | |
| T8 benchmark | 90% name the better arm and its cost | at most 3 actions from the Benchmark page | |
| overall | | | SUS at least 68 at the end of F, at least 75 at H |

### Flows to measure once the browser harness exists

One flow per task, each recording actions, wall time and pass or fail, run in offline mode
in both themes with axe. Owned by the ux-researcher under `crawler-ui/e2e/usability/`.

1. **T1:** Graph empty state → Start a crawl → choose `offline_demo` → Start → first node
   visible. Record time to first node.
2. **T2:** during the crawl, read fetched count and health state; after the end, read the
   end reason. Pass if both match the backend `/status`.
3. **T3:** open the node with the highest score → reach the reason, prompt and reply; open
   one skipped link → reach its reason.
4. **T4:** finish a crawl → open the Runs page → open the run → scrub to the middle; open
   two runs in compare.
5. **T5:** start a long offline crawl → change min delay live → see the acknowledgement →
   check `/config/stored` is unchanged when "this run only" was chosen. Needs R-DEMO-LONG.
6. **T6:** apply the local preset against a stub endpoint → connection test → crawl uses it.
7. **T7:** Data page → dataset → Export CSV → file has the documented columns.
8. **T8:** Benchmark page with fixture results → read harvest and tokens per arm.

Flows 4 to 8 depend on requirements that are not built yet; until then they record the
failure, which is the baseline.
