.PHONY: audit hooks model clean-runs install dev dev-backend dev-frontend lint format typecheck check-baselines test check check-changed hook-test clean

install:
	uv sync --extra dev
	cd crawler-ui && npm install

# Installs the git hooks from lefthook.yml (pre-commit checks, commit title check).
hooks:
	cd crawler-ui && npx lefthook install

# Downloads the sentence-transformers model once (needs network). Crawls load it with
# local_files_only, so run this before the first real crawl; offline mode does not need it.
model:
	uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

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
	uv run ruff format --check .
	cd crawler-ui && npm run lint && npm run lint:css && npm run lint:html && npm run format:check

# Formats Python and the UI. A formatting-only commit goes in .git-blame-ignore-revs.
format:
	uv run ruff format .
	cd crawler-ui && npm run format

# Strict mypy (modules still on the legacy list in pyproject.toml are skipped) and tsc.
typecheck:
	uv run mypy
	cd crawler-ui && npm run typecheck

# The mypy legacy list and ruff baseline may only shrink (tools/check_baselines.py).
check-baselines:
	uv run python tools/check_baselines.py

# Known-vulnerability scan of the locked Python and npm dependencies (what CI runs).
audit:
	uv export --locked --extra dev --no-emit-project --no-hashes -o .audit-requirements.txt
	uv run pip-audit --strict -r .audit-requirements.txt --no-deps --disable-pip; \
		status=$$?; rm -f .audit-requirements.txt; exit $$status
	cd crawler-ui && npm audit --audit-level=high

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

# Deletes recorded crawl runs, logs, debug dumps and saved semantic spaces. Past runs cannot
# be recovered, so it only runs as `make clean-runs YES=1`.
clean-runs:
	@test "$(YES)" = "1" || { echo "This deletes export/, logs/, debug/ and .space_store/. Run: make clean-runs YES=1"; exit 1; }
	rm -rf export/* logs/* debug/* .space_store/*
