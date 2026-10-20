# Working on CrawlViz

This file is for every contributor, human or agent. CLAUDE.md holds the standards codes;
this file holds how the work is organised and done.

## Repository map

| Path | What it holds |
|---|---|
| `main.py`, `routes/` | FastAPI app and routers (run, templates, config, benchmark, validation) |
| `core/` | Crawler composition root, event broker, live settings, bootstrapping |
| `pipelines/` | Crawl stages, sinks and observers (renamed by the pipeline naming scheme, NAME-5) |
| `events/`, `traceability/`, `ui_bridge/` | Event types, trace events, the WebSocket telemetry bridge |
| `services/`, `nlp/`, `priority/`, `models/` | Scoring, embeddings and the semantic space, ranking, domain models and prompts |
| `infrastructure/` | HTTP client, LLM handler and provider translators, keys, call budget |
| `config/` | `RuntimeConfig`, settings store, paths |
| `benchmark/` | Frozen-graph benchmark, judges, audit, analysis, `PROTOCOL.md` |
| `crawler-ui/` | React app (Vite, d3, vitest) |
| `tests/` | pytest suite; `tests/agents/` checks the agent guard hooks |
| `docs/` | Architecture and developer docs; `docs/adr/` decisions; `docs/ux/` requirements |
| `.claude/` | Agent definitions, ownership map, guard hooks, templates |

The backend is moving to `src/crawlviz/<domain>/` one domain at a time (ARCH-1). Until a
domain has moved, its files stay where the table says.

## Commands

| Command | What it does |
|---|---|
| `make install` | Python and Node dependencies |
| `make dev` | API on :8000, Vite on :5173; the crawl WebSocket starts on :8765 per crawl |
| `make lint` | ruff and ESLint |
| `make test` | pytest and vitest |
| `make check-changed` | ruff, ESLint and the tests that cover the files your branch changed |
| `make typecheck` | mypy strict; modules on the legacy list in `pyproject.toml` are skipped, and the list only shrinks |
| `make format` | ruff format (the repo is not formatted yet; do not run it on unrelated files) |
| `make check` | lint, type check, all tests, hook tests and the UI build: what CI runs |
| `make hook-test` | the agent guard hook tests |
| `uv run pytest -m pins` | the behaviour pins (`tests/pins/README.md`); goldens change only with `--update-pins` |
| `python3 .claude/hooks/commit_msg_check.py --range main..HEAD` | commit titles in a range |

Planned in phase A and not available yet: `CRAWLVIZ_OFFLINE=1`,
`make e2e`, `make model`. Do not document or rely on them until they exist.

## How we work

1. **Thorough over quick.** When a quick fix and a harder, better one both exist, take the
   better one. Design for extension; add validation, tests and checks by default. Never stop
   at a partial result without saying so plainly.
2. **A named scope is a direction, not a limit.** Fix related findings you come across in
   your area. Outside your area, raise a CHANGE-REQUEST instead of calling it out of scope.
3. **Verify by running.** Test what the docs describe. If something cannot be tested here,
   write a script for Omar to run and read its log.
4. **Report faithfully.** Quote failing output, name skipped steps, write down assumptions,
   and call something done only when it has been verified.
5. **Review your own diff** before you hand it off, and fix what you find.
6. **Ask before any public action**: push, PR, issue comment, release, DOI. Approval for one
   action does not carry over to the next.
7. **Write plainly.** No em dashes, no AI-sounding prose; run the no-ai-slop skill on docs,
   PR text and commit titles. PEP 8. Follow the conventions of the code you edit.
8. **Respect the protocol.** Never change cache keys, prompts or models in the middle of an
   experiment. A change to the method needs a PROTOCOL.md amendment that Omar approves.
9. **Keep `.left-undone.json` current**: unfinished goals, unverified assumptions and deferred
   architecture, marked done when done.

## Team

### Hierarchy

```
Omar: owner. Approves public actions, protocol amendments, releases and priorities.
└── lead: orchestrator. The only agent that spawns others and merges.
    ├── Authorities: decide in their domain, mostly read-only
    │   ├── architect            technical design, ADRs, cross-area conflicts
    │   ├── research-scientist   scoring and benchmark method, pin sign-off, amendments
    │   └── ux-researcher        user needs, requirements, acceptance, usability measurement
    ├── Builders: write code in their own area only
    │   ├── contracts-steward    schemas, migrations, generated OpenAPI and wire types
    │   ├── backend-engineer     crawler, pipelines, routes, config, NLP, telemetry
    │   ├── llm-engineer         LLM adapters, prompts, LLM ops
    │   ├── design-system-engineer  DESIGN.md, tokens, shared UI, glossary
    │   ├── frontend-engineer    crawler-ui features and refactors
    │   ├── platform-engineer    build, CI, dependencies, packaging
    │   ├── test-engineer        pins, fixtures, load harness, E2E support
    │   └── docs-writer          docs, README, CHANGELOG, FAIR metadata
    ├── Gatekeepers: read-only, veto on their codes
    │   ├── code-reviewer        every change, all codes
    │   ├── security-reviewer    SEC, ETH-1, prompt safety
    │   └── a11y-perf-auditor    A11Y, PERF, HTML-1, CSS-3
    └── Support
        └── chore-runner         one mechanical commit from an exact brief
```

