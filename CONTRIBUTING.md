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
make check-changed   # fast: lint, mypy and the fast tests for the files your branch changed
make check           # what CI runs: lint, mypy, baseline guard, all tests, hook tests, UI build
```

`make check-changed` picks the tests by following imports from the changed files and skips tests marked `slow`. If you change `pyproject.toml`, `pytest.ini`, `uv.lock`, the `Makefile` or the CI workflow, it checks the whole Python side. If you change a file that decides crawl order or scoring, it also runs the behaviour pins and the method guards. Run `make check` before you ask for review.

The pieces, if you want to run one alone:

```bash
make lint                            # ruff check and eslint
make typecheck                       # mypy --strict
make check-baselines                 # the mypy legacy list and ruff baseline did not grow
uv run pytest -m "not pins"          # backend tests
uv run pytest -m pins                # behaviour pins (tests/pins/README.md)
cd crawler-ui && npm run test && npm run build
```

pytest runs from the repo root with no `PYTHONPATH`. Markers are strict (`slow`, `pins`, `e2e`, `method_guard`), and a test that runs longer than 300 seconds fails.

CI runs the same checks on every PR: ruff, mypy, the tests without the pins, the pins once, a check that the pin goldens did not change, the baseline guard, and the frontend lint, tests and build. A PR that fails any of them won't be mergeable.

Do not run `make format` on files you did not change. The repo is not formatted with `ruff format` yet, and a formatting pass belongs in its own commit.

## Code conventions

- Backend: Python 3.12, type-hinted, checked by `ruff` and `mypy --strict` (`[tool.ruff]` and `[tool.mypy]` in `pyproject.toml`). Modules on the mypy legacy list and files in the ruff per-file baseline may only get cleaner: remove an entry when its file is clean, never add one.
- Frontend: plain JS (no TypeScript), see `crawler-ui/README.md` for the folder layout and the `src/theme/` design-token system new UI code should build on.
- New backend pipelines follow the `BasePipeline` pattern (`pipelines/base_pipeline.py`) and communicate only through the `EventBroker`. Read [`docs/03-deep-dive-event-pipeline.md`](docs/03-deep-dive-event-pipeline.md) before adding a pipeline or event type.

## Pull requests

- Keep PRs focused on one change. Unrelated refactors make review harder and are more likely to get pushed back.
- Add or update tests for behavior you change.
- If your change affects documented behavior, update the relevant page under `docs/` in the same PR.

## Reporting bugs

Open a GitHub issue with: what you did, what you expected, what happened instead, and (if relevant) the blueprint JSON or log/trace output that shows the problem. See [`docs/05-deep-dive-resilience-observability.md`](docs/05-deep-dive-resilience-observability.md) for how to get a trace.

## Security issues

Do not open a public issue for a security vulnerability. See [`SECURITY.md`](SECURITY.md).
