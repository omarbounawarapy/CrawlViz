.PHONY: install dev dev-backend dev-frontend lint clean

install:
	uv sync
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

clean:
	find . -type d -name __pycache__ -not -path "./crawler-ui/*" -exec rm -rf {} +
	rm -rf crawler-ui/dist
