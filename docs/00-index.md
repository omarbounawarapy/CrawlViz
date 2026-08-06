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


