.PHONY: install dev dev-backend dev-frontend lint format typecheck check-baselines test check check-changed hook-test clean

install:
	uv sync --extra dev
	cd crawler-ui && npm install

# Runs the FastAPI API (:8000), the crawl WebSocket gateway (:8765,
# started per-crawl -- see core/crawler.py), and the Vite dev server
# (:5173) together. Ctrl+C stops both.
dev:
	@trap 'kill 0' EXIT; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

dev-backend:
	uv run uvicorn main:app --reload --port 8000

dev-frontend:
	cd crawler-ui && npm run dev

lint:
	uv run ruff check .
	cd crawler-ui && npm run lint

# Formats Python with ruff. The repo is not formatted yet: apply it in its own commit
# and list that commit in .git-blame-ignore-revs.
format:
	uv run ruff format .

# Strict mypy; modules still on the legacy list in pyproject.toml are skipped.
typecheck:
	uv run mypy

# The mypy legacy list and ruff baseline may only shrink (tools/check_baselines.py).
check-baselines:
	uv run python tools/check_baselines.py

test:
	uv run pytest -q
	cd crawler-ui && npm run test

# Everything CI runs. Agents and humans run this before asking for review.
check: lint typecheck check-baselines test hook-test
	cd crawler-ui && npm run build

# Lint and tests for the files this branch changed (see tools/check_changed.py).
check-changed:
	uv run python tools/check_changed.py

# The agent guard hooks (.claude/hooks) block what AGENTS.md says they block.
hook-test:
	uv run pytest -q tests/agents

clean:
	find . -type d -name __pycache__ -not -path "./crawler-ui/*" -exec rm -rf {} +
	rm -rf crawler-ui/dist
