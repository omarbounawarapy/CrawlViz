# ADR 8: One status board per crawl feeds `/status` and `SUBSYSTEM_STATUS`, and the gateway starts first

Status: proposed, 2026-10-29

## Context

- No subsystem reports its state. `SUBSYSTEM_STATUS` does not exist in the code (grep, 2026-10-29).
- The WebSocket gateway is built after the NLP subsystem (`core/crawler.py:110-116`): the model
  loads and the space is built while nothing listens, so during a normal start the UI shows
  "Waiting for backend", which reads as a failure.
- `/status` (`routes/run.py:105-121`) returns `running`, `llm_calls` and `queues`, nothing else.
  A crawl that raises is logged and dropped (`routes/run.py:62-63`), so neither the API nor the
  UI can say "Failed", and the user never learns what went wrong.
- The UI polls `/status` (`crawler-ui/src/api/client.js:66`) while it also has the stream, so
  two sources can disagree.
- Rate limits, budget exhaustion and fetch backoff are visible only in logs, so a user cannot
  tell a rate-limited crawl from a stalled one, or see how much LLM budget is left.

## Decision

1. **A `StatusBoard` per crawl**, in `crawlviz.telemetry`. The `CrawlController` (ADR 12)
   creates it before the crawl is built and keeps it after the crawl ends, until the next
   crawl starts.
2. **Subsystems are one fixed list**: `embedder`, `space`, `llm`, `fetch`, `robots`, `export`.
   A new one is one entry in that list, the only list of subsystems.
3. **Each entry** is a typed model: `subsystem`, `state`, `reason`, `since`, `retry_at`
   (optional) and `facts`. `state` is one of `off`, `starting`, `ready`, `waiting`, `failed`.
   `reason` is a snake_case code from a closed list per subsystem (`loading_model`,
   `rate_limited`, `budget_exhausted`, `keys_missing`, ...). `facts` is typed per subsystem,
   for example model and device for the embedder, or calls used, budget, tokens in and out,
   cache hits and in-flight calls for the LLM.
4. **Producers report through an injected `StatusReporter`**, a protocol in `crawlviz.events`
   with one method, `report(subsystem, state, reason, facts)`. Stages, the LLM client
   and the NLP build receive it, so no lower layer imports `telemetry` (ADR 4).
5. **One source, two readers.** The telemetry observer sends `SUBSYSTEM_STATUS` on each change,
   coalesced per subsystem at most every `STATUS_COALESCE_MS` (250 ms, a named constant).
   `SNAPSHOT_FULL` carries the whole board. `GET /status` reads the same board.
6. **Copy lives in the UI.** The backend sends codes and facts, never sentences. The UI catalog
   turns `llm` / `waiting` / `rate_limited` with `retry_at` into "LLM rate limited by Groq,
   waiting 40 s. Lower the call rate or add a key." Each message says what happened and what
   to do next. An unknown code shows a generic message with the code.
7. **The gateway starts first.** The crawl starts the gateway, sends `SNAPSHOT_FULL` with the
   board (embedder `starting`, `loading_model`), then builds the NLP subsystem and the stages.
8. **The crawl outcome is recorded.** The controller keeps the crawl state: `idle`,
   `starting`, `running`, `stopping`, then `stopped` (by the user), `finished` with the limit
   reached, or `failed` with an error code. A failure is logged with `crawl_id` and recorded,
   never dropped. `/status` and `CRAWL_STOPPED` carry the same outcome.
9. **No duplicate polling.** While a WebSocket is connected, the UI reads only the stream.
   It reads `/status` on page load and when no crawl stream is connected.

## Alternatives considered

- **Status as bus events consumed by the bridge.** It works for stages but not for the
  embedder load, which runs before the bus has consumers, nor for `/status` after the crawl
  ends. A board can be read at any time.
- **Health derived in the UI from existing messages.** That is how the UI shows "Waiting for
  backend" today: it guesses from silence.
- **Sentences from the backend.** Simpler at first, but user-facing copy belongs in the UI
  catalogs (ADR 11), and a command-line tool can print the code with its own text.

## Consequences

- `SUBSYSTEM_STATUS` is a new wire message, versioned under ADR 5, and `SNAPSHOT_FULL` gains
  `board` and `crawl_state`. The wire golden changes; that pin update goes in its own reviewed
  commit and is not a method change. Producers must not change scheduling: a report is a
  synchronous, non-blocking call that writes to memory.
- The benchmark runner passes a reporter that discards reports, and the pins do not record
  the board.
- The health strip, the crawl end states, the live LLM cost figures and the run mode (ADR 9)
  read this board. Subsystem reporting is complete when all six subsystems report.
- The gateway port is in use for the whole crawl, model load included.

## Standards affected

- Long-running or failure-prone subsystems report their state, and the UI shows it.
- Structured JSON logs carry `crawl_id`.
- No swallowed errors: a failed crawl is logged and shown.
- Every error says what happened and what to do next.
- User-facing copy lives in the UI catalogs.
- Dependencies point one way: producers get an injected reporter instead of importing
  `telemetry`.
- Each list has one source: the subsystem list.
- Wire messages carry a version, with a migration chain.
- No blocking work on the event loop: a report is O(1) and never blocks.

## Migration and commit plan

1. `Telemetry`: `StatusBoard` and `StatusReporter` with unit tests; nothing reports yet.
2. `Crawl`: the controller records the crawl state and outcome, and a failed crawl is
   recorded instead of dropped, starting with a test that fails today.
3. `Crawl`: the gateway starts before the NLP build and sends the board in `SNAPSHOT_FULL`.
4. `Wire`: `SUBSYSTEM_STATUS` message, generated types, pin update reviewed.
5. One commit per subsystem: `embedder`, `space`, `llm`, `fetch`, `robots`, `export` report.
6. `API`: `/status` reads the board, the crawl state and the mode (ADR 9, ADR 12).
7. UI, in the feature series of ADR 10: the health strip reads the board, and `/status`
   polling stops while a stream is connected.
