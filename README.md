# CrawlViz

![CrawlViz — relevance-guided web traversal](assets/portfolio/visuals/img1.png)
*The reference case study: a crawl seeded on "Type 2 Diabetes" against `wikimd.org`, explored to 539 nodes. `Glycemic_index` acts as a bridge node connecting the `Glucose` and `Diabetes` clusters — the structural signature the scoring cascade is meant to produce (see [`docs/07-research-and-evaluation.md`](docs/07-research-and-evaluation.md)).*

CrawlViz is a topic-focused web crawler. Instead of exploring a site exhaustively, it decides — link by link, in real time — which parts of the web are worth visiting to satisfy a stated topic, and which aren't.

The core problem it solves: a structural crawl (breadth-first from a seed page) has no notion of *meaning*. Starting from "Black Hole" on Wikipedia, a pure BFS drifts into science-fiction and video-game pages within a few hops, because those pages are densely linked to the seed even though they're off-topic. CrawlViz replaces "explore what's linked" with "explore what's relevant," using a cascade of a cheap local embedding model and a selectively-invoked LLM to score every candidate link before it's ever fetched.

That scoring decision is one part of a larger system: an asyncio event bus coordinates roughly a dozen independent pipelines (fetching, extraction, deduplication, scoring, priority, transformation, export, retry, logging), a React frontend renders the crawl graph live over WebSocket and can scrub backward through its own event history, and a two-tier tracing system exists specifically so a crawl's behavior can be reconstructed after the fact, not just watched live.

This repository's documentation is organized so you can go as deep as you need to and stop there — a recruiter can read this page, an engineer can read the architecture and deep dives, and a reviewer who wants to check a specific claim against the code can follow the file:line references throughout.

## Start here, by what you need

| You want to... | Go to |
|---|---|
| Understand what CrawlViz does and why, in five minutes | You're reading it |
| See the system architecture and how components fit together | [`docs/01-architecture.md`](docs/01-architecture.md) |
| Trace exactly what happens to one discovered link, step by step | [`docs/02-execution-walkthrough.md`](docs/02-execution-walkthrough.md) |
| Understand the event-driven pipeline and its concurrency model | [`docs/03-deep-dive-event-pipeline.md`](docs/03-deep-dive-event-pipeline.md) |
| Understand how semantic scoring and the NLP/LLM cascade work | [`docs/04-deep-dive-semantic-scoring.md`](docs/04-deep-dive-semantic-scoring.md) |
| Understand resilience, observability, and replay | [`docs/05-deep-dive-resilience-observability.md`](docs/05-deep-dive-resilience-observability.md) |
| Read the algorithms formally (scoring, priority, backoff) | [`docs/06-algorithms.md`](docs/06-algorithms.md) |
| See the research protocol and results from the project report | [`docs/07-research-and-evaluation.md`](docs/07-research-and-evaluation.md) |
| Install, run, test, and configure the system | [`docs/08-developer-guide.md`](docs/08-developer-guide.md) |
| See the architectural trade-offs and why they were made | [`docs/09-design-decisions.md`](docs/09-design-decisions.md) |
| See the full navigation map and how these documents relate | [`docs/00-index.md`](docs/00-index.md) |

## What's technically distinctive here

A one-line summary undersells each of these — the deep dives explain the mechanism, not just the label — but as an orientation:

- **A two-stage scoring cascade**, not a single LLM call per link. Every candidate link is first scored by a local sentence-embedding similarity pass (milliseconds, no network call); only a budgeted, strategy-dependent sample of the mid-confidence links is then sent to an LLM. This is what keeps LLM cost and latency from becoming the crawl's bottleneck. See [`docs/04-deep-dive-semantic-scoring.md`](docs/04-deep-dive-semantic-scoring.md).
- **An in-process pub/sub event bus** (57 distinct typed events across the backend) decouples fetching, extraction, filtering, scoring, priority calculation, transformation, and export into independently-scheduled pipelines that never call each other directly. See [`docs/03-deep-dive-event-pipeline.md`](docs/03-deep-dive-event-pipeline.md).
- **A `Future`-based readiness gate on every node** (`Node.ready`) that solves a genuine race condition: it lets the scoring pipeline pick up a node the instant it's created while still guaranteeing it won't try to score a node whose content hasn't finished being fetched and processed. See [`docs/03-deep-dive-event-pipeline.md`](docs/03-deep-dive-event-pipeline.md#the-node-ready-synchronization-gate).
- **A checkpoint-assisted event-sourced frontend.** The React state is built entirely by replaying a WebSocket event log through a pure reducer; the UI can scrub to any past point in the crawl by seeking to the nearest periodic checkpoint and replaying only the remainder, rather than replaying the whole log on every scrub. See [`docs/05-deep-dive-resilience-observability.md`](docs/05-deep-dive-resilience-observability.md).
- **A declarative blueprint model.** A crawl's seeds, domains, scoring strategy, extraction fields, and stop conditions are all data (a JSON document validated against a Pydantic schema), not code — the crawl engine itself is written once and reused across arbitrarily many topic configurations.

## What CrawlViz is not (yet)

Being direct about this up front, because the rest of the documentation is more useful if you already know the boundary:

- It is **not distributed**. It's a single-process asyncio application with in-memory state; "concurrency" here means cooperative multitasking within one process, not multiple machines or processes.
- Configuration is **read-only from the UI** in the current build — you can inspect the runtime configuration schema and current values, but there's no write-back/edit path yet (a JSON-schema-driven read view shipped; the editing form did not).
- The backend test suite (123 tests, all passing as of this review) covers pipelines, the blueprint schema/translator, and event wiring; it does not include end-to-end or live-LLM integration tests.
- Persistence is local SQLite, not a horizontally-scalable store — appropriate for the single-machine research/portfolio scope this project targets, not for production multi-tenant crawling.


## Reference case study

The project report documents a full run against `wikimd.org` (a medical encyclopedia), seeded from "Type 2 Diabetes," with a 1200-second budget and a 600-node cap. It explored 539 nodes out of 50,828 identified links (~1%) and produced a graph that clustered cleanly into complications, treatments, and epidemiology sub-topics, connected by bridge nodes like "Glycemic Index" and "HbA1c." That configuration is checked into this repository as `templates/wikiMD.json` and matches the report's parameters. Full protocol and results: [`docs/07-research-and-evaluation.md`](docs/07-research-and-evaluation.md).

## Technology stack

| Layer | Technology | Role |
|---|---|---|
| Crawl engine | Python 3.12 / `asyncio` | Cooperative concurrency for an I/O-bound workload |
| HTTP | `aiohttp` | Non-blocking page fetches |
| HTML parsing | `lxml` | XPath/CSS-driven link and field extraction |
| Semantic scoring | `sentence-transformers` (local) | Cheap, offline embedding similarity |
| Relevance / expansion | LLM via OpenRouter (`aiohttp`-based client) | Selective, budgeted relevance judgments and topic expansion |
| Control plane | FastAPI | REST API for templates, run control, config, validation |
| Data plane | `websockets` | Live crawl-state push to the browser |
| Persistence | SQLite (WAL mode) | Extracted-item export |
| Frontend | React + Vite | Live graph visualization, replay, inspection |

Full list with versions: `pyproject.toml` / `crawler-ui/package.json`.

