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
| `/mine-for-me` | POST | `{subregion_id}` | `{mine, plant, tons, prose, user_coords, mine_coords, plant_coords, degraded?}` |
| `/ask` | POST | `{question, subregion_id?}` | `{answer, sql?, error?}` |

Do not add endpoints without updating the PRD.

### Frontend

- Vanilla JS (no framework). MapLibre GL JS for the map. PixiJS for the particle overlay.
- Stacked-canvas approach: MapLibre and PixiJS each own their own canvas, layered via CSS z-index.
- Chat UI for Cortex Analyst: plain HTML form + chip buttons + transcript div. No component library.
- Geolocation: Browser API with permission prompt. Point-in-polygon against bundled eGRID GeoJSON runs client-side.
- State-picker dropdown as fallback when geolocation is denied or user is outside US.

### Backend

- Python 3.11+ / FastAPI. Match the "dragon smelter" project pattern.
- Snowflake connector: `snowflake-connector-python` with key-pair auth. Private key stored as Cloud Run secret.
- Gemini calls cached per-subregion at the API layer (TTL: until next deploy). Do not call Gemini twice for the same subregion in the same deployment.
- Cortex Analyst: pass-through to Snowflake REST API via `/ask` endpoint.

### Degraded Mode

Both external dependencies (Snowflake, Gemini) have fallbacks:

| Dependency Down | Fallback |
|---|---|
| Snowflake | Return cached static JSON per-subregion with `degraded: true` |
| Gemini | Return pre-rendered template with data interpolated, `degraded: true` |
| Cortex Analyst | Display fallback message, reveal page continues normally |

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
│   └── EIA_860_PLANTS
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

- **Key-pair auth** for Snowflake connector (not user/password). Private key stored as Cloud Run Secret Manager secret.
- **Never hardcode credentials** in source code, environment files, or SQL scripts.
- **XS warehouse only.** The free trial has $400 of credits. Do not burn them on oversized warehouses.
- Do not use `ACCOUNTADMIN` role for application queries. Create and use a scoped application role.

### Performance

- Queries against `V_MINE_FOR_SUBREGION` must return in **under 2 seconds** on XS warehouse.
- Leverage Snowflake's **24-hour result cache** — identical queries return instantly with no compute cost.
- No clustering keys needed at this data scale (~500 mines after coal filter).
- The Cortex COMPLETE summary column must have **no nulls** — validate after ETL.

## 4. Gemini Rules

- Use **Gemini Flash** tier to minimize cost and latency.
- Prompt input must include: `{mine_name, operator, county, state, plant_name, plant_operator, tons_latest_year, tons_year, subregion_id}`.
- Output: 3-5 sentences. Names the mine, the plant, the operator, the tonnage. Grief-coded register. No cheerful hedging.
- **Cache per-subregion** at the API layer. Same subregion within the same deployment = no second Gemini call.

## 5. Frontend Rules

### Map (MapLibre GL)

- Zoom sequence: user location -> power plant -> source mine. Arc line drawn between all three points.
- Sequence must complete within **8 seconds** from payload receipt to final zoom.
- All three pins and labels must be readable on mobile (>= 375px wide) without horizontal scroll.

### Particles (PixiJS)

- Use **ParticleContainer** with sprite batching. Required to maintain >= 30 FPS on low-end laptops.
- Tonnage ticker: `annual_tons / seconds_in_year`, displayed to two decimal places.
- Particles begin within **500ms** of hero image fade-in.

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

## 7. File & Code Conventions

- **Python:** Follow PEP 8. Type hints on all function signatures. Use `async def` only if genuinely async; sync is fine for Snowflake connector and Cortex Analyst REST calls.
- **JavaScript:** Vanilla JS, no transpilation. ES modules. No TypeScript for this project (speed over safety for a weekend build).
- **SQL:** Uppercase keywords, lowercase only inside string literals. One statement per file when possible. Comment the "why," not the "what."
- **Secrets:** Never committed. Use `.env` locally (gitignored), Secret Manager in Cloud Run.
- **Static assets:** Checked into repo under an `assets/` directory. eGRID GeoJSON, hero images, fallback JSON, semantic model YAML.

## 8. Snowflake MCP Server

For local development with Claude Code, use the **official Snowflake MCP server** from Snowflake-Labs:

- **Repo:** https://github.com/Snowflake-Labs/mcp
- **Install:** `uvx snowflake-labs-mcp --service-config-file config.yaml`
- **Capabilities:** Cortex Search, Cortex Analyst, SQL execution, object management
- **Auth:** Key-pair, OAuth, SSO, or user/password via Snowflake Python Connector
- **Transport:** stdio for local dev, streamable-http for container deployment

Alternative (simpler, read-only): https://github.com/isaacwasserman/mcp-snowflake-server
- Install: `npx -y @smithery/cli install mcp_snowflake_server --client claude`
- Good for schema exploration and read queries during development

Do not configure MCP write access without explicit approval. Read-only by default.

## 9. Semantic Model (Cortex Analyst)

The semantic model YAML must be checked into the repo and cover these supported question patterns:

1. "How much has [mine] produced since [year]?"
2. "What other plants buy from [operator]?"
3. "Is [mine] still active?"
4. "What is the total tonnage for [subregion] in [year]?"
5. "Who is the largest coal supplier in [state]?"

Any question outside these patterns should be gracefully rejected with chip suggestions. The YAML covers the 4 base tables + 2 views. Keep it minimal — scope creep in the semantic model is the #1 timeline risk identified in the PRD.
