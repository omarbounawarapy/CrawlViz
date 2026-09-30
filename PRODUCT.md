# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Crawl operators/researchers who configure a topic crawl, watch the graph build live, and scrub back through history to understand why links were scored and visited. Equally, portfolio reviewers (recruiters, engineers) evaluating the project through a demo. Used on desktop screens.

## Product Purpose
CrawlViz is a topic-focused web crawler that decides, link by link, which pages are worth visiting for a stated topic, using a cascade of local embedding scoring and a budgeted LLM pass. The React UI renders the crawl graph live over WebSocket and can replay its own event history. Success: the user can see and trust why the crawler went where it did.

## Positioning
Relevance-driven crawling with every scoring decision traceable and replayable, rather than an exhaustive structural crawl.

## Operating Context
Single-process asyncio backend; UI connects over WebSocket, state built by replaying an event log through a reducer with periodic checkpoints (scrubbable timeline). Crawls are defined by declarative JSON blueprints (templates/wikiMD.json, templates/isi.json).

## Capabilities and Constraints
Live graph, timeline scrubbing, blueprint-driven configuration, tracing/export. Not distributed; local SQLite. Frontend in crawler-ui/ (React, Vite).

## Evidence on Hand
Reference run on wikimd.org (539 nodes of 50,828 links), documented in docs/07-research-and-evaluation.md and report/rapport-english.pdf. No testimonials or customers exist; do not fabricate.

## Product Principles
- Every decision shown must be explainable: surface the why, not just the result.
- Live and historical views are one mental model.
- Dense data stays legible; the graph is the hero.
- Honest about limits (single-process, research scope).

## Accessibility & Inclusion
WCAG AA: contrast, keyboard access, and non-color-only encoding (graph relevance must not rely on hue alone).
