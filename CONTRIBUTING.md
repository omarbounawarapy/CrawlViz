# Contributing

CrawlViz started as an academic project (see `report/rapport-english.pdf`) and is maintained as a solo portfolio project. Contributions are welcome, but keep expectations calibrated to that: response times may be slow, and larger changes are more likely to get a discussion than a quick merge.

## Before you start

For anything beyond a small fix, open an issue first describing what you want to change and why. This avoids duplicated work and lets us agree on the approach before you invest time in an implementation.

## Development setup

See [`docs/08-developer-guide.md`](docs/08-developer-guide.md) for the full install, run, and test instructions. In short:

```bash
make install
cp keys.example.json keys.json   # fill in real keys for whichever LLM provider(s) you use
make dev                         # backend on :8000, frontend on :5173
```

## Running checks before opening a PR

```bash
# Backend
uv run ruff check .
uv run pytest

# Frontend
cd crawler-ui
npm run lint
npm run test
npm run build
```

All four (`ruff`, `pytest`, `eslint`, the frontend test suite) run in CI on every PR; a build that fails any of them won't be mergeable.

## Code conventions

- Backend: Python 3.12, type-hinted, formatted per `ruff` (`pyproject.toml`'s `[tool.ruff]`).
- Frontend: plain JS (no TypeScript), see `crawler-ui/README.md` for the folder layout and the `src/theme/` design-token system new UI code should build on.
- New backend pipelines follow the `BasePipeline` pattern (`pipelines/base_pipeline.py`) and communicate exclusively through the `EventBroker` — see [`docs/03-deep-dive-event-pipeline.md`](docs/03-deep-dive-event-pipeline.md) before adding a new pipeline or event type.

## Pull requests

- Keep PRs focused on one change. Unrelated refactors make review harder and are more likely to get pushed back.
- Add or update tests for behavior you change.
- If your change affects documented behavior, update the relevant page under `docs/` in the same PR.

## Reporting bugs

Open a GitHub issue with: what you did, what you expected, what happened instead, and (if relevant) the blueprint JSON or log/trace output that shows the problem. See [`docs/05-deep-dive-resilience-observability.md`](docs/05-deep-dive-resilience-observability.md) for how to get a trace.

## Security issues

Do not open a public issue for a security vulnerability. See [`SECURITY.md`](SECURITY.md).
