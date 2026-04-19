# unearthed

A live data product that shows any US resident which specific coal mine supplies their local power plant. Snowflake Cortex Analyst answers factual questions about the data in natural language.

**Hard deadline:** DEV submission by **2026-04-20 06:59 UTC**.

## Quick Links

- [PRD](./PRD.md) — full product requirements
- [System Diagram](./system-diagram.md) — architecture overview (Mermaid)
- [AGENTS.md](./AGENTS.md) — coding rules, conventions, and Snowflake standards

## Tech Stack

- **Frontend:** Vanilla JS, MapLibre GL JS (map, satellite basemap, animated flow lines)
- **Backend:** Python 3.12 / FastAPI — two endpoints: `/mine-for-me`, `/ask`
- **Deps:** `pyproject.toml` + `uv` (no requirements.txt). `make install-dev` to set up.
- **Data:** Snowflake (5 tables, 2 views, 2 roles: APP_ROLE + READONLY_ROLE)
- **AI:** Snowflake Cortex Analyst (NL → SQL via semantic model YAML)
- **Deploy:** Google Cloud Run, secrets via Secret Manager, Docker with non-root user
- **Lint/Format:** `ruff` via `make lint` / `make fmt`
- **Tests:** `pytest` — `make test` (521 tests, all), `make test-ci` (510, excludes e2e timing tests)
- **Assets:** eGRID GeoJSON (~1 MB), 19 fallback JSONs, semantic model YAML

## Data Sources

All US federal public-domain data:
- MSHA Mines (mine registry, coordinates, operator, county)
- MSHA Quarterly Production (tonnage per mine per quarter)
- EIA-923 Fuel Receipts 2024 (coal shipments: mine -> plant -> tons)
- EIA-860 Plants 2024 (plant locations, capacity, subregion)
- EPA eGRID subregion boundaries (GeoJSON for point-in-polygon)

## Key Conventions

All coding rules, Snowflake standards, naming conventions, and architectural constraints live in **[AGENTS.md](./AGENTS.md)**. Read it before writing any code.
