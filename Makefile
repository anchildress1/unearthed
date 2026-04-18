.PHONY: install install-dev dev test lint clean docker-build docker-run fallbacks

# Install runtime dependencies
install:
	uv sync --no-dev

# Install all dependencies (runtime + dev)
install-dev:
	uv sync

# Run the FastAPI dev server with auto-reload
dev:
	uv run uvicorn app.main:app --reload --port 8001

# Run the full test suite
test:
	uv run pytest tests/ -v --tb=short

# Run tests with coverage
test-cov:
	uv run pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

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
