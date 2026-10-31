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

## Context of use

Who uses CrawlViz, what for, and under which limits. The structure follows ISO 9241-210
(clause 6.2, understanding and specifying the context of use) and ISO 9241-11 (users,
goals, tasks, resources, environment).

### Users

| User group | Who | What they know | What they do not know | Frequency |
|---|---|---|---|---|
| U1 Crawl researcher (primary) | A researcher who runs a focused crawl for a topic: builds a corpus, studies how a topic spreads across a site, or tests the scoring cascade | The topic and the site; how to read a graph | Often not Python, IR terms (cosine, DBSCAN, percentile) or LLM operations (rate caps, tokens, providers) | Several sessions a week while a study runs; long sessions |
| U2 Score reviewer (primary) | A supervisor, co-author or paper reviewer who audits why the crawler scored, followed or skipped pages, and compares benchmark arms | Research method, statistics, the paper's claims | The code; which number on screen is which scale | Occasional, focused sessions; often on a recorded run, not a live one |
| U3 Developer (secondary) | A Python developer extending the crawler (a new stage, provider or strategy) and checking the result in the UI | The code | IR and the research question | While developing |
| U4 Demo visitor (secondary) | A recruiter or engineer opening the project to judge it | Neither the domain nor the code | Everything; has a few minutes | Once |

### Goals

- **U1:** start a crawl that stays on topic, spend little LLM budget, see early that it is
  going wrong (off topic, rate limited, stalled), change course without restarting, and
  take the results away as data.
- **U2:** for any page, see the evidence behind its score and the reason a link was
  skipped, in plain words; replay a past run; compare runs and benchmark arms on the same
  scale, with the costs.
- **U3:** see that a change behaves as intended on a crawl that needs no keys or network.
- **U4:** understand what the tool does in a minute, with a sample, and without keys.

### Tasks

The eight tasks CrawlViz is built around:

1. Start a crawl from a blueprint.
2. Watch progress and system health.
3. Understand why a page scored X, or why a link was skipped.
4. Replay or compare past runs.
5. Change a setting live.
6. Run with a local LLM.
7. Export results.
8. Compare benchmark arms.

### Environment

- **Technical:** one machine. FastAPI on `localhost:8000`, the Vite UI on `:5173`, and a
  crawl WebSocket on `:8765` that exists only while a crawl runs. Desktop Chrome or Firefox,
  usually a laptop screen (about 1366 to 1920 px wide). The UI must still work, with
  nothing cut off, on a 360 px wide screen and at 400% zoom. Only a light theme exists
  today. Text needs a contrast of at least 4.5:1, and controls and graph marks 3:1 (WCAG
  2.2 AA), in this theme and in any theme added later.
- **Single user.** No accounts. The backend serves the local browser only, and another web
  page open in the same browser could try to call it. The API must refuse a request that
  lacks the session token, or whose Host or Origin header is not the local app's.
- **Network:** real crawls need the target site and, for scoring, a hosted LLM provider
  (Groq, OpenRouter, NVIDIA, OpenAI-compatible) or, once built, a local one. The embedding
  model is downloaded once (`make model`) and then loaded offline.
- **Offline mode:** `CRAWLVIZ_OFFLINE=1` swaps in a frozen site (`benchmark/data/isi.json`),
  a scripted LLM and hashing embeddings. The `offline_demo.json` blueprint runs a 40-page
  crawl in about ten seconds. This is the environment for tests, CI and demos.
- **Social and organisational:** a research project heading for a paper. A change to
  scoring, ranking or prompts changes the research results, so it is reviewed and recorded
  before a release. The tests that pin scores and crawl order fail until their expected
  results are updated on purpose. A researcher can then tell which version of the code
  produced which results.

### Constraints

- **LLM caps.** Free tiers limit calls and tokens (Groq: about 200k tokens a day). A crawl
  has a per-crawl call budget (`llm.max_calls_per_crawl`); cost is a first-class quantity.
- **Politeness.** The crawler must obey robots.txt, and treat a robots.txt that cannot be
  read (a server error or no answer) as a refusal. It must honour Crawl-delay and
  Retry-After, limit its requests per host, and send an honest User-Agent with a contact
  address. The UI must not invite users to impersonate a browser.
- **Single process.** Not distributed; local SQLite and files. One crawl at a time.
- **Reproducibility.** A run is defined by its blueprint, settings, prompts, model ids and
  random seed. To reproduce a run, its manifest has to record the seeds, model versions,
  prompt hashes, library versions and hardware. Today each crawl's manifest records the
  blueprint, the settings, the embedding and LLM model names, the git commit and the seed.
- **Privacy.** Crawled pages and LLM replies stay on the machine unless the user exports
  them.

### What the product is not

Not a general site mirror, not a hosted service, not multi-user. Features that only make
sense for those (accounts, sharing, distributed crawling) are out of scope.
