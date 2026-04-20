![unearthed — coal, traced home](https://repository-images.githubusercontent.com/1213154728/6ae1ef8d-dd2d-4a2b-b708-3353b783fbfa)

# Unearthed

**Tagline:** Find the coal mine under contract to your local power plant. Watch it die in real time. Ask it questions.

Unearthed turns public federal data (MSHA + EIA + EPA) into a consumer-scale reveal: enter an address, see the specific coal mine feeding your grid, read memorial prose written from that mine's safety record, then ask natural-language questions about the contract. Built for the **DEV Weekend Challenge 2026 — Earth Day Edition**, targeting the **Snowflake Cortex** sponsor category.

- **Cortex Analyst** drives natural-language Q&A (semantic model → SQL → real rows).
- **Cortex Complete** (`llama3.3-70b`) writes the mine-memorial prose and the 2–3 sentence summary under the national density map — both carry a degraded flag so template fallbacks never sit under a Cortex byline.
- **H3 hexbin geospatial** + **Marketplace** (EPA Clean Air Markets) are used natively inside Snowflake — no extraction, no ETL away.

> **For challenge judges:** the fastest tour is the [user journey diagram](#user-journey) (what the site does), the [system diagram](#system-architecture) (how Cortex is used), and [`PRD.md`](./PRD.md) §1–3 (why it exists).
>
> **For new devs:** skim the [repo map](#repo-map), then [`AGENTS.md`](./AGENTS.md) for coding rules and Snowflake conventions before touching anything.

---

## User Journey

Scroll-driven dark editorial layout. Each numbered section owns one beat.

```mermaid
flowchart TB
    H["N° 01 — Hero<br/><i>Locate</i><br/>address input · Google Places<br/>geolocation button"]
    P["N° 02 — PlantReveal<br/><i>The contract</i><br/>mine name · operator · tonnage<br/>MSHA safety ledger"]
    M["N° 03 — MapSection<br/><i>The route</i><br/>animated mine → plant → meter<br/>single SVG path · pulse bead<br/>eGRID label on user pin"]
    D["N° 04 — H3Density<br/><i>The seam</i><br/>hexbin cluster · rust→ash<br/>Cortex summary byline"]
    C["N° 05 — CortexChat<br/><i>Ask the data</i><br/>chips · free-text question<br/>visible SQL per turn"]
    T["N° 06 — Ticker<br/><i>While you read</i><br/>live tonnage counter<br/>emissions anchor block"]

    H --> P --> M --> D --> C --> T

    click H "frontend/src/lib/sections/Hero.svelte"
    click P "frontend/src/lib/sections/PlantReveal.svelte"
    click M "frontend/src/lib/sections/MapSection.svelte"
    click D "frontend/src/lib/sections/H3Density.svelte"
    click C "frontend/src/lib/sections/CortexChat.svelte"
    click T "frontend/src/lib/sections/Ticker.svelte"
```

Every section is wrapped in `SectionRail.svelte` (vertical left-gutter N° / rule / rotated label), so the page reads as one magazine spread.

---

## System Architecture

Three tiers: SvelteKit in the browser, FastAPI on Cloud Run, Snowflake as the data + AI spine. Snowflake does the work Snowflake is best at — warehouse, Cortex, H3 geospatial, Marketplace — and the backend is thin.

```mermaid
flowchart LR
    subgraph CLIENT["Browser · SvelteKit + Vite"]
        direction TB
        HERO[Hero] --> TRACE[trace →]
        TRACE --> RESULT[PlantReveal · MapSection<br/>H3Density · CortexChat · Ticker]
    end

    subgraph API["Cloud Run · FastAPI + Python 3.12"]
        direction TB
        MINE["POST /mine-for-me<br/>subregion → mine + prose + stats"]
        ASK["POST /ask<br/>question → answer + SQL + rows"]
        H3["GET /h3-density<br/>hexbins + totals + Cortex summary"]
        EMIT["GET /emissions/{plant}<br/>CO₂ · SO₂ · NOₓ"]
        FB[(Fallback JSON<br/>19 subregions)]
    end

    subgraph SNOW["Snowflake · UNEARTHED_DB"]
        direction TB
        RAW[(6 RAW tables<br/>MSHA + EIA)]
        MRT[(2 MRT tables<br/>MINE_PLANT_FOR_SUBREGION<br/>EMISSIONS_BY_PLANT)]
        VIEWS[(2 views)]
        CA[["Cortex Analyst<br/>semantic model YAML"]]
        CC[["Cortex Complete<br/>llama3.3-70b"]]
        H3FN[["H3 Geospatial<br/>H3_LATLNG_TO_CELL_STRING"]]
        MKT[["Marketplace<br/>EPA Clean Air Markets"]]
        MRT --> CC
        RAW --> MRT
        MKT -.->|CTAS| MRT
        VIEWS --> CA
    end

    TRACE -->|subregion_id| MINE
    RESULT -->|question| ASK
    RESULT -->|GET| H3
    RESULT -->|GET| EMIT

    MINE --> MRT
    MINE -.->|Snowflake down| FB
    ASK --> CA
    CA -->|SQL via READONLY_ROLE| VIEWS
    H3 --> H3FN
    H3 --> CC
    EMIT --> MRT

    style CA fill:#29b5e8,color:#fff
    style CC fill:#29b5e8,color:#fff
    style H3FN fill:#29b5e8,color:#fff
    style MKT fill:#29b5e8,color:#fff
    style MRT fill:#29b5e8,color:#fff
    style RAW fill:#29b5e8,color:#fff
    style VIEWS fill:#29b5e8,color:#fff
    style FB fill:#6e6359,color:#fff
```

**Security boundary on `/ask`:** every Cortex-Analyst-generated SQL is validated (SELECT-only, single-statement) and executed through the least-privilege `UNEARTHED_READONLY_ROLE`, capped at `STATEMENT_TIMEOUT_IN_SECONDS=10`, `ROWS_PER_RESULTSET=500`, and a hard `fetchmany(500)`. See [`system-diagram.md`](./system-diagram.md) for the full security flow.

---

## Repo Map

```mermaid
flowchart LR
    ROOT["unearthed/"]

    ROOT --> APP["app/ <i>FastAPI backend</i>"]
    APP --> APP_MAIN["main.py — endpoints, middleware, caches"]
    APP --> APP_SF["snowflake_client.py — key-pair auth, pool, role scoping"]
    APP --> APP_PR["prose_client.py — Cortex Complete prose + H3 summary"]
    APP --> APP_MOD["models.py — Pydantic I/O schemas"]
    APP --> APP_CFG["config.py — env + secrets"]

    ROOT --> FE["frontend/ <i>SvelteKit + Vite</i>"]
    FE --> FE_SEC["src/lib/sections/ — Hero · PlantReveal · MapSection · H3Density · CortexChat · Ticker"]
    FE --> FE_CMP["src/lib/components/ — SectionRail"]
    FE --> FE_LIB["src/lib/ — api.js · geo.js · maps.js"]
    FE --> FE_E2E["e2e/ — Playwright specs + fixtures"]

    ROOT --> TESTS["tests/ <i>pytest</i>"]
    TESTS --> T_UNIT["unit/ — pure function coverage"]
    TESTS --> T_INT["integration/ — TestClient + mocked Snowflake"]
    TESTS --> T_PERF["performance/ — request-budget guards"]

    ROOT --> ASSETS["assets/ — eGRID GeoJSON, fallback JSONs, semantic model YAML"]
    ROOT --> STATIC["static/ — public frontend assets"]
    ROOT --> SCRIPTS["scripts/ — generate_fallbacks, data loaders"]

    ROOT --> DOCS["docs"]
    DOCS --> D_PRD["PRD.md — product spec"]
    DOCS --> D_AGT["AGENTS.md — coding + Snowflake conventions"]
    DOCS --> D_SYS["system-diagram.md — runtime + data-load + security flows"]
    DOCS --> D_CLD["CLAUDE.md — short brief for AI collaborators"]

    ROOT --> OPS["ops"]
    OPS --> O_DF["Dockerfile — multi-stage Cloud Run image"]
    OPS --> O_MK["Makefile — install · dev · server · test · lhci"]
    OPS --> O_PY["pyproject.toml + uv.lock"]
    OPS --> O_PN["frontend/package.json + pnpm-lock.yaml"]

    style APP fill:#1a1a1a,color:#e8e0d4
    style FE fill:#1a1a1a,color:#e8e0d4
    style TESTS fill:#1a1a1a,color:#e8e0d4
    style DOCS fill:#be573b,color:#fff
    style OPS fill:#5a7a5a,color:#fff
```

---

## Tech Stack

| Layer | Stack |
|---|---|
| Frontend | SvelteKit 2 + Svelte 5 runes · Vite · Google Maps JS API (dynamic `importLibrary`) · Google Places API (New) |
| Backend | Python 3.12 · FastAPI · `uv` · key-pair Snowflake auth · thread-local connection pool |
| Data + AI | Snowflake Cortex Analyst (NL→SQL) · Cortex Complete (`llama3.3-70b`) · H3 geospatial · Marketplace (EPA CAM) |
| Deploy | Google Cloud Run · Secret Manager · multi-stage Docker |
| Testing | `pytest` (unit / integration / perf) · `vitest` + `@testing-library/svelte` · Playwright · Lighthouse CI (a11y=1.0, SEO=1.0, BP≥0.98, perf≥0.90) |
| Lint/Format | `ruff` (line-length 100) · `pnpm lint` |

---

## Quickstart

```sh
make install          # backend (uv) + frontend (pnpm)
cp .env.example .env  # fill in Snowflake + Google Maps keys
make server           # backend on :8001
make dev              # frontend on :5173 (proxies /api to backend)
```

Then open http://localhost:5173.

### Required environment

`.env.example` documents every variable. At minimum:

- **Snowflake (backend):** `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY_PATH`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_ROLE` (`UNEARTHED_APP_ROLE`), `SNOWFLAKE_READONLY_ROLE` (`UNEARTHED_READONLY_ROLE`).
- **Google Maps (frontend):** `VITE_GOOGLE_MAPS_KEY` — restrict to `http://localhost:5173` + your production origin, enable Maps JS + Places API (New).

Snowflake schema provisioning (roles, tables, MRT builds, Marketplace subscription) is covered in [`AGENTS.md`](./AGENTS.md) §3.

---

## Testing

```sh
make test-ci          # pytest (no e2e marker) + vitest + playwright — CI safe
make test             # everything, including backend e2e + Lighthouse CI
make test-cov         # pytest with coverage report
make lint             # ruff check + format --check
```

The test matrix:

| Suite | Tool | What it covers |
|---|---|---|
| `tests/unit/` | pytest | Pure functions — SQL validation, prose fallback, stats extraction, suggestions, model validation |
| `tests/integration/` | pytest + FastAPI TestClient | Endpoints with mocked Snowflake — happy path, edge cases, CORS, 405s, degraded paths |
| `tests/performance/` | pytest | Request-budget guards (response size, lookup time) |
| `frontend/src/**/*.test.js` | vitest + jsdom | Components + helpers in isolation — PlantReveal (+ emissions), CortexChat, Ticker, SectionRail, api client (+ edge), geo helpers (+ edge), reveal state machine |
| `frontend/e2e/` | Playwright | Share-URL replay, pushState history, editorial rail integrity, error-state rendering, Google Maps runtime (MapSection + H3Density) against a behavioral `google.maps` stub |
| `frontend/lighthouserc.cjs` | `@lhci/cli` | a11y=1.0, SEO=1.0, best-practices≥0.98, perf≥0.90 |

---

## Where Things Live

- **Product spec + success criteria:** [`PRD.md`](./PRD.md)
- **Coding rules, Snowflake standards, naming conventions:** [`AGENTS.md`](./AGENTS.md) — read before writing code.
- **Runtime / data-load / security flow diagrams:** [`system-diagram.md`](./system-diagram.md)
- **Short brief for AI pair programmers:** [`CLAUDE.md`](./CLAUDE.md)

---

## License

Polyform Shield 1.0.0 — see [`LICENSE`](./LICENSE).

Built with care and with the help of Claude (Anthropic) for the DEV Weekend Challenge 2026 — Earth Day Edition.
