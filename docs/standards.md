# Standards guide

CLAUDE.md lists the codes in one line each. This page says where each code comes from, gives
an example, and says how it is checked. "Planned" means the automatic check arrives in a later
phase. Until then a reviewer checks it by hand.

Sources:
- Clean-code principles: DRY, KISS, YAGNI, SRP, Boy Scout.
- W3C HTML and CSS validity, and WCAG 2.2.
- Google's Core Web Vitals thresholds.
- ISO 9241-11, 9241-110 and 9241-210.
- Apple's Human Interface Guidelines principles: simplicity, familiarity, agency, hierarchy.
  Liquid Glass and the SF fonts are left out, because they conflict with DESIGN.md and the
  fonts are licensed for Apple platforms only.
- FAIR4RS.

## Architecture

| Code | Example | Checked by |
|---|---|---|
| ARCH-1 | `crawler-ui/src/features/graph/hooks/useZoomBehavior.ts`, not `src/hooks/useZoomBehavior.js` | review; folder layout in ADR 1 |
| ARCH-2 | `import { GraphView } from "../graph"`, not `"../graph/GraphView"` | ESLint `no-restricted-imports` (planned) |
| ARCH-3 | `GraphView.jsx` (990 lines) becomes hooks, pure modules and small components | ESLint `max-lines`, ruff C901/PLR0915 (planned); review |
| ARCH-4 | `useBlueprints()` fetches; `BlueprintList` renders props | lint rule: no `api` imports under `components/` (planned) |
| ARCH-5 | `core/boot_strapper.py` must not import `routes` | import-linter in CI (planned) |
| ARCH-6 | A new priority strategy registers through an entry point and shows up in the schema and UI without editing `crawler.py` | review; registry tests |

## Code

| Code | Example | Checked by |
|---|---|---|
| CODE-1 | One `parse_llm_json()` instead of six copies in the translators | review |
| CODE-2 | `websockets.broadcast` instead of a hand-written send loop; no faiss for a few thousand vectors | review, ADR when a choice is not obvious |
| CODE-3 | A feature exists because a requirement in `docs/ux/requirements.md` names it | review |
| CODE-4 | Unused `VectorSpace` helpers are removed in their own commit | review, ruff unused rules |
| CODE-5 | `except Exception: pass` is never acceptable; a failed robots.txt fetch is logged and fails closed | ruff BLE/S110 (planned), review |

## Naming

| Code | Example | Checked by |
|---|---|---|
| NAME-1 | `def _on_page_fetched(self, event, writer)`, not `def _x(self, e, w)` | ESLint `id-length`, ruff N (planned), review |
| NAME-2 | `DENSITY_RADIUS_DEFAULT = 0.3` in the owning module, not `0.3` in five files | ESLint `no-magic-numbers`, ruff PLR2004 (planned) |
| NAME-3 | `fetchCrawlStatus()` for a GET, `scoreAudit()` for the POST that was named `fetchAuditScore` | review |
| NAME-4 | The UI says "blueprint" and so do the API, the errors and the glossary | review against `docs/glossary.md` |
| NAME-5 | `RequestsPipeline` becomes `FetchStage`, with config key `fetch`, wire stage `fetch` and UI label "Fetch" | review; registry test |

## Language

| Code | Example | Checked by |
|---|---|---|
| PY-1 | `def score_links(self, links: list[Link]) -> list[ScoredLink]:` | ruff, mypy `--strict`, ratcheted per module (planned) |
| TS-1 | `interface GraphControlsProps { query: string; onQueryChange(next: string): void }` | `tsc --noEmit`, typescript-eslint strict (planned) |

## Markup and styling

| Code | Example | Checked by |
|---|---|---|
| HTML-1 | Shell navigation is `<a href="#/run" aria-current="page">`, not a `<button>` | html-validate, axe, jsx-a11y (planned) |
| CSS-1 | `color: var(--color-ink)`, not `color: "#0f1b2d"` | Stylelint colour rule; token build (planned) |
| CSS-2 | `GraphControls.module.css` beside `GraphControls.tsx`; `margin-inline-start`, not `marginLeft` | Stylelint (planned), review |
| CSS-3 | The graph canvas has a fixed `aspect-ratio`; the inspector panel uses `contain: layout paint` | Lighthouse CLS (planned) |

