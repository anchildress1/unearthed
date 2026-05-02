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
- Geolocation denial or outside-US location: inline error copy on the Hero. Google Places autocomplete (restricted to US + territories) covers the state-only case — typing a state name or two-letter abbreviation surfaces valid predictions, so a separate picker isn't needed.
- Dev: `make dev` (frontend :5173) + `make server` (backend :8001). Vite proxies API calls.

### Backend

- Python 3.12 / FastAPI. Dependencies managed via `pyproject.toml` + `uv`.
- Snowflake connector: `snowflake-connector-python` with key-pair auth (preferred) or password auth (opt-in via `ALLOW_PASSWORD_AUTH=true` for local dev). Private key stored as Cloud Run secret.
- Two Snowflake roles: `UNEARTHED_APP_ROLE` (general queries), `UNEARTHED_READONLY_ROLE` (Analyst SQL execution — SELECT-only grants).
- Cortex Analyst: REST API via `/ask` endpoint. Generated SQL is validated (SELECT-only, no multi-statement, no DML/DDL keywords) and executed under the read-only role with a 500-row cap and 10-second statement timeout.
- Default suggestions (from 5 verified queries) are always returned in `/ask` responses.
- Docs/OpenAPI disabled by default (set `ENABLE_DOCS=true` for local dev). CORS origins configurable via `CORS_ORIGINS` env var.
- **Security headers middleware** sets `Content-Security-Policy: frame-ancestors 'self' https://dev.to` (allows DEV embed), `X-Content-Type-Options: nosniff`, and `Referrer-Policy: strict-origin-when-cross-origin` on every response. Tests live in `tests/integration/test_new_endpoints.py::TestSecurityHeaders`.

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
- **Honest attribution:** `generate_prose` returns `(text, degraded, stats)` — the `stats` dict carries the MSHA safety counts (`fatalities`, `injuries_lost_time`, `days_lost`) that the frontend's unified cost block (people subsection) surfaces at the top of section 2, independent of whether the prose itself is Cortex-written or templated. `generate_h3_summary` returns `(text, degraded)`. Only Cortex output is cached — template fallbacks are not, so a recovered model shows up on the next request and the "Cortex, on this map" / "Cortex, reading the record" bylines never sit over template prose.
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
- **Emissions are pre-aggregated** — `MRT.EMISSIONS_BY_PLANT` (240 rows, `FACILITY_NAME` uppercase) replaces the 2.2B-row EPA_CAM_TIMESERIES join. Query the MRT table, not the Marketplace tables directly. The `/emissions` endpoint strips EIA parenthetical suffixes (e.g. `(TN)`) and uses `LIKE` prefix matching to bridge EIA→EPA naming differences.
- **Mine-plant lookup is materialized** — `MRT.MINE_PLANT_FOR_SUBREGION` (19 rows) pre-computes the top mine + plant per eGRID subregion. `/mine-for-me` reads this single table instead of joining 4 RAW tables through views.
- **Session-level guards** — every connection sets `STATEMENT_TIMEOUT_IN_SECONDS = 10` and `ROWS_PER_RESULTSET = 500` via `ALTER SESSION` at creation time. These cap runaway Analyst SQL and protect credit burn. `execute_analyst_sql` also enforces a hard 500-row cap via `fetchmany(500)`. If `ALTER SESSION` fails, the connection is closed before re-raising to prevent session leaks.
- **Bounded in-memory caches** — `_emissions_cache` and `_mine_context` are LRU `OrderedDict`s capped at 256 entries. Prose and H3 summary caches are bounded by their fixed key spaces (19 subregions, ~50 states). All caches reset on process restart.
- **Prose prewarm** — gated behind `PREWARM_PROSE=true` env var (default off). When enabled, a background thread pre-warms prose for all 19 fallback subregions at startup. Disabled by default to avoid multiplying Cortex costs on autoscaled Cloud Run instances.

## 4. Frontend Rules

### Map (Google Maps JavaScript API)

