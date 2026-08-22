# Deep Dive: The Event-Driven Pipeline

## The problem this architecture solves

A web crawler is dominated by I/O wait: network round-trips for fetching, and for CrawlViz specifically, network round-trips for LLM calls too. The report's own measurement makes the case concretely — a sequential run and a concurrent run explored the same 560 nodes and found the same ~65,000 links; the sequential run took over 600 seconds, the concurrent run took 15. That's not a claim about theoretical I/O-bound speedup in the abstract; it's a measured ~40x difference on this codebase, doing the same work.

`asyncio` gets you concurrency without one thread per in-flight request, which matters because a crawl can have dozens of fetches and LLM calls outstanding simultaneously — but concurrency alone doesn't answer the architectural question that actually shaped this system: **how do independently-running stages of a pipeline hand work to each other without becoming tightly coupled or racing each other?** That's what the event bus and the pipelines built on it answer.

## The broker and the registry

`core/event_broker.py`'s `EventBroker` is deliberately small: it holds an `EventRegistry` (the subscription table — event type → list of subscriber objects) and a `dispatch(event)` method that looks up subscribers for `type(event)` and calls `subscriber.put(event)` on each, wrapped in `asyncio.create_task`. That's the entire mechanism. It does not know what a `NodeAddedEvent` means, does not transform events, and does not guarantee delivery order across different subscribers — each dispatched `put()` is its own task.

`subscribe()` is a plain method call (`broker.subscribe(pipeline, [EventTypeA, EventTypeB])`), not a decorator or a config file — wiring happens once, in `core/crawler.py`, where every pipeline's subscriptions are visible in one place (roughly lines 420–450). This matters for extensibility in a very literal sense: adding a new consumer of, say, `NodeExpandedEvent` is one line in that wiring block, and requires touching nothing inside `ScoringPipeline` or any other producer of that event. The **producer never knows who's listening, or how many listeners there are.**

## The pipeline abstraction

Every pipeline (`RequestsPipeline`, `ScoringPipeline`, `FilteringPipeline`, and eight others) subclasses `BasePipeline` (`pipelines/base_pipeline.py`), which provides:

- An `asyncio.Queue` (or `PriorityQueue`, depending on the pipeline — see below) that events land in via `put()`.
- A configurable pool of `max_concurrency` worker coroutines, each running `while True: item = await queue.get(); await self._process(item, worker_id)`.
- A uniform `start()` / `stop()` lifecycle the crawler calls once per crawl.

Subclasses implement exactly one method — `_process()` — and nothing else about how they're scheduled, queued, or torn down. This is why the pipeline count in this codebase (~13) doesn't correspond to ~13 different concurrency patterns: there's one pattern, reused. The exception, `RequestsPipeline`, is deliberate rather than an oversight — its docstring explains it directly: it queues `Node` domain objects instead of typed events, and its "processing" is a rate-limited fetch loop rather than generic event handling, so forcing it through the same `BasePipeline` shape would have meant bending the abstraction to fit a case it wasn't designed for.

**Per-pipeline concurrency is a real, tunable knob**, not a fixed constant: `StoragePipeline` runs with a single worker (`max_concurrency=1`) because it's the only writer to the in-memory `Storage`, and serializing writes there is simpler than coordinating concurrent mutation of shared dicts. `RequestsPipeline` and `ProcessingPipeline` run with multiple workers, because fetching and HTML parsing genuinely parallelize. This is exactly the report's claim in §1.6.2 — "one worker suffices for the database; several workers can be used for request processing when volume increases" — and it's visible directly in each pipeline's constructor defaults, not just asserted.

## The `node.ready` synchronization gate

This is the mechanism the report's §1.6.3 describes conceptually (separating the fetch and scoring pipelines to avoid an out-of-order race) — worth being precise about the actual implementation, because it's a genuinely elegant piece of engineering that's easy to undersell as "we used two queues."

**The race it avoids:** `ScoringPipeline` and `RequestsPipeline` both subscribe to `NodeAddedEvent`. If scoring simply pulled the next node off its own queue whenever it was free, nothing would stop it from trying to score a node whose page hasn't been fetched yet — the two pipelines are racing on the same signal.

**The fix is not "wait longer" — it's a `Future` living on the `Node` itself.** `models/node.py`'s `Node` class carries `self.ready: asyncio.Future`, created unresolved. `ScoringPipeline._process(node)` does `await node.ready` as its first line — this suspends *only that specific coroutine*, on *only that specific node's* future; it does not block the pipeline's other concurrent workers, and it does not block `RequestsPipeline` at all, because `RequestsPipeline` never awaits it. The future resolves when `StoragePipeline._on_transformation_completed` calls `node.update_state()`, which happens only once that node's content has been fetched, its links and items extracted, filtered, and its items transformed.

The result: `ScoringPipeline` can claim a node the instant it's created (so there's no scheduling gap), while the actual scoring work for that node cannot start until the data it needs genuinely exists — enforced by the `Future`, not by timing assumptions, retries, or polling. This is precisely how the report's Table 1.3 (`the scoring worker only considers already-ready nodes`) is realized in code.

**A related, non-obvious detail:** the future resolves after *transformation* completes, not after *filtering* completes, even though filtering is what actually produces the deduplicated link list scoring needs. Item transformation and link scoring are conceptually independent (one shapes extracted content fields, the other ranks candidate URLs) but are coupled here because both `event.links` and the transformed items arrive on the same `TransformationCompletedEvent`. In practice this means a node with a long transform chain on its items delays scoring on its links, a coupling that isn't visible from the report's lifecycle-state description alone.

## Two logging tiers on the same event stream

`LoggingPipeline` and `DebuggingPipeline` both subscribe to (largely overlapping) event sets, but serve different purposes and are independently toggleable:

- **`LoggingPipeline`** is always on. It renders a fixed, small set of node-lifecycle transitions (`CREATED`, `FETCHED`, `FILTERED`, `TRANSFORMED`, `SCORED`, `EXPANDED`) as structured log lines, each carrying node ID, worker ID, and state.
- **`DebuggingPipeline`** is optional (gated by a `DEBUG` config flag) and subscribes to a much wider event surface — NLP scoring internals, LLM request/response cycles, network-level retries — anything useful for reconstructing *why* a decision was made, not just *that* a state transition happened.

The separation matters operationally: `DebuggingPipeline`'s wider event surface has real overhead (every subscribed event triggers a `put()` and a coroutine, whether or not anything is listening usefully), so it's designed to be switched off in normal operation without losing the always-on lifecycle trail that `LoggingPipeline` provides. See [`05-deep-dive-resilience-observability.md`](05-deep-dive-resilience-observability.md) for what each tier actually captures and how the traced data feeds session replay.


