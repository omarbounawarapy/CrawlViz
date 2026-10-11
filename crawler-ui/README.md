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

- `src/App.jsx`: shell, hash router, top-level WebSocket-fed state
- `src/state/`: `reducer.js` (event to state, and the replay engine), `eventNormalizer.js`, `metrics.js`, `constants.js`
- `src/hooks/`: `useCrawlStream` (WebSocket client with backoff reconnect) and `useDemoMode` (synthetic event generator, started by the "Load a sample replay" link on the landing page or the "Load a synthetic sample" button on the empty canvas)
- `src/app/Shell.jsx`: the page shell and navigation
- `src/features/`: one folder per screen: `graph/` (radial tree view), `timeline/` (replay scrubber), `inspector/`, `pipeline/`, `overview/`, `run/`, `blueprints/` (`BlueprintManager`), `data/`, `config/`, `landing/`, `loading/`
- `src/api/client.js`: REST client for the backend
- `src/theme/`: design tokens (`tokens.js`, `themes/dark.js`, `themes/light.js`; dark is active) and a shared component style factory (`components.js`) used by the feature screens. `App.jsx`'s shell chrome uses the factory. The feature screens still use local inline styles.

## Commands

```bash
npm run dev      # dev server
npm run build    # production build to dist/
npm run lint     # eslint
npm run preview  # preview a production build locally
```