- Loader lives in `frontend/src/lib/maps.js` — uses the Google Maps Dynamic Library Import bootstrap (`google.maps.importLibrary`). `loadGoogleMaps()` installs the bootstrap once; each caller then does `await importLibrary('places'|'maps'|'geometry')` for only the scope it needs (billing is per-library). A 15 s `setTimeout` watchdog rejects the load promise if the script is blocked by a privacy tool or CSP without firing `onerror`.
- **Hero address resolution** goes through GCP end-to-end via the Places API (New). Places classes are imported through `google.maps.importLibrary('places')` — never the legacy `AutocompleteService`. As the user types (≥3 chars, debounced) we call `AutocompleteSuggestion.fetchAutocompleteSuggestions` with `{ input, includedRegionCodes: ['us', 'pr', 'vi', 'gu', 'mp', 'as'], language: 'en-US', sessionToken }` — a hard restrict to the US + territories we carry eGRID coverage for. `region` alone only *biases* results and would still surface Paris, France for "par"; `includedRegionCodes` is the parameter that excludes non-US predictions entirely. Up to 5 predictions render in a custom dropdown beneath the existing input — **the input, trace button, and glass styling are untouched**. Clicking a prediction just populates the input (same as typing); hitting `trace →` resolves the chosen (or top) prediction via `place.fetchFields({ fields: ['location'] })` on the Autocomplete-Essentials tier. No Nominatim, no other geocoder.
- `DARK_STATE_STYLES` + `MAP_COLORS` are the single source of truth for both maps. No cloud-registered `mapId` — that would silently disable the local style array.
- `MapSection` arc: mine → plant → your meter, one rust color, animated dot rides the geodesic. Labels fan out (above / below / side) to avoid InfoWindow stacking.
- **Labeled pin cards (`createLabeledMarker` in `maps.js`).** All three map tags — MINE, PLANT, METER — render as one unified 3-line card: rust glyph + mono TYPE eyebrow, serif name, mono subtitle. Only the glyph shape changes by type (diamond for MINE, flat square for PLANT, circle for METER/YOU) so the family reads as one voice across sections 03 and 04. Subtitle format is `identifier · geography` — for MINE, `MSHA {id} · {county} Co., {state}` when all fields are present; empty strings skip the row so degraded payloads don't render "undefined". The METER name stays `your meter` until reverse geocoding lands; its subtitle uses the eGRID subregion as the honest identifier. Do not fork the card chrome per section — extend `createLabeledMarker` instead.
- `H3Density`: resolution-5 hexbins, bigger dot = more mines, rust→ash gradient for active→abandoned. SQL filters null-island and ocean outliers at the query layer. Single map frame fit tight on the hex cluster ("the shape of extraction"). **No eGRID polygon is drawn on either map** — the user's subregion is surfaced only as text on their pin in `MapSection` (N° 03, via `meterSubtitle`), so each section owns one framing and the two don't compete for the reader's focus. A labeled MINE card anchors the reader's dot in the cluster (same helper, same subtitle format as section 03); the user pin stays label-free on purpose — a card over the cluster would block the shape it's trying to show. Render failures surface in the console with a full stack and flip a single `errored` flag; the outer data-fetch catch is the only path that degrades the whole section.
- All three pins and labels must be readable on mobile (>= 375px wide) without horizontal scroll.

### Section chrome (editorial unification)

**One title treatment for the whole page.** `SectionRail.svelte` is the canonical wrapper — every scroll section uses it, and it must mirror the Hero section's editorial signature so the page reads as one magazine spread instead of disconnected blocks. The component owns:

