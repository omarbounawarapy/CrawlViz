# Security Policy

CrawlViz is a research/portfolio project, not something deployed as a multi-tenant production service (see the scope note in [`docs/00-index.md`](docs/00-index.md)). That said, real security issues (e.g. anything that could leak API keys, execute arbitrary code, or read arbitrary files through the API) are taken seriously.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security vulnerability. Instead, report it privately via [GitHub's private vulnerability reporting](https://github.com/omarbounawarapy/crawlviz/security/advisories/new) for this repository, or contact the maintainer directly.

Include:
- A description of the issue and its potential impact.
- Steps to reproduce, or a proof of concept if you have one.
- Which version/commit you tested against.

## What's in scope

- The FastAPI control API (`routes/`), including the read-only SQL layer in `routes/validation_db.py`.
- Handling of LLM provider API keys (`infrastructure/key_manager.py`, `keys.json`).
- The WebSocket data plane (`ui_bridge/ui_websocket_gateway.py`).

## What's out of scope

- Denial-of-service reports against a single-process, single-machine crawler with no built-in rate limiting for its own control API — this is a known, accepted limitation of the current architecture, not something we're tracking as a vulnerability.
- Issues that only manifest with a maliciously crafted `keys.json` or blueprint file you'd have to place there yourself (i.e. you already have local filesystem access).

## Response

This is maintained by one person outside of full-time work, so there's no formal SLA. Reports will be acknowledged as soon as reasonably possible.
