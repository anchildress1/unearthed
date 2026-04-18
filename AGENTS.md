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

The backend exposes exactly two FastAPI endpoints:

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/mine-for-me` | POST | `{subregion_id}` (regex: `[A-Za-z0-9]{2,10}`) | `{mine, plant, tons, prose, mine_coords, plant_coords, degraded}` or 404 |
| `/ask` | POST | `{question, subregion_id?}` | `{answer, sql?, error?, suggestions?, results?}` |

Subregion IDs are validated with `^[A-Za-z0-9]{2,10}$` — rejects path traversal, special chars.
Unknown subregions return **404**, not placeholder data.

Do not add endpoints without updating the PRD.

### Frontend

- Vanilla JS (no framework). MapLibre GL JS for the map.
- Chat UI for Cortex Analyst: plain HTML form + chip buttons + transcript div. No component library.
- Geolocation: Browser API with permission prompt. Point-in-polygon against bundled eGRID GeoJSON runs client-side.
- State-picker dropdown as fallback when geolocation is denied or user is outside US.

### Backend

- Python 3.12 / FastAPI. Dependencies managed via `pyproject.toml` + `uv`.
- Snowflake connector: `snowflake-connector-python` with key-pair auth (preferred) or password auth (opt-in via `ALLOW_PASSWORD_AUTH=true` for local dev). Private key stored as Cloud Run secret.
- Two Snowflake roles: `UNEARTHED_APP_ROLE` (general queries), `UNEARTHED_READONLY_ROLE` (Analyst SQL execution — SELECT-only grants).
- Gemini calls cached per-subregion at the API layer as `(prose, degraded)` tuples (TTL: until next deploy). Do not call Gemini twice for the same subregion in the same deployment.
- Cortex Analyst: REST API via `/ask` endpoint. Generated SQL is validated (SELECT-only, no multi-statement, no DML/DDL keywords) and executed under the read-only role with a 500-row cap and 10-second statement timeout.
- Default suggestions (from 5 verified queries) are always returned in `/ask` responses.
- Docs/OpenAPI disabled by default (set `ENABLE_DOCS=true` for local dev). CORS origins configurable via `CORS_ORIGINS` env var.

### Degraded Mode

Both external dependencies (Snowflake, Gemini) have fallbacks:

| Dependency Down | Fallback |
|---|---|
| Snowflake | Return cached static JSON per-subregion (19 files) with `degraded: true` |
| Snowflake + no fallback | Return **404** (no fake placeholder data) |
| Gemini | Return pre-rendered template with data interpolated, `degraded: true` |
| Cortex Analyst | Display fallback message with default suggestions, reveal page continues normally |
| Analyst SQL execution | Set `error` field with explicit message; answer text still returned |

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
├── RAW          — raw ingested CSVs/XLSX, untransformed
│   ├── MSHA_MINES
│   ├── MSHA_QUARTERLY_PRODUCTION
│   ├── EIA_923_FUEL_RECEIPTS
│   ├── EIA_860_PLANTS
│   └── PLANT_SUBREGION_LOOKUP
├── INT          — cleaned, joined, filtered to coal
│   └── (intermediate transforms)
└── MRT          — consumption-ready views
    ├── V_MINE_FOR_PLANT        (mine rankings per plant)
    └── V_MINE_FOR_SUBREGION    (mine rankings per eGRID subregion + Cortex summary)
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

Two distinct Cortex features in use — do not confuse them:

| Feature | Purpose | Where Used |
|---|---|---|
| `SNOWFLAKE.CORTEX.COMPLETE` | LLM text generation inline in SQL | Materialized summary column on `V_MINE_FOR_SUBREGION`, populated at build time |
| Cortex Analyst | NL-to-SQL via semantic model YAML | `/ask` endpoint, runtime user questions |

- **COMPLETE model:** Start with `llama3-8b` for cost/speed. Switch to `mistral-large` only if prose quality is inadequate.
- **Cortex Analyst semantic model:** Checked into repo as YAML. Covers only the 4-5 chip question patterns — not open-ended. If Analyst is flaky by Sunday noon, degrade to COMPLETE with hand-written SQL templates.
- **COMPLETE column generation:** Run during ETL/table load (Saturday), not at query time. ~500 mines x 1 call each.

### Security

- **Key-pair auth** preferred for Snowflake (password auth requires explicit `ALLOW_PASSWORD_AUTH=true`). Private key stored as Cloud Run Secret Manager secret.
- **Never hardcode credentials** in source code, environment files, or SQL scripts.
- **Two roles:** `UNEARTHED_APP_ROLE` for data queries, `UNEARTHED_READONLY_ROLE` (SELECT-only grants on MRT schema) for executing Analyst-generated SQL.
- **SQL validation:** Analyst SQL is regex-validated before execution — must start with SELECT/WITH, no semicolons (multi-statement), no DML/DDL keywords. Defense-in-depth on top of the read-only role.
- **Input validation:** Subregion IDs validated with `^[A-Za-z0-9]{2,10}$` to prevent path traversal. Fallback file paths resolved and verified under `assets/fallback/`.
- **XS warehouse only.** The free trial has $400 of credits. Do not burn them on oversized warehouses.
- Do not use `ACCOUNTADMIN` role for application queries.

### Performance

- Queries against `V_MINE_FOR_SUBREGION` must return in **under 2 seconds** on XS warehouse.
- Leverage Snowflake's **24-hour result cache** — identical queries return instantly with no compute cost.
- No clustering keys needed at this data scale (~500 mines after coal filter).
- The Cortex COMPLETE summary column must have **no nulls** — validate after ETL.

## 4. Gemini Rules

- Use **Gemini Flash** tier to minimize cost and latency.
- Prompt input must include: `{mine_name, mine_operator, mine_county, mine_state, mine_type, plant_name, plant_operator, tons_latest_year, tons_year, subregion_id}`.
- Output: 3-5 sentences. Names the mine, the plant, the operator, the tonnage. Grief-coded register. No cheerful hedging.
- **Cache per-subregion** at the API layer. Same subregion within the same deployment = no second Gemini call.

## 5. Frontend Rules

### Map (MapLibre GL)

- Zoom sequence: user location -> power plant -> source mine. Arc line drawn between all three points.
- Sequence must complete within **8 seconds** from payload receipt to final zoom.
- All three pins and labels must be readable on mobile (>= 375px wide) without horizontal scroll.

### Hero Images

- Exactly 2 images: one surface mine, one underground mine. Routed by mine type.
- **Pre-1980 public domain only.** Library of Congress or Wikimedia with clear provenance.
- No recent photography. No named living individuals.

### Share URL

- Structure: `/?m=hobet-wv` (or similar slug).
- Open Graph tags populated with mine name, share image, and 1-sentence hook.
- Share URL skips geolocation and jumps straight to that mine's reveal.

## 6. Error Handling Philosophy

- **Cortex Analyst misfires:** Display the generated SQL plus "I could not answer that confidently." Honesty > hallucinated numbers.
- **Out-of-scope questions:** Semantic model guardrails reject. UI offers chip suggestions instead.
- **Gemini failure:** Pre-rendered template with data interpolated. Never show a blank or broken reveal.
- **Snowflake failure:** Cached static JSON fallback per-subregion.
- **Location outside US:** Graceful message + state picker. Never a dead end.
- **No coal in user's subregion:** Show the mine supplying the nearest coal-burning plant in their eGRID subregion, or fall back to national median contract.

## 7. Code Quality & Maintenance

- **No backwards-compatibility hacks.** Do not rename unused variables to `_var`, re-export removed types, add `// removed` comments, or create shims for deleted functionality. If something is unused, delete it completely.
- **No temporary solutions or quick fixes.** Every line of code merged must be production-intent. Do not add TODO-gated workarounds, feature flags for half-finished work, or "fix later" stubs. If a proper solution cannot be implemented now, scope the work down — do not ship a placeholder.