- **Vertical left-gutter rail.** The chrome (`N° ## / hairline / rotated label`) is a narrow flex column pinned in the left gutter; the content column is `flex: 1 1 0` to its right. The hairline uses `flex: 1 1 auto` so it stretches the full height of the content column — N° caps the top, the rotated label anchors the bottom, the rule runs the length of the editorial frame. Exactly matches `Hero.svelte`'s `.hero-layout` structure — if you touch one, touch the other. Do **not** regress to a horizontal chrome strip.
- **Rotated label.** `writing-mode: vertical-rl; transform: rotate(180deg);` — real sideways text so screen readers still read it. Do not use transform-only rotation (breaks accessibility and paints inconsistently).
- **Narrow-screen collapse.** At `≤720px` the `.section-layout` flex-direction flips to `column`, the rail goes horizontal, and the label reads left-to-right again. Same breakpoint as Hero.
- Canonical `h2`/`h3` typography (serif, clamped, `em` accent) — do NOT re-declare in sections. If a title doesn't match, it's a bug in the section, not a license to override.
- The `.sub` subtitle pattern.
- The `.cortex-note` block (rust border-left) signaling Cortex-written text.
- The **three-line anchor pattern** via `:global(.anchor-primary)` + `:global(.anchor-secondary)`: big value / serif plain-English primary / mono uppercase tag. Used by PlantReveal's lower stat cards, the emissions panel, and the H3 tallies. **Do not re-declare these per section.** If you need a larger closing beat (Ticker), define a distinct class — don't shadow the canonical one.
- The **cost block** at the top of section 2 (`.cost` in `PlantReveal.svelte`) is an intentional break from the three-line anchor pattern: it's the moral center of the page and needs its own editorial voice. Structure is an inset column (rust left-gutter, small rust tick, rust-glow pooled at top-left — no glass card) with a mono eyebrow attribution, a serif title (`.cost-title`), a **people** ledger (`.ledger[data-kind="people"]` — oversized serif numerals on the left, serif primary + italic sub on the right; fatalities row is `.row--grave` with the numeral bumped and colored `--rust-bright` italic — the charged moment that tier exists for; injuries first, fatalities second, days-lost third; zero-value rows omitted), a typographic caesura (`.cost-break` with rust interpuncts), a **land** ledger (`.ledger--quiet` with compact inline `254 / 192` for surface mines, or a prose note for underground), and a closing couplet (`.cost-kicker`: first line `--text-dim` italic, second line `--rust-bright` italic bigger — "The acres can be restored. / The miners cannot."). The whole block hides only when both subsections have nothing to show. Do not revert to a card grid here; the asymmetric typographic weight *is* the argument.
- **Section content widths.** `SectionRail`'s `.rail-content` no longer caps the content column — headlines fill it edge-to-edge as the editorial beat of each section, and sections cap their own interactive/wide-prone content locally. Canonical caps to keep in mind: CortexChat's `.cortex-shell` wraps the form + pipeline + chips + results table at `min(1040px, 100%)` (the old outer cap, moved in); MapSection's `.map-frame` at `min(1080px, 100%)`; PlantReveal's internal panels at `min(820px, 100%)` and `.cost` at `min(720px, 100%)`; canonical `.sub` at `640px`. Do NOT re-introduce the outer `.rail-content` clamp — it caps headlines, which is the regression that prompted removing it. The old per-section `.map-header` / `.h3-header` wrappers have been consolidated into `.section-header`; do not reintroduce per-file copies, and do not re-add narrow `.closing` / `.dedication` caps on Ticker — those regressed the column unification.

### Share URL

- Structure: `/?m=SRVC` (eGRID subregion ID, not mine slug).
- Open Graph tags updated client-side with mine name and hook text after reveal.
- Share URL skips geolocation and jumps straight to that subregion's reveal.
- Every successful trace (not just share-link arrivals) calls `history.pushState({}, '', ?m=<subregion>)` so a refresh preserves the trace — `onMount` replays it from the URL, and the browser restores scroll position to where the user was reading. Do not "fix" the refresh-lands-on-empty-space symptom with `scrollRestoration = 'manual'`; the root cause is URL state, and the pushState handles it end-to-end.

### Testing (frontend)

Three tiers, all runnable from `frontend/` with `pnpm`:

