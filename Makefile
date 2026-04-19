.PHONY: install install-dev dev server test test-ci test-cov test-frontend test-e2e lhci lint clean docker-build docker-run fallbacks

# Install runtime dependencies
install:
	uv sync --no-dev
	cd frontend && pnpm install

# Install all dependencies (runtime + dev)
install-dev:
	uv sync
	cd frontend && pnpm install

# Run the SvelteKit frontend (proxies API to backend on 8001)
dev:
	cd frontend && pnpm dev

# Run the FastAPI backend
server:
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

# Build Docker image
docker-build:
	docker build -t unearthed .

# Run Docker container locally
docker-run:
	docker run --rm -p 8080:8080 --env-file .env unearthed

# Remove build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .coverage htmlcov/
