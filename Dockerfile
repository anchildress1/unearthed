FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install dependencies and create the non-root app user in one layer. The
# user setup is trivially cheap and rarely changes, so collapsing it into
# the uv sync layer keeps the image smaller without meaningfully hurting
# the dependency-layer cache: both invalidate together on uv.lock changes,
# which already forces a re-resolve of the heavy work.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && \
    addgroup --system app && adduser --system --ingroup app app

COPY . .

RUN chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
