# AGENTS.md — Coding Rules & Conventions

These rules govern all code written in this repository. Read fully before contributing.

---

## 1. Project Constraints

- **Deadline:** 2026-04-20 06:59 UTC. Every decision optimizes for shipping, not elegance.
- **No user accounts, no persistence, no login.** Every visit is stateless.
- **US only.** MSHA + EIA data is US-specific.
- **No carbon calculator.** Out of scope.
- **No appliance-level physics simulation.** Appliance toggles use fixed coefficients only.
- **No real-time EIA API.** We use the 2024 annual release (published 2025) as static data.

## 2. Architecture Rules

### Endpoints

The backend exposes these FastAPI endpoints:

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/mine-for-me` | POST | `{subregion_id}` | Mine + plant data, Cortex Complete prose, coords |
| `/ask` | POST | `{question, subregion_id?}` | Cortex Analyst answer + SQL + results |
| `/h3-density` | GET | `?resolution=4&state=WV` | H3 hexbin cells + unfiltered registry `totals` (`total`/`active`/`abandoned`) + Cortex-generated `summary` (with `summary_degraded` flag when template fallback fires) |
| `/emissions/{plant}` | GET | plant name | CO2/SO2/NOx from EPA Marketplace data |

Subregion IDs validated with `^[A-Za-z0-9]{2,10}$`. Unknown subregions return **404**.

### Frontend

- SvelteKit (Vite) with static adapter. Scroll-driven typographic sections.
- Google Maps JS API for satellite map with animated flow lines.
- Chat UI for Cortex Analyst: Svelte component with chips and transcript.
- Geolocation: Browser API with permission prompt. Point-in-polygon against bundled eGRID GeoJSON runs client-side.
- State-picker dropdown as fallback when geolocation is denied or user is outside US.
- Dev: `make dev` (frontend :5173) + `make server` (backend :8001). Vite proxies API calls.

### Backend

- Python 3.12 / FastAPI. Dependencies managed via `pyproject.toml` + `uv`.
- Snowflake connector: `snowflake-connector-python` with key-pair auth (preferred) or password auth (opt-in via `ALLOW_PASSWORD_AUTH=true` for local dev). Private key stored as Cloud Run secret.
- Two Snowflake roles: `UNEARTHED_APP_ROLE` (general queries), `UNEARTHED_READONLY_ROLE` (Analyst SQL execution — SELECT-only grants).
- Cortex Analyst: REST API via `/ask` endpoint. Generated SQL is validated (SELECT-only, no multi-statement, no DML/DDL keywords) and executed under the read-only role with a 500-row cap and 10-second statement timeout.
- Default suggestions (from 5 verified queries) are always returned in `/ask` responses.
- Docs/OpenAPI disabled by default (set `ENABLE_DOCS=true` for local dev). CORS origins configurable via `CORS_ORIGINS` env var.

### Degraded Mode

Snowflake is the sole external dependency. Fallbacks:

| Dependency Down | Fallback |
|---|---|
| Snowflake | Return cached static JSON per-subregion (19 files) with `degraded: true` |
| Snowflake + no fallback | Return **404** (no fake placeholder data) |
| Cortex Analyst | Display fallback message with default suggestions, reveal page continues normally |
| Analyst SQL execution | Set `error` field with explicit message; answer text still returned |
| Cortex Complete (H3 summary) | Template fallback returned with `summary_degraded: true`; frontend hides the "Cortex, on this map" byline so template prose is never mis-attributed to the model. Fallbacks are **not cached** so recovery shows up on the next request. |

Never let a single API failure break the reveal page.

## 3. Snowflake Rules

### Naming Conventions

All Snowflake identifiers use **UPPERCASE with underscores**.

| Object | Pattern | Example |
|---|---|---|
| Database | `UNEARTHED_DB` | `UNEARTHED_DB` |
| Schema | Layer prefix: `RAW`, `INT`, `MRT` | `RAW`, `MRT` |
| Table (raw) | `[SOURCE]_[ENTITY]` | `MSHA_MINES`, `EIA_923_FUEL_RECEIPTS` |
| View | `V_[NAME]` | `V_MINE_FOR_PLANT`, `V_MINE_FOR_SUBREGION` |
| Warehouse | `UNEARTHED_[PURPOSE]_WH` | `UNEARTHED_APP_WH` |
| Stage | `[NAME]_STG` | `RAW_CSV_STG` |
| File Format | `[NAME]_FF` | `PIPE_DELIMITED_CSV_FF` |

### Schema Layout

```
UNEARTHED_DB
├── RAW          — cleaned CSVs, key columns cast to native types
│   ├── MSHA_MINES
│   ├── MSHA_QUARTERLY_PRODUCTION
│   ├── MSHA_ACCIDENTS           (fatalities, injuries, narratives)
│   ├── EIA_923_FUEL_RECEIPTS
│   ├── EIA_860_PLANTS
│   └── PLANT_SUBREGION_LOOKUP
└── MRT          — consumption-ready views and tables
    ├── V_MINE_FOR_PLANT        (mine rankings per plant)
    ├── V_MINE_FOR_SUBREGION    (mine rankings per eGRID subregion)
    ├── MINE_PLANT_FOR_SUBREGION (materialized: top mine + plant per subregion, 19 rows)
    └── EMISSIONS_BY_PLANT      (pre-aggregated EPA CO2/SO2/NOx per coal facility)

