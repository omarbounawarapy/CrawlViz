# Execution Walkthrough

This traces one concrete path through CrawlViz: from `POST /run` to a single discovered link becoming a scored, prioritized child node. Every step names the actual class and event type involved, so it can be checked against the source directly.

## 0. Starting a crawl

```mermaid
sequenceDiagram
    participant User
    participant RunAPI as routes/run.py
    participant Crawler as core.Crawler
    participant Boot as BootStrapper
    participant Broker as EventBroker
    participant GW as UIWebSocketGateway

    User->>RunAPI: POST /run {template: "wikiMD"}
    RunAPI->>Crawler: Crawler(blueprint).start()
    Crawler->>Boot: bootstrap()
    Boot->>Boot: parse blueprint, validate against schema
    Boot->>Boot: create Domain objects, seed Node objects (priority=0.01 default)
    Boot-->>Crawler: storage pre-seeded
    Crawler->>Broker: construct + wire ~13 pipelines (subscribe calls)
    Crawler->>GW: start WebSocket server on :8765 (per-crawl)
    Crawler->>Broker: emit NodeAddedEvent for each seed
    RunAPI-->>User: 202, crawl running
```

The control API returns as soon as the crawl task is launched. It does not wait for the crawl to finish. From here on, everything is driven by events; there is no central loop iterating "for each node, do X."

## 1. A seed node enters the frontier

`NodeAddedEvent` for a seed node reaches two independent subscribers at once:

- **`RequestsPipeline`** enqueues it for fetching.
- **`ScoringPipeline`** enqueues it too, but immediately `await`s `node.ready`, a per-node `asyncio.Future` that isn't resolved yet. This is deliberate: the scoring pipeline is allowed to *claim* a node the instant it exists, but it physically cannot start scoring it until the node has content and extracted links. See [§ The `node.ready` synchronization gate](03-deep-dive-event-pipeline.md#the-node-ready-synchronization-gate) for why this matters more than it sounds like it should.

## 2. Fetch, extract, filter, transform

```mermaid
sequenceDiagram
    participant Req as RequestsPipeline
    participant Net as NetworkClient
    participant Broker as EventBroker
    participant Proc as ProcessingPipeline
    participant Filt as FilteringPipeline
    participant Trans as TransformationPipeline
    participant Store as StoragePipeline
    participant Export as ExportingPipeline

    Req->>Net: GET page (rate-limited, 1 req/s/worker)
    Net-->>Req: 200 OK, HTML
    Req->>Broker: emit PageFetchedEvent(node, html)
    Broker->>Proc: dispatch
    Proc->>Proc: run XPath/CSS selectors from blueprint<br/>extract candidate links + raw item fields
    Proc->>Broker: emit ContentExtractedEvent(links, items)
    Broker->>Filt: dispatch
    Filt->>Filt: hash-based dedup against Storage seen-link<br/>and seen-item-content sets
    Filt->>Broker: emit ContentFilteredEvent(accepted_links, accepted_items)
    Broker->>Trans: dispatch
    Trans->>Trans: apply blueprint transform chain to items<br/>strip, lowercase, custom functions...
    Trans->>Broker: emit TransformationCompletedEvent(node, links, transformed_items)
    Broker->>Store: dispatch
    Store->>Store: node.set_links(links) node.update_state()<br/>this resolves node.ready
    Broker->>Export: dispatch (independently, same event)
    Export->>Export: buffer transformed_items for SQLite write
```

