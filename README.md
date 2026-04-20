# unearthed

Show any US resident which specific coal mine supplies their local power plant.
Federal data (MSHA + EIA + EPA) in **Snowflake Cortex** — Analyst answers
factual questions in natural language; Complete (openai-gpt-5.2) writes both
the short mine-safety prose and the 2-3 sentence explanation of the national
H3 density map (with an honest degraded flag so template fallbacks never sit
under a Cortex byline). DEV Weekend Challenge 2026 — Earth Day Edition.

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