SNOWFLAKE_PUBLIC_DATA_FREE       — Marketplace (free, source for EMISSIONS_BY_PLANT)
└── PUBLIC_DATA_FREE
    ├── EPA_CAM_PLANT_UNIT_INDEX (plant emissions metadata)
    └── EPA_CAM_TIMESERIES       (CO2/SO2/NOx hourly + quarterly, 2.2B rows)
```

### SQL Standards

- **Never use `SELECT *`** — always specify columns. Snowflake is columnar; fewer columns = less data scanned.
- **No `ORDER BY` in CTEs or subqueries** — only at the final result set.
- **Use `QUALIFY`** to filter window function results directly instead of wrapping in a subquery.
- **Avoid functions in WHERE clauses** — they degrade predicate pushdown and partition pruning.
- **Match data types on join columns** — no implicit type conversions.
- **Trailing wildcards only** — `LIKE 'abc%'` is fine; `LIKE '%abc'` is not.
- **Deduplicate join keys before joining** to prevent row explosion.
- **Use CTEs over nested subqueries** for readability.

### Warehouse Management

- Use **XS warehouse** (`UNEARTHED_APP_WH`) for all queries. Do not upsize without profiling first.
- **Auto-suspend: 60 seconds.** Per-second billing makes aggressive suspension free.
- **Auto-resume: enabled.**
- One warehouse for this project. No need for workload isolation at this scale.

### Cortex AI Usage

Two Cortex features in use:

| Feature | Purpose | Where Used |
|---|---|---|
| Cortex Analyst | NL-to-SQL via semantic model YAML | `/ask` endpoint, runtime user questions |
| Cortex Complete (`llama3.3-70b`) | Short safety prose from MSHA_ACCIDENTS stats | `/mine-for-me` response, in-process cache per subregion |
| Cortex Complete (`llama3.3-70b`) | 2-3 sentence explanation of the H3 density map | `/h3-density` `summary` field, in-process cache per scope (state / national) |

- **Cortex Analyst semantic model:** Checked into repo as YAML. Covers only the 4-5 chip question patterns — not open-ended.
- **Cortex Complete model:** `llama3.3-70b` via `SNOWFLAKE.CORTEX.COMPLETE()`. Used in `prose_client.py` for mine narratives and `snowflake_client.summarize_analyst_results` for SQL result explanations.
- **Cortex Complete prompts:** Injuries lead, fatalities land second — see `app/prose_client.py`. H3 summary prompt leads with what the reader sees, then the scale. Both strip outer quotes before returning.
- **Honest attribution:** Both `generate_prose` and `generate_h3_summary` return `(text, degraded)`. Only Cortex output is cached — template fallbacks are not, so a recovered model shows up on the next request and the "Cortex, on this map" / "Cortex, reading the record" bylines never sit over template prose.
- **Honest totals:** `/h3-density` runs a second unfiltered count query and returns `totals` alongside the hex cells. The hex SQL drops null-coord rows, ocean outliers, and small clusters for legibility; the `totals` payload does none of that so the Cortex summary and the frontend legend both claim "X mines on record" against MSHA's full registry, not the hexes visible at this resolution. `generate_h3_summary` accepts a `role` kwarg so the readonly endpoint can scope the Cortex connection to `UNEARTHED_READONLY_ROLE` instead of the default app role.

### Snowflake-Native Features Beyond Cortex

Two endpoints lean on Snowflake's built-in geospatial / Marketplace story:

| Endpoint | Snowflake capability | UI |
|---|---|---|
| `/h3-density` | `H3_LATLNG_TO_CELL_STRING` for hexbin aggregation | `H3Density.svelte` — national footprint section |
| `/emissions/{plant}` | EPA Clean Air Markets via Snowflake Marketplace (free) | Inline card on `PlantReveal.svelte` |

### Security

- **Key-pair auth** preferred for Snowflake (password auth requires explicit `ALLOW_PASSWORD_AUTH=true`). Private key stored as Cloud Run Secret Manager secret.
- **Never hardcode credentials** in source code, environment files, or SQL scripts.
- **Two roles:** `UNEARTHED_APP_ROLE` (SELECT on RAW + MRT, Cortex function access) for data queries, `UNEARTHED_READONLY_ROLE` (SELECT on RAW + MRT) for executing Analyst-generated SQL. Both roles have USAGE on `UNEARTHED_APP_WH`.
- **SQL validation:** Analyst SQL is regex-validated before execution — must start with SELECT/WITH, no DML/DDL keywords. **Semicolons:** Cortex Analyst appends a trailing semicolon to generated SQL; `execute_analyst_sql` strips it before validation. After stripping, any remaining semicolons (multi-statement) are rejected. Defense-in-depth on top of the read-only role.
- **Input validation:** Subregion IDs validated with `^[A-Za-z0-9]{2,10}$` to prevent path traversal. Fallback file paths resolved and verified under `assets/fallback/`.
- **XS warehouse only.** The free trial has $400 of credits. Do not burn them on oversized warehouses.
- Do not use `ACCOUNTADMIN` role for application queries.

### Performance

- Queries against `V_MINE_FOR_SUBREGION` must return in **under 2 seconds** on XS warehouse.
- Leverage Snowflake's **24-hour result cache** — identical queries return instantly with no compute cost.
- **RAW tables are pre-cleaned** — embedded CSV quotes stripped, key columns cast to native types (MINE_ID → NUMBER, LATITUDE/LONGITUDE → DOUBLE, QUANTITY → NUMBER). Use column values directly — no `REPLACE()`, `TRY_TO_NUMBER()`, or `TRY_TO_DOUBLE()` needed.
- **Emissions are pre-aggregated** — `MRT.EMISSIONS_BY_PLANT` (240 rows) replaces the 2.2B-row EPA_CAM_TIMESERIES join. Query the MRT table, not the Marketplace tables directly.
- **Mine-plant lookup is materialized** — `MRT.MINE_PLANT_FOR_SUBREGION` (19 rows) pre-computes the top mine + plant per eGRID subregion. `/mine-for-me` reads this single table instead of joining 4 RAW tables through views.
- **Session-level guards** — every connection sets `STATEMENT_TIMEOUT_IN_SECONDS = 10` and `ROWS_PER_RESULTSET = 500` via `ALTER SESSION` at creation time. These cap runaway Analyst SQL and protect credit burn. `execute_analyst_sql` also enforces a hard 500-row cap via `fetchmany(500)`.
- **Bounded in-memory caches** — `_emissions_cache` and `_mine_context` are LRU `OrderedDict`s capped at 256 entries. Prose and H3 summary caches are bounded by their fixed key spaces (19 subregions, ~50 states). All caches reset on process restart.
- **Prose prewarm** — gated behind `PREWARM_PROSE=true` env var (default off). When enabled, a background thread pre-warms prose for all 19 fallback subregions at startup. Disabled by default to avoid multiplying Cortex costs on autoscaled Cloud Run instances.

## 4. Frontend Rules

### Map (Google Maps JavaScript API)

- Loader lives in `frontend/src/lib/maps.js` — one idempotent script tag shared by `MapSection` (mine→plant→meter) and `H3Density` (hexbin), with a 15s watchdog and poll-for-ready so a cached script can't hang the promise forever.
- `DARK_STATE_STYLES` + `MAP_COLORS` are the single source of truth for both maps. No cloud-registered `mapId` — that would silently disable the local style array.
- `MapSection` arc: mine → plant → your meter, one rust color, animated dot rides the geodesic. Labels fan out (above / below / side) to avoid InfoWindow stacking.
- `H3Density`: resolution-5 hexbins, bigger dot = more mines, rust→ash gradient for active→abandoned. SQL filters null-island and ocean outliers at the query layer.
- All three pins and labels must be readable on mobile (>= 375px wide) without horizontal scroll.

### Section chrome (editorial unification)

**One title treatment for the whole page.** `SectionRail.svelte` is the canonical wrapper — every scroll section uses it. The component owns:

- The left-rail number + label (`N° 02 / Your coal`) — chrome, not content.
- Canonical `h2`/`h3` typography (serif, clamped, `em` accent) — do NOT re-declare in sections. If a title doesn't match, it's a bug in the section, not a license to override.
- The `.sub` subtitle pattern.
- The `.cortex-note` block (rust border-left) signaling Cortex-written text.
- The **three-line anchor pattern** via `:global(.anchor-primary)` + `:global(.anchor-secondary)`: big value / serif plain-English primary / mono uppercase tag. Used by PlantReveal cards, the land-disturbed block, the emissions panel, and the H3 tallies. **Do not re-declare these per section.** If you need a larger closing beat (Ticker), define a distinct class — don't shadow the canonical one.

### Share URL

- Structure: `/?m=SRVC` (eGRID subregion ID, not mine slug).
- Open Graph tags updated client-side with mine name and hook text after reveal.
- Share URL skips geolocation and jumps straight to that subregion's reveal.

## 5. Error Handling Philosophy

- **Cortex Analyst misfires:** Display the generated SQL plus "I could not answer that confidently." Honesty > hallucinated numbers.
- **Out-of-scope questions:** Semantic model guardrails reject. UI offers chip suggestions instead.
- **Snowflake failure:** Cached static JSON fallback per-subregion.
- **Location outside US:** Graceful message + state picker. Never a dead end.
- **No coal in user's subregion:** Show the mine supplying the nearest coal-burning plant in their eGRID subregion, or fall back to national median contract.

## 6. Code Quality & Maintenance

- **No backwards-compatibility hacks.** Do not rename unused variables to `_var`, re-export removed types, add `// removed` comments, or create shims for deleted functionality. If something is unused, delete it completely.
- **No temporary solutions or quick fixes.** Every line of code merged must be production-intent. Do not add TODO-gated workarounds, feature flags for half-finished work, or "fix later" stubs. If a proper solution cannot be implemented now, scope the work down — do not ship a placeholder.

