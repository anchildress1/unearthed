# unearthed

Show any US resident which specific coal mine supplies their local power plant.
Federal data (MSHA + EIA + EPA) in **Snowflake Cortex** — Analyst answers
factual questions in natural language; Complete (openai-gpt-5-chat) writes
the short safety prose. H3 geospatial hexbins render the national extraction
footprint. DEV Weekend Challenge 2026 — Earth Day Edition.

## Run locally

```sh
make install          # backend (uv) + frontend (pnpm)
make server           # backend on :8001
make dev              # frontend on :5173 (proxies API)
make test-ci          # full test suite, excludes e2e
```

See [CLAUDE.md](./CLAUDE.md) for the short project brief,
[AGENTS.md](./AGENTS.md) for coding rules, and [PRD.md](./PRD.md) for the
full product spec.
