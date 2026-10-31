# ADR 10: UI features own their containers, components and model; one crawl session store serves live and replay

Status: proposed, 2026-10-30

## Context

- The UI is JavaScript: `tsconfig.json` is strict, but `allowJs` is on, `checkJs` is off, and
  the code is `.js` and `.jsx`.
- Components over the 250-line component limit, `wc -l` on 2026-10-29:
  `features/graph/GraphView.jsx` 1389, `features/blueprints/BlueprintManager.jsx` 1161,
  `features/config/ConfigPage.jsx` 511, `SettingsEditor.jsx` 495, `NodeInspector.jsx` 451,
  `RunsTab.jsx` 429, `FieldControl.jsx` 428, `Landing.jsx` 428, `TimelinePage.jsx` 405,
  `DataExplorer.jsx` 404, `App.jsx` 369.
- 17 feature files and `App.jsx` import `api/client.js` directly. 16 of those feature files
  also call `useEffect`, the pattern of fetching inside the component, where data and side
  effects belong in a container hook. The client is hand-written and untyped, and its names do
  not follow a verb rule (`fetchX` reads, `createX`, `updateX` and `deleteX` write, `startX`
  and `stopX` control): `fetchAuditScore` is a POST, `crawlStatus` and `benchmarkJob` have no
  verb.
- Shared code is grouped by type: `src/hooks/`, `src/state/` (the crawl reducer, 381 lines),
  `src/utils/`, `src/theme/`, `src/api/`.
- Opening a past run in the graph, and explaining a score on it, need a replayed run to behave
  exactly like a live one. Today only the live stream feeds the reducer.

## Decision

1. **Feature layout** (ADR 1). Inside `features/<feature>/`:
   - `index.ts`: the only import path for other features and `app/`.
   - `components/`: presentational `.tsx` with explicit prop interfaces and a CSS Module
     beside each. They take props, and never import `shared/api` or another feature's hooks.
   - `hooks/`: containers that own data and side effects.
   - `model/`: pure logic (reducers, selectors, layout maths) with unit tests.
   - `api.ts`: the feature's calls through the shared client, named by the verb rule above.
   - `messages.ts`: the feature's copy catalog (ADR 11).
2. **Server data through two shared hooks**, `useApiResource` (load, error, refetch, abort on
   unmount) and `useApiMutation`, in `shared/api/`. They replace the hand-written `useEffect`
   fetches. No data-fetching library for now: two small hooks are the simplest design that
   meets the need. A later ADR adds one if features need shared caching or invalidation.
3. **One crawl session store.** The `crawl-session` feature owns the reducer, the message
   normaliser, the stream hook and the batched dispatch, which today are in `state/` and
   `hooks/`. It also loads a recorded run from the runs API (ADR 12) and feeds it to the same
   reducer. Graph, inspector, timeline, pipeline monitor and health strip read it through
   selector hooks (`useCrawlNodes()`, `useCrawlState()`, `useStatusBoard()`), with expensive
   selectors memoised. It uses React context and `useReducer`, as today. If load and
   interaction measurements on a large graph show re-render cost, the context is split by
   slice before any state library is considered.
4. **TypeScript per feature**, strict and with no `any`. A feature is converted to `.ts` and
   `.tsx` when its series starts. Types come from the generated `openapi.ts` and `wire.ts`
   (ADR 5), never written by hand. ESLint rejects new `.js` or `.jsx` files under `src/`.
   `allowJs` is removed after the last feature.
5. **Boundaries in ESLint**, for the import rules of ADR 1 and ADR 4 and the container rule
   above: `no-restricted-imports` for paths inside another feature and for `shared/api` under
   `components/`; `import/no-cycle`; `max-lines` 250 for components; `shared/` may not import
   `features/` or `app/`.
6. **Routing stays hash-based** (`useRoute`, `#/run`). It works with the dev server and any
   static host without a router library.
7. **New features for the user requirements listed in ADR 12:** `health` (subsystem health,
   live LLM cost and the run mode) and `runs` (past runs and replay). The rest change existing
   features: `inspector` (why a page got its score, why a link was skipped), `pipeline` and
   the shell header (states and counts that match the backend), and `data` (export). Scores
   are shown only through `shared/lib/format.ts`, on the one display scale of ADR 12.
8. **The design system** lives in `shared/ui/`. `theme/components.js` moves there, and
   colours, spacing and type come from design tokens.

## Alternatives considered

- **Redux Toolkit or Zustand for the crawl store.** The reducer already exists and is tested
  (`state/reducer.test.js`); a library would rewrite it and add a dependency with no
  requirement asking for it.
- **TanStack Query.** It removes the hand-written fetches, as the shared hook does, and adds
  caching that no current requirement needs.
- **Convert the whole UI to TypeScript first.** A bulk change that cannot be reviewed feature
  by feature, and the types would be hand-written before ADR 5 generates them.
- **React Router.** Hash routes cover the six pages, and links are real `a` elements already.

## Consequences

- Each feature series is reviewable alone, with screenshots and an axe accessibility check
  each time.
- The reducer becomes the one consumer of the wire protocol, so a protocol bump (ADR 5) touches
  one feature.
- Until a feature is converted, the boundary rules apply to it as warnings with a baseline that
  only shrinks, the same way the Python baselines work.
- `GraphView.jsx` and `BlueprintManager.jsx` are split in their own series, with the split
  agreed before the code moves.

## Standards affected

- Code is grouped by feature, and other features are used only through their `index.ts`.
- Size limits: a component at most 250 lines.
- Containers (hooks) own data and side effects; presentational components take props and never
  import the API client.
- Dependencies point one way: `app`, then features, then `shared`, with no cycles.
- Strict TypeScript with no `any`, and API types generated.
- Colour, spacing and type come from design tokens; CSS Modules sit beside each component.
- Performance: load and interaction stay fast on a large graph, and expensive derivations are
  memoised.
- REST client functions are named by the verb rule above.
- Real `a` and `button` elements, not clickable `div`s.
- The simplest design that meets the need.
- Small commits, each green on its own; redesigns land one feature at a time.

## Migration and commit plan

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