Two things worth being precise about here, because a casual reading of the report's five-state node lifecycle ([§2.7.2 — States in a Node's Lifecycle](../report/rapport-english.pdf#page=19), `CREATED → FETCHED → FILTERED → SCORED → EXPANDED`) would miss them:

- **There's an unlabeled sixth stage.** The `LoggingPipeline` emits a `TRANSFORMED` log line between `FILTERED` and `SCORED` (`pipelines/logging_pipeline.py`), corresponding to `TransformationCompletedEvent`. It isn't one of the report's five named lifecycle states, but it is a distinct, separately logged step in the actual pipeline.
- **The scoring gate is transformation-complete, not filtering-complete.** `node.ready` is resolved by `StoragePipeline._on_transformation_completed`, which fires only after *both* the filtered links are known *and* the item transformation chain has finished. A node whose extracted items are slow to transform (e.g., a long transform chain) delays scoring for that node's links too, even though link scoring conceptually has nothing to do with item transformation. This is a real coupling in the current implementation, not an inference.

## 3. Scoring: the cascade

`ScoringPipeline`'s worker, having been unblocked by `node.ready`, now has a `Node` with a list of candidate `Link` objects. For each link:

1. **NLP pass (always, local, no network):** `NLPService.score_link()` builds a feature vector (target similarity, novelty, coverage, lexical overlap, and other signals; [full list in the deep dive](04-deep-dive-semantic-scoring.md)) and reduces it to a single composite `_nlp_score` used only for bucketing.
2. **Bucketing:** every link in the node is sorted into `low` / `mid` / `high` against two configurable thresholds. `mid` always goes to the LLM. `low` and `high` are each *sampled*: a small random slice from `low` (to avoid the crawl converging on one semantic neighborhood) and a top-K-plus-random slice from `high` (to spend LLM budget confirming the crawler's most confident guesses, not just its uncertain ones). Everything not sampled is either dropped (`low`) or fast-tracked without an LLM call (`high`, tagged `trusted_no_llm`).
3. **LLM pass (selective, budgeted):** the sampled links are batched into one prompt (`ScoringPromptBuilder`, strategy-selected, e.g. `TOPICAL`), sent through `LlmHandler` → `KeyManager` (picks a non-cooling-down API key) → `NetworkClient` (the actual HTTP call, with its own retry/backoff independent of the crawl-level `RetryProcessor`) → `OpenRouterTranslator` (parses the response) → `ResultMapper` (attaches `score`, `relevance_type`, and `expansions` back onto each `Link`).

`ScoringPipeline` emits `LinksScoredEvent` for LLM-scored links and `HighScoreLinksEvent` for the `trusted_no_llm` fast-tracked ones. These are two separate event types precisely because one carries an LLM score and the other doesn't, and `PriorityPipeline` needs to treat them differently (see next step).

## 4. Priority and node creation

```mermaid
sequenceDiagram
    participant Score as ScoringPipeline
    participant Broker as EventBroker
    participant Prio as PriorityPipeline
    participant Store as StoragePipeline

    Score->>Broker: emit LinksScoredEvent / HighScoreLinksEvent
    Broker->>Prio: dispatch (subscribed to both)
    Prio->>Prio: strategy_fn(node, link, nlp_bias=60, llm_bias=40)<br/>or (1, 0) if the link has no LLM score
    Prio->>Broker: emit PriorityCalculatedEvent(entries: [{link, priority}])
    Broker->>Store: dispatch
    Store->>Store: create new child Node per entry<br/>(state=CREATED, priority=computed value)
    Store->>Broker: emit NodeAddedEvent for each new node
```

This is where the frontier actually grows: each scored link becomes a brand-new `Node`, and `NodeAddedEvent` fires again, which is exactly step 1, recursively. The crawl has no separate "main loop"; it's this event chain running until a stop condition fires.

## 5. Stopping

`StoppingPipeline` subscribes to the node-count and depth signals it needs and evaluates the blueprint's stop conditions (`max_nodes`, `max_depth`, `max_time`) after relevant events. When one is met, it emits `StopCrawlEvent`, which every pipeline treats as a drain-and-halt signal: `ExportingPipeline` flushes its buffer, `RequestsPipeline` stops pulling new fetches, and `Crawler` tears down the WebSocket gateway.

## 6. What the browser sees, the whole time

None of the above waits for a UI client to be connected. `TelemetryBridge` is just one more broker subscriber; if no browser is connected, it still updates `CrawlStateSnapshot` and calls `UIWebSocketGateway.broadcast()`, which is a no-op with zero connected clients. When a client *does* connect (at any point, including mid-crawl), it receives one `SNAPSHOT_FULL` message, the entire current state, node graph and telemetry counters both, and then the same incremental messages every other connected client gets from that point on. See [`05-deep-dive-resilience-observability.md`](05-deep-dive-resilience-observability.md) for how the frontend turns that stream into a scrubbable timeline.
