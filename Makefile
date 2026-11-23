.PHONY: install dev backend frontend test sample check record-demo demo-build

install:
	cd backend && uv sync
	cd frontend && npm install

# Run backend and frontend together against the Ollama already running on this machine.
dev:
	@trap 'kill 0' INT TERM; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

backend:
	cd backend && uv run uvicorn lce.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q

check: test
	cd backend && uv run ruff check .
	cd frontend && npm run typecheck && npm run lint && npm run build

# Regenerate the fictional sample PDFs.
sample:
	cd backend && uv run python scripts/make_sample.py

# Re-record the hosted demo's results from the real backend on local Ollama.
record-demo:
	cd backend && uv run python scripts/record_demo.py

# Build the frontend as the hosted demo (replays recordings; no backend needed).
demo-build:
	cd frontend && NEXT_PUBLIC_DEMO=1 npm run build
