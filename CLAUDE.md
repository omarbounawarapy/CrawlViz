# CrawlViz

Topic-focused web crawler with a live graph UI. Python backend at the repo root (moving to
`src/crawlviz/`), React UI in `crawler-ui/`, benchmark in `benchmark/`.

@AGENTS.md

## Standards

Every change meets these. Reviews and task briefs cite the codes; commit titles never do.
Examples and the way each one is checked are in `docs/standards.md`.

| Code | Rule |
|---|---|
| ARCH-1 | Group by feature or domain (`src/crawlviz/<domain>/`, `crawler-ui/src/features/<f>/`), not by file type. |
| ARCH-2 | Other areas use a feature only through its public `index.ts` or `__init__.py`; no deep imports. |
| ARCH-3 | Component at most 250 lines, module 400, function 50, complexity 10. Split by responsibility. |
| ARCH-4 | Containers (hooks, services) own data and side effects; presentational components take props and never import `api`. |
| ARCH-5 | Dependencies point one way: app, api, features or domains, shared. No cycles; no lazy imports to dodge one. |
| ARCH-6 | Extend through registries or entry points. Each list (strategies, transforms, profiles, providers, stages) has one source. |
| CODE-1 | DRY: no logic in two places. |
| CODE-2 | KISS: simplest design that meets the need; a library when it removes real code. |
| CODE-3 | YAGNI: build what a requirement or ADR asks for. |
| CODE-4 | Boy Scout: leave touched files cleaner; delete dead code in its own commit. |
| CODE-5 | No swallowed errors: log with context, then re-raise or surface to the user. |
| NAME-1 | Names say why a thing exists and what it does. No cryptic abbreviations; single letters only for loop indices and d3 datums. |
| NAME-2 | No magic numbers: named constants in the owning module, or config fields. |
| NAME-3 | `get_` in memory, `load_`/`save_` disk, `fetch_` network. REST client: `fetchX`, `createX`, `updateX`, `deleteX`, `startX`/`stopX`. |
| NAME-4 | Domain terms come from `docs/glossary.md` ("blueprint", "seed page" vs "random seed"). |
| NAME-5 | Pipeline parts: `<Verb>Stage`, `<Noun>Sink`, `<Noun>Observer`, `<Noun>Controller`; one snake_case key for module, config, wire and UI; events `<Stage><Subject?><PastVerb>Event`, failures `<Stage>FailedEvent`. |
| PY-1 | `mypy --strict` and ruff clean, PEP 8, full type hints; `Any` only at JSON boundaries with a comment. |
| TS-1 | TypeScript `strict` and `noUncheckedIndexedAccess`; no `any`; explicit prop interfaces; API types generated. |
| HTML-1 | Semantic landmarks, one `h1` per route, real `a`/`button`/`form`/`fieldset`, W3C valid. |
| CSS-1 | Colour, spacing, type and radius only from tokens generated from DESIGN.md. |
| CSS-2 | CSS Modules beside the component, nesting at most one level, logical properties, `rem` type; inline style only for data-driven values. |
| CSS-3 | Explicit size or `aspect-ratio` on media and canvas; `contain` on independent panels. |
| A11Y-1 | WCAG 2.2 AA. Contrast 4.5:1 text, 3:1 UI and graph marks, both themes. Targets at least 24px, 44px for primary and coarse-pointer controls. |
| A11Y-2 | Keyboard operable with visible focus; reduced motion honoured; nothing hidden at 400% zoom or 360px. |
| PERF-1 | LCP at most 2.5 s, INP at most 200 ms, CLS under 0.1 on the 3000-node fixture; bundle budget held. |
| PERF-2 | Lists over 200 items virtualised; search inputs deferred or debounced; expensive derivations memoised. |
| PERF-3 | Backend: no blocking work on the event loop; hot paths vectorised or batched; nothing O(n²) per page or event without an ADR. |
| TEST-1 | A bug fix starts with a test that fails before the fix. |
| TEST-2 | Behaviour pins pass unchanged; an update needs `--update-pins`, a reason and research-scientist sign-off. |
| TEST-3 | Coverage only goes up; new logic has unit tests; core user tasks have E2E tests. |
| SEC-1 | Token on every route; Host and Origin checked; JSON content type enforced; WebSocket origins allowlisted. |
| SEC-2 | Untrusted input bounded: SSRF and redirect checks, size caps, path sanitising, regex input caps, prompt data delimited. |
| SEC-3 | Secrets never reach logs, manifests, traces or UI; `keys.json` mode 0600. |
| ETH-1 | robots.txt (5xx fails closed), Crawl-delay, per-host rate limit, Retry-After, honest User-Agent with contact, safe default limits. |
| LLM-1 | LLM calls go through `LlmClient` with typed request and response; output validated with pydantic, one repair attempt. |
| LLM-2 | Prompts in `prompts/<id>.md` with front matter; rendered-prompt hashes in every manifest; prompt changes run the golden replay. |
| LLM-3 | Every call records tokens, cost, latency, attempts, cache hit and outcome. |
| OBS-1 | Structured JSON logs with `crawl_id`, `node_id`, `trace_id`. |
| OBS-2 | Long-running or failure-prone subsystems report state in `SUBSYSTEM_STATUS`, and the UI shows it. |
| CONTRACT-1 | Stored files and wire messages carry `schema_version` or `protocol` with a migration chain; config models forbid unknown keys. |
| CONTRACT-2 | REST endpoints declare `response_model`; OpenAPI, wire and config-fixture types are generated; CI fails on drift. |
| UX-1 | ISO 9241-110: task-fitting, self-describing copy; every error says what happened and what to do next; no raw errors shown. |
| UX-2 | HIG principles: undo for destructive actions, `ConfirmButton` for confirmations, hierarchy, progressive disclosure, familiarity. |
| UX-3 | ISO 9241-210/11: changes trace to `docs/ux/requirements.md`; usability goals re-measured each phase. |
| I18N-1 | All formatting through `shared/lib/format.ts` (Intl); user-facing strings in per-feature catalogs. |
| REPRO-1 | Seeds, model revisions, prompt hashes, weights, versions, hardware and footprint in the manifest; PROTOCOL.md append-only. |
| FAIR-1 | CITATION.cff, codemeta.json, semver releases, data cards and licences kept in sync. |
| DOC-1 | Docs change in the same PR as the behaviour; every documented command has been run. |
| GIT-1 | Omar is the only author; title-only messages; no AI attribution; no amend, rebase or force-push after review; public actions need his approval each time. |
| GIT-2 | Titles follow `<Area>: <what is now true or what changed>` (AGENTS.md, Commit conventions); no standards codes, phases, task numbers or "done". |
| GIT-3 | Small controlled commits: one logical change each, green on its own; redesigns land incrementally, never as one bulk change. |
