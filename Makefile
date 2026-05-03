.PHONY: install install-dev dev dev-frontend dev-backend test test-ci test-cov test-frontend test-e2e lhci lint clean docker-build docker-run deploy fallbacks data-export data-upload data-cutover data-verify

# Install runtime dependencies
install:
	uv sync --no-dev
	cd frontend && pnpm install

# Install all dependencies (runtime + dev)
install-dev:
	uv sync
	cd frontend && pnpm install

# Run frontend (Vite :5173) and backend (FastAPI :8001) together. Ctrl-C
# kills both. Vite proxies /api/* to the backend, so this is the canonical
# local-dev entry point.
dev:
	@bash -c 'trap "kill 0" EXIT INT TERM; \
		(uv run uvicorn app.main:app --reload --port 8001) & \
		(cd frontend && pnpm dev) & \
		wait'

# Run only the SvelteKit frontend (proxies /api/* to :8001).
dev-frontend:
	cd frontend && pnpm dev

# Run only the FastAPI backend on :8001 (autoreload).
dev-backend:
	uv run uvicorn app.main:app --reload --port 8001

# Run the full test suite: backend pytest + frontend unit/component + e2e + Lighthouse.
# "test" means every tier — unit, integration, e2e, and perf/a11y audits — so a
# green `make test` is the ship-ready signal.
test:
	uv run pytest tests/ -v --tb=short
	cd frontend && pnpm test
	cd frontend && pnpm test:e2e
	cd frontend && pnpm lhci

# CI-safe: skip the timing-sensitive backend e2e marker and skip LHCI (which
# requires a full build + Chromium audit and is too slow for per-commit CI).
# Frontend unit + Playwright e2e still run — they're deterministic and fast.
test-ci:
	uv run pytest tests/ -v --tb=short -m "not e2e"
	cd frontend && pnpm test
	cd frontend && pnpm test:e2e

# Run tests with coverage (CI-safe)
test-cov:
	uv run pytest tests/ -v --tb=short -m "not e2e" --cov=app --cov-report=term-missing

# Frontend unit/component tests (Vitest + jsdom + @testing-library/svelte)
test-frontend:
	cd frontend && pnpm test

# Frontend e2e tests (Playwright, Chromium, mocked backend)
test-e2e:
	cd frontend && pnpm test:e2e

# Lighthouse CI (thresholds: a11y>=1.0, SEO>=1.0, best-practices>=0.98, perf>=0.90)
lhci:
	cd frontend && pnpm lhci

# Lint with ruff (install separately: uv pip install ruff)
lint:
	uv run ruff check app/ tests/
	uv run ruff format --check app/ tests/

# Auto-format code
fmt:
	uv run ruff format app/ tests/

# Generate fallback JSON files from live Snowflake
fallbacks:
	uv run python -m scripts.generate_fallbacks

# Export every Snowflake table named in the export manifest to local Parquet,
# validating row counts. Writes under data/parquet/{layer}/.
data-export:
	uv run python -m scripts.export_snowflake_to_parquet

# Upload data/parquet/ to R2 (idempotent; replaces whatever is there).
data-upload:
	uv run python -m scripts.upload_to_r2 --src data/parquet

# One-shot live cutover: Snowflake -> local Parquet -> R2.
# Run this when R2 is empty or stale. The two steps are sequential — the
# upload only runs if the export succeeded (row-count mismatch fails loudly).
data-cutover: data-export data-upload

# Confirm what's actually in R2 right now (uses the same boto3 client as upload).
data-verify:
	uv run python -m scripts.upload_to_r2 --list

# Build Docker image (reads VITE_GOOGLE_MAPS_KEY from frontend/.env)
docker-build:
	docker build --build-arg VITE_GOOGLE_MAPS_KEY=$$(grep VITE_GOOGLE_MAPS_KEY frontend/.env | cut -d= -f2) -t unearthed .

# Run Docker container locally
docker-run:
	docker run --rm -p 8080:8080 --env-file .env unearthed

# Deploy to Cloud Run (builds, pushes, maps domain, configures secrets)
deploy:
	./deploy.sh

# Remove build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .coverage htmlcov/