## Accessibility and performance

| Code | Example | Checked by |
|---|---|---|
| A11Y-1 | Graph marks reach 3:1 against the paper in both themes | token contrast check, axe |
| A11Y-2 | At 360px the timeline controls move into an overflow menu instead of `display: none` | Playwright at 360px and 400% zoom (planned), axe |
| PERF-1 | Graph search stays under 200 ms INP at 3000 nodes | Playwright with web-vitals, Lighthouse CI (planned) |
| PERF-2 | The timeline event list is windowed; graph search uses `useDeferredValue` | review, perf tests |
| PERF-3 | Link features are one matrix product per page, not a Python loop over the space | load harness budget (planned), review |

## Testing

| Code | Example | Checked by |
|---|---|---|
| TEST-1 | The rate-limit race fix lands with a test that fails on the old code | review |
| TEST-2 | A refactor commit leaves `tests/pins/` golden files byte-identical | `pytest -m pins` (planned) |
| TEST-3 | New hooks and models get unit tests; "start a crawl" has an E2E test | coverage ratchet in CI (planned) |

## Security and ethics

| Code | Example | Checked by |
|---|---|---|
| SEC-1 | A cross-origin `POST /stop` from another site is rejected | security tests, security-reviewer |
| SEC-2 | A seed that redirects to `169.254.169.254` is blocked | security tests, security-reviewer |
| SEC-3 | Manifests show `Authorization: [redacted]` | tests, security-reviewer |
| ETH-1 | Four workers still send at most one request per `min_delay` to a host | politeness tests |

## LLM and observability

| Code | Example | Checked by |
|---|---|---|
| LLM-1 | `LlmResponse.parsed` is a validated `ScoredLinks` model, or the call is retried once with the error | tests, review |
| LLM-2 | `prompts/scoring.md` front matter carries `id` and `version`; the manifest records `{"scoring": "<sha>"}` | golden render and replay tests (planned) |
| LLM-3 | `/status` shows tokens in and out, cost and malformed-answer rate for the run | tests |
| OBS-1 | Every log line is JSON with `crawl_id` | tests on the log formatter |
| OBS-2 | The health strip shows "Embedding model: loading (cpu)" during a cold start | E2E (planned) |

## Contracts

| Code | Example | Checked by |
|---|---|---|
| CONTRACT-1 | A settings file from the previous version loads and migrates | migration tests |
| CONTRACT-2 | `crawler-ui/src/shared/api/openapi.ts` is regenerated, and CI fails if it is stale | drift check in CI (planned) |

## User experience

| Code | Example | Checked by |
|---|---|---|
| UX-1 | "The blueprint 'isi' was not found. Pick one from the list or create it." instead of a raw 404 | review, ux-researcher heuristic review |
| UX-2 | Deleting a preset shows an undo toast | E2E, review |
| UX-3 | Each phase adds an entry to `docs/usability-log.md` | ux-researcher |
| I18N-1 | `formatCount(1234)` gives "1,234" in en and "1 234" in fr | unit tests |

## Research and FAIR4RS

| Code | Example | Checked by |
|---|---|---|
| REPRO-1 | The manifest records the MiniLM revision hash and the torch version | manifest tests |
| FAIR-1 | The version in `CITATION.cff` matches `pyproject.toml` | CI sync check (planned) |
| DOC-1 | The README quickstart includes the model download step, and it was run | review |

## Git

| Code | Example | Checked by |
|---|---|---|
| GIT-1 | Author and committer are Omar; no trailers | `guard_bash.py`, review |
| GIT-2 | `Robots: a 5xx robots.txt blocks the host until it recovers` | `commit_msg_check.py` |
| GIT-3 | The pipeline rename is a series: add aliases, move each stage, remove aliases | review, commit size check |
