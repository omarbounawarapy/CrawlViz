# ADR 9: The UI reads its runtime settings and the run mode from one `/ui-config` endpoint

Status: proposed, 2026-10-30

## Context

- The UI hard-codes the crawl WebSocket address in two places: `ws://localhost:8765` in
  `crawler-ui/src/App.jsx:27` (`VITE_WS_URL` fallback) and in
  `crawler-ui/src/hooks/useCrawlStream.js:4`. The backend's `observability.ui_port` setting
  (`config/runtime_config.py:747`) moves the gateway (`core/crawler.py:69`, `:330`), but the UI
  keeps connecting to 8765, so with any other `ui_port` the UI cannot reach the crawl stream.
- Everything the UI knows about the backend is fixed at build time through Vite variables
  (`VITE_API_BASE_URL`, `VITE_WS_URL`, `VITE_API_TOKEN`, `crawler-ui/src/api/client.js:1`, `:26`),
  so one build cannot serve a backend on another port or in Docker.
- Nothing tells the UI the run mode. Offline mode is an environment variable read inside the run
  route (`offline/session.py:12-18`, `routes/run.py:42-52`), the manifest records the model but
  not the mode (`core/crawler.py:310-321`), and the Run page shows provider fields that offline
  mode ignores. A user cannot tell whether a crawl, or a benchmark arm, calls a live provider
  and spends its cap.
- The UI also has a synthetic demo (`crawler-ui/src/hooks/useDemoMode.js`) that never calls the
  backend.

## Decision

1. **`GET /api/v2/ui-config`** returns what the UI needs before its first other call. The
   values are fixed for the life of the backend process:
   - `app_version` (the package version) and `protocol` (the wire protocol, ADR 5). If
     `protocol` differs from the one the UI was generated for, the UI says to reload and does
     not open the stream.
   - `crawl_stream_url`: the WebSocket URL built from the configured host and port. The UI
     connects only to this URL.
   - `mode`: the process run mode and, for live, the provider and model the stored settings
     would call.
   - `score_scales`: the display scale for each score kind (ADR 12), so the UI applies the
     backend's one definition instead of its own.
   Later features add fields (for example the safe default limits that a warning before the
   start compares against). Adding a field does not change the version (ADR 5).
2. **The run mode is resolved in one function.** `resolve_run_mode()` in `crawlviz.crawl`
   returns `RunModeInfo {mode, provider, model, calls_network}`, with `mode` one of `offline`,
   `cached` or `live`. These read it and nothing else decides the mode:
   - `/ui-config` (process default);
   - `POST /config/effective`, for a chosen blueprint and its overrides, so the Run page can
     show the mode, provider and model before the start, and mark provider fields that
     offline mode does not use;
   - the crawl start, which uses it to choose the LLM and fetcher, offline doubles included;
   - `/status`, `SNAPSHOT_FULL` and the run manifest, for the running or recorded crawl, so a
     recorded run says how it ran.
   `CRAWLVIZ_OFFLINE=1` stays an environment variable. It is a safety switch for tests and
   development without keys, not a user setting.
3. **One build-time value is left.** `VITE_API_BASE_URL` stays, because the UI needs it to find
   the backend. `VITE_WS_URL` is removed. `VITE_API_TOKEN` stays until the separate fix that
   requires the token on every route decides how the token reaches the browser. This ADR does
   not decide that.
4. **`/ui-config` requires the token** like every route. It returns no secrets: no keys, no
   token, no filesystem paths.
5. **The UI demo is not a backend mode.** The synthetic demo stays a UI-only feature and is
   labelled as a sample by the UI. It is not `offline`, which runs the real crawler with
   doubles.

## Alternatives considered

- **Mode on `/status` only.** `/status` describes the current crawl and changes every second;
  the Run page needs the mode before any crawl, and the stream URL is needed before the stream.
  `/status` still carries the running crawl's mode.
- **Keep Vite variables and fix `ui_port` by documenting it.** It leaves two sources for one
  port and a build per deployment.
- **Serve the values in `index.html`.** Only works when the backend serves the built UI, which
  `make dev` does not.

## Consequences

- The UI makes one call at start-up before it renders backend data. Until the call answers,
  the shell shows a "Connecting" state, and a failure shows what happened and what to do.
- `ui_port` works as its description says. The Config page copy for it stays true.
- Benchmark arms state whether they call the network from the arm registry (ADR 7), through
  the benchmark API (ADR 12), not through `/ui-config`. The benchmark form needs this per arm.
- The manifest gains a `mode` block, a versioned change under ADR 5.

## Standards affected

- No logic in two places: one source for the mode and one for the stream URL.
- REST endpoints declare their response model, and the UI types are generated from it.
- Every route requires the session token.
- Secrets never reach the UI.
- Every error says what happened and what to do next.
- Subsystems report their state, and the UI shows it.
- The manifest records what is needed to reproduce a run; the mode is now part of it.

## Migration and commit plan

1. `Crawl`: `resolve_run_mode()` with unit tests. The run route calls it instead of reading the
   environment.
2. `Runs`: the manifest records the mode.
3. `API`: `GET /api/v2/ui-config` with its `response_model`.
4. `API`: `POST /config/effective`, `/status` and `SNAPSHOT_FULL` carry the mode (wire change
   through ADR 5).
5. UI, in the feature series of ADR 10: the app reads `/ui-config` at start-up and connects
   to `crawl_stream_url`; `VITE_WS_URL` and the hard-coded URLs are removed, in one commit.
