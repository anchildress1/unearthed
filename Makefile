.PHONY: install install-dev dev server test test-ci test-cov lint clean docker-build docker-run fallbacks

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

# Run the full test suite (all tests including e2e)
test:
	uv run pytest tests/ -v --tb=short

# Run CI-safe tests (excludes timing-sensitive e2e tests)
test-ci:
	uv run pytest tests/ -v --tb=short -m "not e2e"

# Run tests with coverage (CI-safe)
test-cov:
	uv run pytest tests/ -v --tb=short -m "not e2e" --cov=app --cov-report=term-missing

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
