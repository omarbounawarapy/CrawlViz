# Documentation map

This is the navigation hub for CrawlViz's documentation. Each page has a canonical home for its concepts; other pages link to it rather than re-explaining it.

## Reading paths by audience

**Recruiter / client (5 minutes):** [`README.md`](../README.md) 

**Software engineer evaluating the code:** [`01-architecture.md`](01-architecture.md) → [`02-execution-walkthrough.md`](02-execution-walkthrough.md) → whichever deep dive (`03`, `04`, `05`) matches what you're curious about → [`08-developer-guide.md`](08-developer-guide.md) to actually run it.

**Technical lead assessing trade-offs:** [`01-architecture.md`](01-architecture.md) → [`09-design-decisions.md`](09-design-decisions.md) 

**Research / academic reader:** [`06-algorithms.md`](06-algorithms.md) → [`07-research-and-evaluation.md`](07-research-and-evaluation.md).

## All documents

| # | Document | Answers |
|---|---|---|
| 00 | [Index](00-index.md) | Where do I find X? |
| 01 | [Architecture](01-architecture.md) | What are the components, and how are they wired together? |
| 02 | [Execution Walkthrough](02-execution-walkthrough.md) | Concretely, what happens between "a link was discovered" and "a new node exists"? |
| 03 | [Deep Dive: Event-Driven Pipeline](03-deep-dive-event-pipeline.md) | How does the broker work? Why pipelines instead of function calls? Where's the actual asynchrony, and what does it solve? |
| 04 | [Deep Dive: Semantic Scoring](04-deep-dive-semantic-scoring.md) | What does the NLP layer compute? What does the LLM see and return? How do they combine into a priority? |
| 05 | [Deep Dive: Resilience & Observability](05-deep-dive-resilience-observability.md) | How does the crawler survive flaky networks? How is a session traced, logged, and replayed? |
| 06 | [Algorithms](06-algorithms.md) | Formal description of the scoring, bucketing, priority, and backoff functions |
| 07 | [Research & Evaluation](07-research-and-evaluation.md) | What was tested, how, and what did it show? |
| 08 | [Developer Guide](08-developer-guide.md) | How do I install, run, configure, and test this? |
| 09 | [Design Decisions](09-design-decisions.md) | Why this architecture and not another? |

## Project Report

**CrawlViz: A Semantically-Guided Focused Web Crawler** is the academic project report behind this repository. It covers the state of the art in focused crawling, the algorithmic and architectural design of the scoring cascade and event pipeline, the UML modeling of the system, and the implementation and experimental evaluation (the `wikimd.org` / Type 2 Diabetes case study referenced throughout this documentation).

Expected path: [`../report/rapport-english.pdf`](../report/rapport-english.pdf) (English translation; the original is in French).

The documentation above explains **how CrawlViz is implemented**; the report explains **why it was designed that way, how it was evaluated, and what the results mean**. Where a topic is covered in both, the relevant doc page links to the report chapter or section rather than repeating its argument.

| Documentation topic | Report reference |
|---|---|
| Focused crawling background, state of the art, requirements | [Chapter 1 — General Project Framework](../report/rapport-english.pdf#page=4) |
| EventBroker / pub-sub architecture | [§2.6.2 — Pipeline and Pub/Sub Model](../report/rapport-english.pdf#page=14) |
| Semantic scoring (NLP encoding, semantic basis, cold start) | [§2.1 — Semantic Representation of the Target Topic](../report/rapport-english.pdf#page=10) |
| Two-stage NLP/LLM scoring cascade | [§2.3 — Two-Stage Scoring Architecture](../report/rapport-english.pdf#page=12) |
| Resilience (backoff, jitter, rate limiting) | [§2.5 — Resilience Strategies](../report/rapport-english.pdf#page=14) |
| Node lifecycle & causal traceability / replay | [§2.7 — Causal Traceability and Replayability](../report/rapport-english.pdf#page=17) |
| Declarative blueprint configuration | [§2.8 — Declarative Blueprint Configuration](../report/rapport-english.pdf#page=19) |
| System architecture, use cases, class & sequence diagrams | [Chapter 3 — Design](../report/rapport-english.pdf#page=21) |
| Technology stack & implementation | [§4.1 — Environment and Technology Choices](../report/rapport-english.pdf#page=40) |
| Experimental protocol & reference-run results | [§4.3 — Practical Evaluation](../report/rapport-english.pdf#page=66) |


