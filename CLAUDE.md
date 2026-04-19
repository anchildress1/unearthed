# unearthed

A live data product that shows any US resident which specific coal mine supplies their local power plant. Snowflake Cortex Analyst answers factual questions, Cortex Complete writes prose from federal mine safety records.

**Hard deadline:** DEV submission by **2026-04-20 06:59 UTC**.

## Quick Links

- [PRD](./PRD.md) — full product requirements
- [System Diagram](./system-diagram.md) — architecture overview (Mermaid)
- [AGENTS.md](./AGENTS.md) — coding rules, conventions, and Snowflake standards

## Tech Stack

- **Frontend:** SvelteKit (Vite) — scroll-driven dark glassmorphism, Google Maps JS API
- **Backend:** Python 3.12 / FastAPI — endpoints: `/mine-for-me`, `/ask`, `/h3-density`, `/emissions/{plant}`
- **Deps:** `pyproject.toml` + `uv` (backend), `pnpm` (frontend). `make install` to set up both.
- **Data:** Snowflake (6 tables, 2 views, 2 roles: APP_ROLE + READONLY_ROLE)
- **AI:** Snowflake Cortex Analyst (NL → SQL) + Cortex Complete (prose from fatality data)
- **Snowflake Native:** H3 geospatial hexbin density, Marketplace enrichment (EPA CAM emissions)
- **Deploy:** Google Cloud Run, secrets via Secret Manager, Docker multi-stage
- **Lint/Format:** `ruff` via `make lint` / `make fmt`
- **Dev:** `make server` (backend :8001) + `make dev` (frontend :5173, proxies API)
- **Tests:** `pytest` — `make test` (all), `make test-ci` (excludes e2e)
- **Assets:** eGRID GeoJSON (~1 MB), 19 fallback JSONs, semantic model YAML

## Data Sources

All US federal public-domain data:
- MSHA Mines (mine registry, coordinates, operator, county, status)
- MSHA Quarterly Production (tonnage per mine per quarter)
- MSHA Accidents (fatalities, injuries, days lost, narratives)
- EIA-923 Fuel Receipts 2024 (coal shipments: mine → plant → tons)
- EIA-860 Plants 2024 (plant locations, capacity, subregion)
- EPA eGRID subregion boundaries (GeoJSON for point-in-polygon)
- EPA Clean Air Markets (CO2/SO2/NOx emissions per plant — Snowflake Marketplace, free)

## Key Conventions

All coding rules, Snowflake standards, naming conventions, and architectural constraints live in **[AGENTS.md](./AGENTS.md)**. Read it before writing any code.