### Decision rights

| Kind of question | Decides |
|---|---|
| Technical design, cross-area conflict | architect, recorded as an ADR |
| Scores, ordering, prompts, statistics | research-scientist, then Omar for method changes |
| Whether a feature is needed and how it behaves | ux-researcher, then Omar for priority |
| Whether a change meets a standard | the gatekeeper for that code; a veto stands until fixed or the architect records an exception |
| Anything public or irreversible | Omar |

### Agents

Definitions live in `.claude/agents/<name>.md`. Write areas live in `.claude/ownership.toml`
and are enforced by `.claude/hooks/guard_paths.py`; shell rules by `guard_bash.py`.

| Agent | Model | Effort | Runs in | Writes |
|---|---|---|---|---|
| lead | opus | xhigh | main checkout (`claude --agent lead`) | `.claude/`, AGENTS.md, CLAUDE.md, `.left-undone.json` |
| architect | opus | xhigh | main checkout, read-only on code | `docs/adr/` |
| research-scientist | opus | xhigh | worktree | `benchmark/` (not results), `docs/research/` |
| ux-researcher | opus | high | main checkout, offline demo | `PRODUCT.md`, `docs/ux/`, `docs/usability-log.md` |
| contracts-steward | opus | high | worktree | contracts, schemas, generated API types and fixtures |
| backend-engineer | sonnet | high | worktree, offline | backend packages and their tests |
| llm-engineer | opus | high | worktree, fake or cached LLM | LLM layer, prompts and their tests |
| design-system-engineer | opus | high | worktree | DESIGN.md, tokens, shared UI, glossary |
| frontend-engineer | sonnet | high | worktree, demo mode | `crawler-ui/src/` outside the design system and API types |
| platform-engineer | sonnet | medium | worktree | Makefile, CI, pyproject, package.json, Docker |
| test-engineer | sonnet | high | worktree | pins, conftest, load harness, E2E support |
| docs-writer | sonnet | medium | worktree | docs, README, CHANGELOG, CITATION, codemeta |
| code-reviewer | opus | high | read-only | nothing |
| security-reviewer | opus | xhigh | read-only | nothing |
| a11y-perf-auditor | sonnet | high | read-only, runs the app | nothing |
| chore-runner | haiku | low | worktree | only the paths in its brief (`CRAWLVIZ_CHORE_PATHS`) |

The `impeccable` skill used by the design and frontend agents is installed per machine
(`.claude/skills/impeccable/`, 18 MB, not committed).

Every agent shares these guardrails, enforced by hooks:
- nobody pushes, rewrites history, skips hooks or changes the git identity
- nobody reads `keys.json` or `.env`
- only the platform-engineer changes dependencies
- only listed agents use the network
- read-only agents cannot change files from the shell
- `benchmark/PROTOCOL.md` and `docs/usability-log.md` are append-only
- builders cannot finish while `make check-changed` fails

## Workflow for a task

1. **Brief.** The lead fills in `.claude/templates/task-brief.md`: goal, requirement or
   finding, owner and area, standards in scope, acceptance criteria, planned commit series,
   pin impact, reviewers.
2. **Build.** The owner works in a worktree as a series of small commits. A bug fix starts
   with its failing test. Before each commit: `make check-changed`, then a review of that
   commit's diff.
3. **Gates, in parallel.**
   - code-reviewer: always
   - security-reviewer: for the API, fetching, LLM calls, keys, prompts or settings
   - a11y-perf-auditor: for the UI
   - research-scientist: for method files (listed in the ownership map) or pins
   - architect: for contracts or cross-area changes
4. **Integrate.** The lead merges the worktree branch into the phase branch, runs `make check`
   and the pins, checks the commit titles and updates `.left-undone.json`.
5. **Publish.** Omar approves each push or PR. The lead runs `.claude/templates/pr-checklist.md`
   first.

### Asking another area

Agents do not edit outside their area. They put this block in their report and the lead
routes it:

```
CHANGE-REQUEST
to: <owner agent>
path: <file or glob>
what: <the change you need>
why: <the finding or requirement, with file:line>
standard: <code>
```

