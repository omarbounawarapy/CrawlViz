# Design Decisions

Each rationale is cited where the repository or the report gives direct evidence. Where only the decision is documented, this page states that and does not invent a reason.

---

### D1. Two-stage scoring cascade instead of scoring every link with an LLM

**Problem:** Evaluating every discovered link with an LLM doesn't scale. The report names request-count explosion, token cost, and latency as the specific failure modes ([§2.3.1: The Problem of Evaluation Cost](../report/rapport-english.pdf#page=12)), and frames a naive per-link LLM call as turning the LLM into the crawl's bottleneck.

**Options/constraints:** Score everything with the LLM (accurate, doesn't scale); score everything with only local NLP (scales, but a pure embedding-similarity signal alone is a weaker relevance judgment, particularly early in a crawl when the semantic basis is thin); some hybrid of the two.

**Decision:** A cascade. Cheap local NLP scoring always runs and buckets every link; the LLM is invoked only for a budgeted, strategy-dependent sample (the full "mid-confidence" band, plus small samples from the "low" and "high" bands for exploration and precision respectively).

**Consequences:** LLM cost scales with nodes visited (bounded per-node budget), not with links discovered. In the reference run, 50,828 links were identified against 539 explored nodes, a ratio the cascade's sampling is directly responsible for. The trade-off is that some individually relevant links in the "low" bucket are permanently dropped (only a random sample survives), and the low/high thresholds are a tuning surface the crawl operator has to get right for a given topic.

---

### D2. In-process pub/sub instead of direct pipeline-to-pipeline calls

**Problem:** A crawl pipeline has many stages (fetch, extract, filter, transform, score, prioritize, store, export) with different concurrency needs, and new stages get added as the system evolves. The telemetry bridge itself is evidence of this: it was added well after the original pipeline set.

**Options/constraints:** Direct method calls between pipeline objects (simple, but couples every stage to the exact interface of every stage it calls, and makes adding an observer of an existing stage require modifying that stage); a full external message queue (decoupled, but real infrastructure overhead for a single-process application); an in-process event bus.

**Decision:** A single `EventBroker` with typed events and a subscription registry. Pipelines never call each other, only `broker.subscribe()` at wiring time and `broker.dispatch()` (implicitly, via emitting events) at runtime.

**Consequences:** Producers do not know who is listening, so a new consumer is added without touching the producers (see `03-deep-dive-event-pipeline.md`). The cost is that the system is easy to reason about one stage at a time but hard to follow end to end. Answering "what happens when a node is created" means tracing every subscriber to `NodeAddedEvent` across the wiring block. Events with no subscriber, or a missing subscription, are easy to introduce this way.

---

### D3. The `node.ready` Future instead of a single unified queue

**Problem:** `RequestsPipeline` and `ScoringPipeline` both react to a node's creation, but scoring can't meaningfully start until fetching, extraction, filtering, and transformation have all completed for that specific node. A naive shared trigger risks the scoring pipeline picking up a node before its data exists (the report's [§2.6.3, "Simultaneous Triggering and Synchronization Mechanism"](../report/rapport-english.pdf#page=17) out-of-order problem).

**Options/constraints:** A single combined fetch-then-score pipeline (removes the race, but serializes what could otherwise run concurrently, and re-couples two conceptually separate stages); polling / retry-until-ready (works, but wastes cycles and adds latency); a synchronization primitive scoped to the individual node.

**Decision:** Each `Node` carries its own `asyncio.Future` (`node.ready`), resolved once that specific node's transformation completes. `ScoringPipeline` claims a node immediately on creation but blocks on that node's future before doing any work.

**Consequences:** No polling and no wasted cycles, and the two pipelines stay decoupled and independently concurrent. The trade-off is that the future's resolution point is coupled to *transformation* completing, which bundles item-shaping (conceptually unrelated to link scoring) into the gate that unblocks scoring; see `03-deep-dive-event-pipeline.md` for the detail.

---

### D4. Declarative blueprints instead of per-crawl code

**Problem:** A researcher or operator wants to run the same crawl engine against many different topics, domains, extraction schemas, and scoring strategies, without touching the engine's code for each one.

**Options/constraints:** A general-purpose scripting/config API embedded in the engine (flexible, but blurs the line between configuration and code, and makes the engine's behavior harder to reason about in isolation); a declarative, schema-validated configuration document.

**Decision:** A JSON "blueprint" (validated against a Pydantic schema in `config/blueprint_schema.py`) fully describes seeds, domains, scoring strategy, extraction fields and transforms, and stop conditions. The engine's procedural logic is written once; blueprints only configure it, they don't extend it. This is the declarative-configuration principle the report lays out in [§2.8.1: Blueprint Principle](../report/rapport-english.pdf#page=19).

**Consequences:** The same engine ran the report's `wikiMD` diabetes case study, and it runs a different topic and domain by swapping the blueprint. `templates/wikiMD.json` and `templates/isi.json` are two working configurations. The cost is that anything the blueprint schema cannot express (a new extraction pattern, a new priority strategy) needs a code change. The blueprint model trades flexibility for configuration-only reuse within the space it covers.

---

### D5. Separate in-memory `Storage` and `items.db` export sink

**Problem:** The live crawl graph (for visualization) and the extracted data (for downstream use) have different lifetimes, different consumers, and different consistency needs. The graph needs to be mutated and queried constantly during a crawl; the export data needs to be durable and queryable after the crawl ends, independent of whether the process is still running.

**Decision:** Two separate stores: in-memory `Storage`, owned exclusively by `StoragePipeline`, holding the live graph; SQLite `items.db`, written exclusively by `ExportingPipeline`, holding only extracted items (not links, not graph structure).

**Consequences:** `routes/validation.py` reads `items.db` as a read-only SQL source, whether or not a crawl is running. The validation API (`routes/validation_db.py`) therefore needs no live-state concurrency handling. The cost is that the live graph is not durable: closing the process drops the in-memory nodes and links, while extracted items survive in SQLite. See the next document for the details.

---

### D6. Event replay via periodic checkpoints instead of full-log replay

**Problem:** The frontend derives all UI state from replaying a WebSocket event log through a reducer, so timeline scrubbing means replaying events, and replaying the entire log on every scrub degrades as a crawl runs longer, exactly when the timeline feature becomes most useful.

**Decision:** Checkpoint a full state snapshot every 200 events. Seeking to any index replays only from the nearest prior checkpoint, not from the start.

**Consequences:** Seek cost is bounded by the checkpoint interval, whatever the total log length. The cost is `O(log length / 200)` extra memory for stored snapshots. The code comments describe this as a correction to the earlier full-replay approach (V1), which replayed the whole log on every seek.
