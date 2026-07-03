# crawler-ui

React + Vite frontend for CrawlViz: the live graph view, timeline,
metrics, and the Templates / Run / Validation screens. Plain JS
(no TypeScript) -- see `../docs/crawl_messages.ts` for the WebSocket
message contract this consumes.

## Setup

```bash
npm install
npm run dev      # http://localhost:5173, expects the backend on :8000/:8765
```

See the root `README.md` for running the backend alongside it (`make
dev` from the repo root runs both).

Copy `.env.example` to `.env.local` to point at a non-default backend:

```bash
cp .env.example .env.local
```

## Structure

- `src/App.jsx` — shell, hash router, top-level WebSocket-fed state
- `src/state/` — `reducer.js` (event -> state, also the replay engine),
  `eventNormalizer.js`, `metrics.js`, `constants.js`
- `src/hooks/` — `useCrawlStream` (WebSocket client with backoff
  reconnect), `useDemoMode` (synthetic event generator; not currently
  reachable from the UI, useful for local UI work without a backend)
- `src/components/` — `graph/` (the force-directed view), `timeline/`,
  `metrics/`, `common/`
- `src/pages/` — `TemplateManager`, `RunScreen`, `ValidationView`
- `src/theme/` — design tokens (`tokens.js`, `themes/dark.js`,
  `themes/light.js` -- dark is active) and a shared component style
  factory (`components.js`), used by `components/*`. The three
  `pages/*` and `App.jsx`'s own shell chrome are progressively being
  migrated onto this; `App.jsx` is done, the pages still use local
  inline styles.

## Commands

```bash
npm run dev      # dev server
npm run build    # production build to dist/
npm run lint     # eslint
npm run preview  # preview a production build locally
```