| You need | Ask (through the lead) |
|---|---|
| A change to a file outside your area | that area's owner (see `.claude/ownership.toml`) |
| A new dependency or a CI change | platform-engineer |
| A new or changed API field, message or stored format | contracts-steward; architect for a breaking change |
| Anything that changes scores, ordering or prompts | research-scientist; Omar for a method change |
| A new token, shared component or glossary term | design-system-engineer |
| To know whether a feature is needed and how it should behave | ux-researcher |
| A fixture or pin update | test-engineer, with research-scientist sign-off |
| An exception to a standard | architect, as an ADR |
| Anything public or irreversible | Omar |

## Commit conventions

**Titles.** Follow the existing history, for example `Timeline: empty filter result uses
the shared empty state`.
- Shape: `<Area>: <what is now true or what changed>`.
- The area is the feature or module as a reader knows it, capitalised: `Graph`,
  `Config page`, `Fetch`, `Robots`, `LLM adapters`, `Benchmark analysis`, `CI`, `Docs`.
- The summary starts lowercase (identifiers and acronyms excepted) and has no trailing
  period. Aim for about 72 characters.
- Say the outcome or the concrete change, not the activity. Write
  `Fetch: rate limit holds across workers, per host`, not `Fix stuff` or `Refactor`.
- Title only: no body, no trailers, no AI attribution, no em dashes.
- Never name standards codes, phases, task numbers, "plan", "done" or "WIP" in a title.

| Instead of | Write |
|---|---|
| `SEC-1 done` | `API: every route requires the session token` |
| `Phase D: rename pipelines` | `Fetch: RequestsPipeline becomes FetchStage` |
| `refactor GraphView (ARCH-3)` | `Graph: label placement moves to its own module` |

`commit_msg_check.py` enforces this; `guard_bash.py` checks titles given with `-m`.

**Size and control.**
- One logical change per commit. Moves (`git mv`), formatting-only changes and generated
  files each get their own commit, never mixed with behaviour.
- A bug fix commit holds its failing test and the fix.
- About 200 hand-written changed lines at most per commit, not counting moves, generated
  files and lockfiles; larger needs a reason in the brief.
- Every commit passes `make check-changed` and the pins on its own, so history bisects and
  any commit reverts cleanly.
- A PR is a short series (about ten commits at most) for one requirement or fix group.

**Redesigns land incrementally, never in bulk.**
1. Strangler pattern: build the new piece beside the old one, switch one consumer per
   commit, delete the old piece last.
2. Renames ship an alias or migration first, move callers in small commits, then remove
   the alias.
3. UI migrations go one component or feature at a time, with screenshots and axe each time.
4. Package moves go one domain at a time: a `git mv` commit, then an import-fix commit,
   then any cleanup.
5. Large switches go behind a config flag that defaults to the old path until pins and
   tests agree. Flip the default in one commit; remove the old path in another.

## Invariants

- **Wire contract.** `docs/crawl_messages.ts` is the UI message contract, enforced by
  `tests/test_wire_protocol.py`. Change it only through the contracts-steward.
- **Scoring output format.** The scoring prompt's JSON output format is locked
  (`models/prompts.py`). Prompt edits are method changes.
- **Benchmark records.** `benchmark/PROTOCOL.md` is append-only. Results, analysis and
  `SHA256SUMS` are never edited by hand.
- **Experiments in progress.** LLM cache keys, prompts and model ids do not change while an
  experiment is running.
- **Single-worker sinks.** The crawl log and document archive sinks run with one worker,
  because they write one file in order.
- **Offline doubles.** These exist for tests and agents, so no keys or network are needed:
  - `HashingEmbeddingEngine` (`nlp/embedding_engine.py`)
  - `FixedLlm` (`tests/test_runtime_invariants.py`)
  - `CachedLlm` (`benchmark/llm_cache.py`)
  - `FrozenGraph` (`benchmark/graph.py`)

## Phases

Work is ordered so each phase's findings feed the next. A phase starts only when the
phases it depends on have passed their gates.

| Phase | What it does | Depends on |
|---|---|---|
| A. Setup and safety net | Agent organisation, snapshot tag, behaviour pins, tooling, offline mode, quality baseline | none |
| B. Consumer and design discovery | Context of use, tasks, baseline usability, ranked requirements, ADRs, method review, threat model | A |
| C. Correctness fixes | Security, data loss, politeness, UI and config bugs, then method fixes with approved amendments | B |
| D. Contracts and backend architecture | Import cycles, packages, pipeline naming, versioned contracts, god objects, DRY | C |
| E. Backend capabilities | LLM layer, performance, observability, configurability, feature APIs; ends with API v2 frozen | D |
| F. Frontend | Design system, structure and strict TypeScript, splits, features on API v2, quality pass | E |
| G. Research rerun | Re-recorded graph, statistics, judge, all arms, reproduction package. Runs alongside F. | E |
| H. Docs, FAIR4RS, packaging, release | Docs accuracy, metadata, Docker, release, final usability evaluation | F, G |