## 7. File & Code Conventions

- **Python:** Python 3.12. Follow PEP 8 enforced by `ruff`. Type hints on all function signatures. Use `async def` only if genuinely async; sync is fine for Snowflake connector and Cortex Analyst REST calls.
- **Dependencies:** `pyproject.toml` with `uv`. Dev deps in `[dependency-groups]`. Run `uv sync` to install, `make lint` / `make fmt` for ruff, `make test` for pytest.
- **JavaScript/Svelte:** SvelteKit with Vite. Svelte 5 runes mode. No TypeScript (speed over safety for a weekend build).
- **SQL:** Uppercase keywords, lowercase only inside string literals. One statement per file when possible. Comment the "why," not the "what."
- **Secrets:** Never committed. Use `.env` locally (gitignored), Secret Manager in Cloud Run.
- **Static assets:** Checked into repo under an `assets/` directory. eGRID GeoJSON, hero images, fallback JSON (19 subregions), semantic model YAML.
- **Docker:** Non-root user, `.dockerignore` excludes secrets/tests/dev files. Deps installed via `uv sync --frozen --no-dev` from `pyproject.toml` + `uv.lock`.

## 8. Snowflake MCP Server

For local development with Claude Code, use the **official Snowflake MCP server** from Snowflake-Labs:

