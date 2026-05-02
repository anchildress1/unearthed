# ─── Stage 1: Build SvelteKit frontend ────────────────────────────────────────
FROM node:22-alpine AS frontend

RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /build

COPY frontend/package.json frontend/pnpm-lock.yaml ./
COPY frontend/svelte.config.js frontend/vite.config.js ./
RUN pnpm install --frozen-lockfile

# Client-side key injected via --build-arg from cloudbuild.yaml.
# frontend/.env is gitignored so Vite cannot read it during Cloud Build.
ARG VITE_GOOGLE_MAPS_KEY
ENV VITE_GOOGLE_MAPS_KEY=$VITE_GOOGLE_MAPS_KEY

COPY frontend/ .
RUN pnpm build && test -f build/index.html


# ─── Stage 2: Resolve Python dependencies ────────────────────────────────────
FROM python:3.12-slim AS deps

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


# ─── Stage 3: Production runtime ─────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

# Pre-built virtualenv — no build tools in the final image
COPY --from=deps /app/.venv /app/.venv

# Application code (selective COPY — no tests, scripts, or dev tooling)
COPY app/ app/
COPY assets/ assets/
COPY static/ static/

# Pre-built frontend from stage 1
COPY --from=frontend /build/build frontend/build/

# Pre-install DuckDB httpfs extension so Cloud Run cold starts don't trigger
# an outbound download. HOME=/app puts extensions under /app/.duckdb (covered
# by the chown below); at runtime LOAD httpfs reads from that path, no network.
ENV HOME=/app
RUN /app/.venv/bin/python -c "import duckdb; con=duckdb.connect(); con.execute('INSTALL httpfs')"

RUN chown -R app:app /app

USER app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