| Tier | Command | Stack | Scope |
|---|---|---|---|
| Unit / component | `pnpm test` | Vitest + jsdom + @testing-library/svelte | Pure JS modules (`geo.js` + edge, `api.js` + edge, `reveal.js`) and component chrome (`SectionRail`, `PlantReveal` + emissions, `CortexChat`, `Ticker`). Coverage via `pnpm test:coverage`. |
| E2E | `pnpm test:e2e` | Playwright (Chromium) against the built `vite preview` bundle | Share-URL replay (`/?m=NWPP`), pushState refresh preservation, editorial rail rendering on every section, lowercase token normalization, degraded / error-state rendering, and Google Maps runtime (MapSection + H3Density marker/OverlayView lifecycle) via the behavioral `google.maps` stub in `fixtures.js`. Backend is mocked at the `page.route` layer — no FastAPI or Snowflake required. |
| Lighthouse | `pnpm lhci` | @lhci/cli against `vite preview` | Audits `/`. Thresholds are load-bearing and enforced by `lighthouserc.cjs`. |

**Lighthouse thresholds (non-negotiable):**

- Accessibility ≥ **1.00**
- SEO ≥ **1.00**
- Best Practices ≥ **0.98**
- Performance ≥ **0.90**

Missed thresholds fail CI. Fix the root cause — do not relax the gate. A fresh run should produce all-four-green. Known contributors to regressions:

- `errors-in-console` — any 404 (favicon, missing asset) or unhandled console error drops Best Practices. A real `static/favicon.ico` is in-tree; do not delete it.
- `color-contrast` — dim copy against the near-black background. `--text-ghost` and the `.data-credit` footer color are tuned to ≥4.5:1; darken them and the a11y score falls back to 0.95. Keep the rationale comments in `+layout.svelte`.

E2E specs live in `frontend/e2e/`. Shared fixtures are in `e2e/fixtures.js`: `mockBackend(page)` installs routes for `/mine-for-me`, `/emissions/*`, `/h3-density`, `/ask`, plus a swallow-route for `maps.googleapis.com` so the Places bootstrap doesn't stall tests. `installGoogleMapsStub(page)` is the behavioral `google.maps` double used by `maps-render.spec.js` — it records every `new Map`, `new Marker`, and `OverlayView.setMap` call on `globalThis.__gmapsCalls` so tests can assert on marker construction and the projection/draw lifecycle without pixel-perfect rendering. Register test-specific routes **after** `mockBackend` — Playwright matches most-recent-first.

## 5. Error Handling Philosophy

- **Cortex Analyst misfires:** Display the generated SQL plus "I could not answer that confidently." Honesty > hallucinated numbers.
- **Out-of-scope questions:** Semantic model guardrails reject. UI offers chip suggestions instead.
- **Snowflake failure:** Cached static JSON fallback per-subregion.
- **Location outside US:** Graceful message on the Hero + the Places-restricted input (US territories included) so the reader can type any state and reach coverage. Never a dead end.
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
6. "Which mines supply plants in [subregion]?" (and the compound form, "Which mines in [state] supply plants in [subregion]?") — answered against `MRT.V_MINE_FOR_SUBREGION`.

Any question outside these patterns should be gracefully rejected with chip suggestions. The YAML covers the 5 RAW tables that serve patterns 1–5 (MSHA_MINES, MSHA_QUARTERLY_PRODUCTION, MSHA_ACCIDENTS, EIA_923_FUEL_RECEIPTS, EIA_860_PLANTS, PLANT_SUBREGION_LOOKUP) plus one MRT rollup — `V_MINE_FOR_SUBREGION` — which is the authoritative answer for pattern 6. The rollup is exposed to Analyst because reconstructing mine-to-subregion through a 3-hop RAW join (receipts → plants → subregion lookup) was causing Analyst to bail on disambiguation instead of answering. `MINE_PLANT_FOR_SUBREGION` and the RAW-layer `V_MINE_FOR_PLANT` remain out of the semantic model — they serve the `/mine-for-me` endpoint via hand-written SQL. Keep the semantic model minimal — scope creep is the #1 timeline risk identified in the PRD.
