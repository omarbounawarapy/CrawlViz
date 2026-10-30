# ADR 10: UI features own their containers, components and model; one crawl session store serves live and replay

Status: proposed, 2026-10-30

## Context

- The UI is JavaScript: `tsconfig.json` is strict, but `allowJs` is on, `checkJs` is off, and
  the code is `.js` and `.jsx`.
- Components over the 250-line limit (ARCH-3), `wc -l` on 2026-10-29:
  `features/graph/GraphView.jsx` 1389, `features/blueprints/BlueprintManager.jsx` 1161,
  `features/config/ConfigPage.jsx` 511, `SettingsEditor.jsx` 495, `NodeInspector.jsx` 451,
  `RunsTab.jsx` 429, `FieldControl.jsx` 428, `Landing.jsx` 428, `TimelinePage.jsx` 405,
  `DataExplorer.jsx` 404, `App.jsx` 369.
- 17 feature files and `App.jsx` import `api/client.js` directly. 16 of those feature files
  also call `useEffect`, the pattern of fetching inside the component (ARCH-4). The client is hand-written and untyped; its names break
  NAME-3 (`fetchAuditScore` is a POST, `crawlStatus` and `benchmarkJob` have no verb).
- Shared code is grouped by type: `src/hooks/`, `src/state/` (the crawl reducer, 381 lines),
  `src/utils/`, `src/theme/`, `src/api/`.
- R-RUNS acceptance 2 and R-WHY acceptance 6 need a replayed run to behave exactly like a live
  one. Today only the live stream feeds the reducer.

## Decision

1. **Feature layout** (ADR 1). Inside `features/<feature>/`:
   - `index.ts`: the only import path for other features and `app/`.
   - `components/`: presentational `.tsx` with explicit prop interfaces and a CSS Module
     beside each. They take props, and never import `shared/api` or another feature's hooks.
   - `hooks/`: containers that own data and side effects.
   - `model/`: pure logic (reducers, selectors, layout maths) with unit tests.
   - `api.ts`: the feature's calls through the shared client, named by NAME-3.
   - `messages.ts`: the feature's copy catalog (ADR 11).
2. **Server data through two shared hooks**, `useApiResource` (load, error, refetch, abort on
   unmount) and `useApiMutation`, in `shared/api/`. They replace the hand-written `useEffect`
   fetches. No data-fetching library for now (CODE-2). A later ADR adds one if
   features need shared caching or invalidation.
3. **One crawl session store.** The `crawl-session` feature owns the reducer, the message
   normaliser, the stream hook and the batched dispatch, which today are in `state/` and
   `hooks/`. It also loads a recorded run from the runs API (ADR 12) and feeds it to the same
   reducer. Graph, inspector, timeline, pipeline monitor and health strip read it through
   selector hooks (`useCrawlNodes()`, `useCrawlState()`, `useStatusBoard()`), with expensive
   selectors memoised (PERF-2). It uses React context and `useReducer`, as today. If PERF-1
   measurements show re-render cost, the context is split by slice before any state library
   is considered.
4. **TypeScript per feature** (TS-1). A feature is converted to `.ts` and `.tsx` when its
   series starts. Types come from the generated `openapi.ts` and `wire.ts` (ADR 5), never
   written by hand. ESLint rejects new `.js` or `.jsx` files under `src/`. `allowJs` is removed
   after the last feature.
5. **Boundaries in ESLint** (ARCH-2, ARCH-4, ARCH-5): `no-restricted-imports` for paths inside
   another feature and for `shared/api` under `components/`; `import/no-cycle`; `max-lines`
   250 for components; `shared/` may not import `features/` or `app/`.
6. **Routing stays hash-based** (`useRoute`, `#/run`). It works with the dev server and any
   static host without a router library.
7. **New features for the ranked requirements:** `health` (R-HEALTH, R-COST-LIVE, R-MODE),
   `runs` (R-RUNS). The rest change existing features: `inspector` (R-WHY, R-SKIP-REASON),
   `pipeline` and the shell header (R-STATE-TRUTH), and `data` (R-EXPORT). Scores are shown
   only through `shared/lib/format.ts` (R-SCALE, ADR 12).
8. **The design system** lives in `shared/ui/` (design-system-engineer). `theme/components.js`
   moves there, and colours, spacing and type come from tokens (CSS-1).

## Alternatives considered

- **Redux Toolkit or Zustand for the crawl store.** The reducer already exists and is tested
  (`state/reducer.test.js`); a library would rewrite it and add a dependency with no
  requirement asking for it.
- **TanStack Query.** It removes the hand-written fetches, as the shared hook does, and adds
  caching that no current requirement needs.
- **Convert the whole UI to TypeScript first.** A bulk change with no review per feature
  (GIT-3), and the types would be hand-written before ADR 5 generates them.
- **React Router.** Hash routes cover the six pages, and links are real `a` elements already
  (HTML-1).

## Consequences

- Each feature series is reviewable alone, with screenshots and axe each time (AGENTS.md,
  redesigns).
- The reducer becomes the one consumer of the wire protocol, so a protocol bump (ADR 5) touches
  one feature.
- Until a feature is converted, the boundary rules apply to it as warnings with a baseline that
  only shrinks, the same way the Python baselines work.
- `GraphView.jsx` and `BlueprintManager.jsx` are split in their own series. The frontend-engineer
  proposes the split in the brief, and the architect checks it.

## Standards affected

ARCH-1 to ARCH-5, TS-1, CSS-1, CSS-2, PERF-1, PERF-2, NAME-3, HTML-1, CODE-2, GIT-3.

## Migration and commit plan

Phase F; frontend-engineer, design-system-engineer for `shared/ui/`, platform-engineer for
lint rules.

1. `UI API`: typed `shared/api/http.ts` and the two hooks; `api/client.js` re-exports through
   them.
2. `UI lint`: boundary and size rules, as warnings with a baseline.
3. `Crawl session`: `state/` and the stream hooks move into the feature (a `git mv` commit,
   then an import fix), then it is converted to TypeScript.
4. `Crawl session`: a recorded run loads through the same reducer.
5. One feature per series, in requirement order: `inspector`, `health` (new), `pipeline` and
   header, `runs` (new), `data`, then `graph`, `timeline`, `config`, `blueprints`, `benchmark`
   and `landing`. Each series: move and `index.ts`, TypeScript, container and component split,
   CSS Modules.
6. `UI`: `api/client.js`, `hooks/`, `state/` and `utils/` are deleted once empty, and the lint
   rules become errors.