## 8. File & Code Conventions

- **Python:** Python 3.12. Follow PEP 8 enforced by `ruff`. Type hints on all function signatures. Use `async def` only if genuinely async; sync is fine for Snowflake connector and Cortex Analyst REST calls.
- **Dependencies:** `pyproject.toml` with `uv`. Dev deps in `[dependency-groups]`. Run `uv sync` to install, `make lint` / `make fmt` for ruff, `make test` for pytest.
- **JavaScript:** Vanilla JS, no transpilation. ES modules. No TypeScript for this project (speed over safety for a weekend build).
- **SQL:** Uppercase keywords, lowercase only inside string literals. One statement per file when possible. Comment the "why," not the "what."
- **Secrets:** Never committed. Use `.env` locally (gitignored), Secret Manager in Cloud Run.
- **Static assets:** Checked into repo under an `assets/` directory. eGRID GeoJSON, hero images, fallback JSON (19 subregions), semantic model YAML.
- **Docker:** Non-root user, `.dockerignore` excludes secrets/tests/dev files. Deps installed via `uv sync --frozen --no-dev` from `pyproject.toml` + `uv.lock`.

## 9. Snowflake MCP Server

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

## 10. Semantic Model (Cortex Analyst)

The semantic model YAML must be checked into the repo and cover these supported question patterns:

1. "How much has [mine] produced since [year]?"
2. "What other plants buy from [operator]?"
3. "Is [mine] still active?"
4. "What is the total tonnage for [subregion] in [year]?"
5. "Who is the largest coal supplier in [state]?"

Any question outside these patterns should be gracefully rejected with chip suggestions. The YAML covers the 5 raw tables (MSHA_MINES, MSHA_QUARTERLY_PRODUCTION, EIA_923_FUEL_RECEIPTS, EIA_860_PLANTS, PLANT_SUBREGION_LOOKUP). MRT views are not included — they serve the `/mine-for-me` endpoint via hand-written SQL, not Cortex Analyst. Keep the semantic model minimal — scope creep is the #1 timeline risk identified in the PRD.
