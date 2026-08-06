# Design Decisions

Documented where the repository or report provides direct evidence of the reasoning. Where evidence exists only for the decision, not the rationale, that's stated rather than invented.

---

### D1. Two-stage scoring cascade instead of scoring every link with an LLM

**Problem:** Evaluating every discovered link with an LLM doesn't scale — the report names request-count explosion, token cost, and latency as the specific failure modes (§1.3.1), and frames a naive per-link LLM call as turning the LLM into the crawl's bottleneck.

**Options/constraints:** Score everything with the LLM (accurate, doesn't scale); score everything with only local NLP (scales, but a pure embedding-similarity signal alone is a weaker relevance judgment, particularly early in a crawl when the semantic basis is thin); some hybrid of the two.

**Decision:** A cascade — cheap local NLP scoring always runs and buckets every link; the LLM is invoked only for a budgeted, strategy-dependent sample (the full "mid-confidence" band, plus small samples from the "low" and "high" bands for exploration and precision respectively).

**Consequences:** LLM cost scales with nodes visited (bounded per-node budget), not with links discovered — in the reference run, 50,828 links were identified against 539 explored nodes, a ratio the cascade's sampling is directly responsible for. The trade-off is that some individually-relevant links in the "low" bucket are permanently dropped (only a random sample survives), and the low/high thresholds are a tuning surface the crawl operator has to get right for a given topic.

---

### D2. In-process pub/sub instead of direct pipeline-to-pipeline calls

**Problem:** A crawl pipeline has many stages (fetch, extract, filter, transform, score, prioritize, store, export) with different concurrency needs, and new stages get added as the system evolves (the telemetry bridge itself is evidence of this — it was added well after the original pipeline set).

**Options/constraints:** Direct method calls between pipeline objects (simple, but couples every stage to the exact interface of every stage it calls, and makes adding an observer of an existing stage require modifying that stage); a full external message queue (decoupled, but real infrastructure overhead for a single-process application); an in-process event bus.

**Decision:** A single `EventBroker` with typed events and a subscription registry; pipelines never call each other, only `broker.subscribe()` at wiring time and `broker.dispatch()` (implicitly, via emitting events) at runtime.

**Consequences:** Producers don't know or care who's listening — extensibility is genuinely additive (see `03-deep-dive-event-pipeline.md`). The cost is a whole system that's easy to reason about stage-by-stage but harder to reason about holistically — "what happens when a node is created" requires tracing every subscriber to `NodeAddedEvent` across the wiring block, not just reading one function. The project's own `docs/V2_ARCHITECTURE.md` audit exists largely because that holistic tracing had drifted from what was actually wired (events emitted with no subscriber, or a needed subscription missing) — a direct, acknowledged cost of this architecture's discoverability.

---

### D3. The `node.ready` Future instead of a single unified queue

**Problem:** `RequestsPipeline` and `ScoringPipeline` both react to a node's creation, but scoring can't meaningfully start until fetching, extraction, filtering, and transformation have all completed for that specific node — a naive shared trigger risks scoring pipeline picking up a node before its data exists (the report's §1.6.3 "out-of-order" problem).

**Options/constraints:** A single combined fetch-then-score pipeline (removes the race, but serializes what could otherwise run concurrently, and re-couples two conceptually separate stages); polling / retry-until-ready (works, but wastes cycles and adds latency); a synchronization primitive scoped to the individual node.

**Decision:** Each `Node` carries its own `asyncio.Future` (`node.ready`), resolved once that specific node's transformation completes. `ScoringPipeline` claims a node immediately on creation but blocks on that node's future before doing any work.

**Consequences:** No polling, no wasted cycles, and the two pipelines stay fully decoupled and independently concurrent — this is a genuinely elegant solution to a real problem, not decoration. The trade-off, noted directly rather than glossed over, is that the future's resolution point is coupled to *transformation* completing, which bundles item-shaping (conceptually unrelated to link scoring) into the gate that unblocks scoring — see `03-deep-dive-event-pipeline.md` for the detail.

---

### D4. Declarative blueprints instead of per-crawl code

**Problem:** A researcher or operator wants to run the same crawl engine against many different topics, domains, extraction schemas, and scoring strategies, without touching the engine's code for each one.

**Options/constraints:** A general-purpose scripting/config API embedded in the engine (flexible, but blurs the line between configuration and code, and makes the engine's behavior harder to reason about in isolation); a declarative, schema-validated configuration document.

**Decision:** A JSON "blueprint" (validated against a Pydantic schema in `routes/blueprint_schema.py`) fully describes seeds, domains, scoring strategy, extraction fields and transforms, and stop conditions. The engine's procedural logic is written once; blueprints only configure it, they don't extend it.

**Consequences:** The same engine, unmodified, ran the report's `wikiMD` diabetes case study and can run an entirely different topic/domain by swapping the blueprint — this is directly demonstrated by `templates/wikiMD.json` and `templates/isi.json` coexisting as two working configurations. The cost is that anything not expressible in the blueprint schema (a genuinely novel extraction pattern, a new priority strategy) requires code changes, not configuration — the blueprint model trades flexibility for reuse-without-code-changes within the space it does cover.

---

### D5. Separate in-memory `Storage` and `items.db` export sink

**Problem:** The live crawl graph (for visualization) and the extracted data (for downstream use) have different lifetimes, different consumers, and different consistency needs — the graph needs to be mutated and queried constantly during a crawl; the export data needs to be durable and queryable after the crawl ends, independent of whether the process is still running.

**Decision:** Two separate stores: in-memory `Storage`, owned exclusively by `StoragePipeline`, holding the live graph; SQLite `items.db`, written exclusively by `ExportingPipeline`, holding only extracted items (not links, not graph structure).

**Consequences:** `routes/validation.py` can read `items.db` as a plain, read-only SQL data source, independent of whether a crawl is even running — this is what makes the validation API's minimal, allowlisted design (`routes/validation_db.py`) sufficient rather than needing to also handle live-state concurrency. The cost is that the live graph itself is not durable — closing the process loses the in-memory node/link structure even though the extracted items survive in SQLite, which is a real, acknowledged limitation (see next document) rather than a gap this decision was unaware of.

---

### D6. Event replay via periodic checkpoints instead of full-log replay

**Problem:** The frontend derives all UI state from replaying a WebSocket event log through a reducer, so timeline scrubbing means replaying events — and replaying the entire log on every scrub degrades as a crawl runs longer, exactly when the timeline feature becomes most useful.

**Decision:** Checkpoint a full state snapshot every 200 events; seeking to any index replays only from the nearest prior checkpoint, not from the start.

**Consequences:** Seek cost is bounded by the checkpoint interval regardless of total log length, at the cost of `O(log length / 200)` extra memory for stored snapshots. This is stated in the code itself as a deliberate correction to the project's earlier (V1) full-replay approach, not a decision made from a blank slate — it's evidence of the project iterating on a real, measured usability problem rather than getting the design right on the first attempt, which is itself worth noting rather than treating as a flaw.