- **Repo:** https://github.com/Snowflake-Labs/mcp
- **Install:** `uvx snowflake-labs-mcp --service-config-file snowflake-mcp-config.yaml`
- **Capabilities:** Cortex Search, Cortex Analyst, SQL execution, object management
- **Auth:** Key-pair, OAuth, SSO, or user/password via Snowflake Python Connector
- **Transport:** stdio for local dev, streamable-http for container deployment

Alternative (simpler, read-only): https://github.com/isaacwasserman/mcp-snowflake-server
- Install: `npx -y @smithery/cli install mcp_snowflake_server --client claude`
- Good for schema exploration and read queries during development

The checked-in config (`snowflake-mcp-config.yaml`) is read-only by default. For ETL or one-time data loading, use a local untracked override — do not commit write-enabled configs.

## 9. Semantic Model (Cortex Analyst)

The semantic model YAML must be checked into the repo and cover these supported question patterns:

1. "How much has [mine] produced since [year]?"
2. "What other plants buy from [operator]?"
3. "Is [mine] still active?"
4. "What is the total tonnage for [subregion] in [year]?"
5. "Who is the largest coal supplier in [state]?"

Any question outside these patterns should be gracefully rejected with chip suggestions. The YAML covers the 5 raw tables (MSHA_MINES, MSHA_QUARTERLY_PRODUCTION, EIA_923_FUEL_RECEIPTS, EIA_860_PLANTS, PLANT_SUBREGION_LOOKUP). MRT views are not included — they serve the `/mine-for-me` endpoint via hand-written SQL, not Cortex Analyst. Keep the semantic model minimal — scope creep is the #1 timeline risk identified in the PRD.
