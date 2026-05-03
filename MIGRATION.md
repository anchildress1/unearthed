# MIGRATION.md — Snowflake → R2 + DuckDB + Claude

This is the handoff brief for Claude Code (Insiders). The hackathon is shipped and won. Snowflake's role is over. This document is the spec for migrating to a hobby-budget stack while preserving every public contract.

Read [AGENTS.md](./AGENTS.md) before writing code. Read [PRD.md](./PRD.md) for product intent. This doc supersedes the Snowflake-specific sections of AGENTS.md once a phase is complete; update AGENTS.md in Phase 4.

---

## Locked decisions (do not relitigate)

| Concern | Decision | Rationale |
|---|---|---|
| Storage backend | **Cloudflare R2** | 10GB free, $0 egress, fits "could go viral, won't always". User has Cloudflare account already. GCS rejected because all infra is in `us-east1` and GCS always-free is `us-central` only. |
| Query engine | **DuckDB embedded in FastAPI** | No server, no daemon, queries Parquet over `httpfs`. Column pruning + predicate pushdown over HTTP make this viable for low-traffic. |
| Data format | **Parquet** | 5-10x compression vs CSV, columnar reads, universal. |
| LLM (runtime) | **Claude Sonnet 4.6** with prompt caching | NL→SQL not needed; tool-using agent is the model. Sonnet for capability, prompt cache for cost. |
| LLM (build-time prose) | **Claude Sonnet 4.6**, output committed | Mine narratives baked once per mine, never called at request time. |
| Compute host | **Cloud Run stays** (with config fix) | Rewriting FastAPI as TS Workers for $3/mo savings is not worth the time. |
| Frontend host | **Cloud Run stays for now** | Cloudflare Pages migration is a separate concern, not in this brief. Note in TODO if user wants it later. |
| Public endpoint contracts | **Unchanged** | `/mine-for-me`, `/ask`, `/h3-density`, `/emissions/{plant}` keep current request/response shapes. Frontend code does not change. |
| Degraded-mode contract | **Unchanged** | Per-subregion fallback JSON (19 files) and the `degraded: true` flag stay. Add new fallback paths *only* if a new failure mode is introduced. |

## Hard out-of-scope

- **No new features.** This is a stack migration, not a product change.
- **No new endpoints.** Same four routes, same request/response shapes.
- **No frontend rewrite.** Footer credit copy update only (Phase 4).
- **No Cloudflare Workers / Pages migration.** Separate effort.
- **No changes to the eGRID GeoJSON, the 19 fallback JSONs, the semantic model YAML's question-pattern coverage** (the YAML itself goes away in Phase 3, but the same patterns must still be answerable).
- **No "TODO-gated" half-finished work.** AGENTS.md §6 stands. If a phase can't fully ship, scope it down — don't merge a stub.

---

## Phase 0 — Prep (one-off, no code)

**Deliverables:**

1. R2 bucket created. Suggested name: `unearthed-data`. Region: pick the auto / nearest. Public access: **off** (DuckDB authenticates via S3-compatible keys).
2. Cloudflare R2 API token issued. Scope: Object Read + Object Write on the bucket only. Not the account-wide token.
3. Anthropic API key issued, stored in Cloud Run as `ANTHROPIC_API_KEY` secret via Secret Manager.
4. R2 credentials stored in Cloud Run as `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`, `R2_BUCKET` secrets.
5. Bucket layout decided and documented in this file:

```
unearthed-data/
├── raw/
│   ├── msha_mines.parquet
│   ├── msha_quarterly_production.parquet
│   ├── msha_accidents.parquet
│   ├── eia_923_fuel_receipts.parquet
│   ├── eia_860_plants.parquet
│   └── plant_subregion_lookup.parquet
├── mrt/
│   ├── v_mine_for_plant.parquet
│   ├── v_mine_for_subregion.parquet
│   ├── mine_plant_for_subregion.parquet
│   └── emissions_by_plant.parquet
└── prose/
    └── mine_narratives.json     (pre-baked, committed to R2 not the repo)
```

**Acceptance:** `aws s3 ls --endpoint-url $R2_ENDPOINT s3://unearthed-data/` returns an empty bucket. Cloud Run revision has all secrets bound (verify via `gcloud run services describe`).

---

## Phase 1 — Data layer foundation + first endpoint cutover

**Goal:** Prove the R2 + DuckDB pattern end-to-end on the simplest endpoint before committing to it for all four.

**Deliverables:**

1. **Export script** (`scripts/export_snowflake_to_parquet.py` or similar). Reads each Snowflake table once, writes Parquet locally, validates row counts against `SELECT COUNT(*)` from Snowflake. **Must fail loudly on count mismatch.** No silent data loss.
2. **Upload script** (`scripts/upload_to_r2.py` or `make` target). Uses boto3 against R2's S3-compatible endpoint. Idempotent.
3. **`app/data_client.py`** — new module. DuckDB connection lifecycle (one connection per FastAPI worker, lazy `INSTALL httpfs; LOAD httpfs;`, R2 credentials from env). Helper functions for parameterized parquet reads. **Do not** expose raw `con.execute()` outside this module — keep query construction here so SQL injection surface stays narrow (mirrors the SELECT-only validation discipline of the current `snowflake_client`).
4. **`/emissions/{plant}` migrated.** Hand-written DuckDB SQL against `s3://unearthed-data/mrt/emissions_by_plant.parquet`. Same response shape. Same EIA→EPA name normalization (`LIKE` prefix matching, parenthetical stripping).
5. **Tests:** existing `test_new_endpoints.py::TestEmissions*` must pass without modification. Add a unit test for `data_client.query_emissions_for_plant` that hits a fixture parquet file checked into `tests/fixtures/`.
6. **Old code path stays alive.** `snowflake_client.get_emissions_for_plant` is not removed yet — Phase 5 does the deletion. Endpoint just stops calling it.

**Acceptance:**
- `pytest tests/integration/test_new_endpoints.py::TestEmissions` green.
- `curl localhost:8001/emissions/COLSTRIP` returns identical JSON shape and values to current Snowflake-backed response (spot-check 5 plants).
- Cold-start `/emissions/{plant}` latency under 1s (DuckDB needs to fetch the parquet's footer the first time; subsequent queries reuse the open connection).
- No regressions in the other three endpoints.

---

## Phase 2 — Migrate `/mine-for-me` and `/h3-density`

**Goal:** All non-LLM endpoints serve from R2 + DuckDB. `/ask` stays on Cortex Analyst until Phase 3.

**Deliverables:**

1. **`/mine-for-me`** — query `s3://unearthed-data/mrt/mine_plant_for_subregion.parquet`. Same 19-subregion fallback contract via `assets/fallback/<subregion>.json`. **Cortex Complete prose generation is NOT yet replaced** — this endpoint still calls `prose_client.generate_prose` against Snowflake. That's fine; replaced in Phase 3.
2. **`/h3-density`** — DuckDB does not have a native H3 extension equivalent to Snowflake's `H3_LATLNG_TO_CELL_STRING`. Use the **`h3-py`** library to compute hex cell IDs at query time, OR pre-compute hex assignments in Phase 1's export and store as a Parquet column. **Decide and document which.** Pre-computing is cheaper at runtime; computing at query time is more flexible if resolution becomes a tunable. Pre-computing wins for hobby cost.
3. **Same `totals` second-query pattern** stays — unfiltered registry counts go through DuckDB the same way.
4. **Cortex Complete H3 summary** stays on Snowflake until Phase 3.
5. **Tests:** all existing `/h3-density` and `/mine-for-me` tests pass unmodified, including the degraded-mode tests and the `summary_degraded` flag behavior.

**Acceptance:**
- All three non-LLM endpoints return DuckDB-sourced data with identical JSON shapes.
- Snowflake connection still alive (used by `/ask` and prose endpoints).
- `make test-ci` green.

---

## Phase 3 — Replace Cortex Analyst and Cortex Complete

**Goal:** No more Snowflake calls. `/ask` becomes a Claude tool-using agent. Mine narratives and H3 summary become build-time-baked or one-shot Claude calls.

**Deliverables:**

1. **`app/llm_client.py`** — Anthropic SDK wrapper. One client per worker. Prompt caching enabled on the system prompt + tool catalog. Model: `claude-sonnet-4-6`.
2. **`app/tools.py`** — tool catalog. Functions Claude can call. Each is a thin Python wrapper over `data_client.py` queries. Suggested first cut:
   - `lookup_mine_by_id(mine_id: int) -> dict`
   - `mines_supplying_plant(plant_name: str, year: int | None = None) -> list[dict]`
   - `production_history(mine_id: int, year_range: tuple[int, int] | None = None) -> list[dict]`
   - `safety_record(mine_id: int) -> dict` — fatalities, injuries, days lost
   - `emissions_for_plant(plant_name: str) -> dict`
   - `search_mines(state: str | None = None, county: str | None = None, status: str | None = None) -> list[dict]`
   - `top_supplier_in_state(state: str) -> dict`
   - `subregion_breakdown(subregion_id: str) -> dict`

   These cover the six question patterns in AGENTS.md §9 plus comfortable freeform headroom. **Tools must enforce the 500-row cap and 10s timeout** that the current Snowflake session-level guards provide. Do this in Python with explicit limits in the SQL and `concurrent.futures` timeouts.
3. **`app/skill.md`** (or a constant in `llm_client.py`, but a markdown file is easier to iterate on) — system prompt covering:
   - Domain primer (US coal supply chain, MSHA vs EIA vs EPA roles, what each ID means)
   - Tool catalog with when-to-use guidance
   - Reasoning patterns (question → tool sequence)
   - Output rules (format, citation of mine IDs, "I don't know" triggers)
   - Refusal patterns (no investment advice, no predictions, no data outside the corpus, no scope creep into adjacent topics)
   - Scope reminder: this is a US coal lookup, not a general energy chatbot
4. **`/ask` rewrite.** Endpoint accepts `{question, subregion_id?}` (unchanged). Invokes Claude with tools. Response shape:
   ```json
   {
     "answer": "...",
     "tools_used": ["mines_supplying_plant", "safety_record"],
     "suggestions": [...],
     "degraded": false,
     "error": null
   }
   ```
   The `sql` field from the current Cortex Analyst response goes away — the frontend's CortexChat component will need a small update to drop the SQL display block. Coordinate with the frontend update in Phase 4.
5. **Pre-baked mine narratives.** New script `scripts/bake_mine_narratives.py`. For each mine in `MSHA_MINES`, generate the safety prose Cortex Complete used to write — but call Claude once at build time. Output `prose/mine_narratives.json` keyed by mine ID, upload to R2. Commit the script, **do not** commit the JSON output (it lives in R2). `/mine-for-me` reads from R2 and falls back to a template if the mine ID is missing.
6. **H3 summary.** Two options: (a) bake it per state at build time and store in `prose/h3_summaries.json`, OR (b) one-shot Claude call at request time with the cell counts. Bake-time wins for cost; pick (a). The `summary_degraded` flag still fires if the prose is missing for the requested scope.
7. **Honest attribution preserved.** AGENTS.md §3's rule that "the 'Cortex, on this map' byline never sits over template prose" becomes "the 'Claude, on this map' byline never sits over template prose." Same contract, new label. Frontend copy updates in Phase 4.

**Acceptance:**
- All four endpoints serve without any Snowflake call. Verify with `grep -r 'snowflake' app/` returning only the dead `snowflake_client.py` (Phase 5 deletion).
- `/ask` answers the six AGENTS.md §9 question patterns correctly. Add a regression test per pattern.
- Realistic per-question cost measured and logged. Document actual numbers in this file.

---

## Phase 4 — Hardening + doc sync

**Deliverables:**

1. **Question-hash cache for `/ask`.** SHA256 of normalized question (lowercased, whitespace-collapsed) → cached response. Backend: in-memory `OrderedDict` LRU capped at 1024 entries (matches the 256-entry pattern of `_emissions_cache` but bigger because question space is larger). Optional: persist to R2 as `cache/ask/<hash>.json` with a 24h TTL; only worth it if cold-start traffic is non-trivial.
2. **Rate limit on `/ask`.** `slowapi` middleware. 5/min/IP, 50/day/IP. Return 429 with a polite message that points to the chips. Document in AGENTS.md §2.
3. **Cloud Run config.** Update the deploy command / Terraform / `gcloud run services update` invocation to set `--min-instances=0` and `--cpu-throttling`. Verify Cloud Run cost drops.
4. **Doc sync — non-negotiable, all in this PR:**
   - `AGENTS.md` §1 (project constraints): hackathon constraint section can soften — mark deadline as "originally 2026-04-20, since shipped." Cost-optimization rule replaces shipping rule.
   - `AGENTS.md` §2 (architecture): rewrite to describe DuckDB + R2 + Claude tool agent. Drop the two-Snowflake-roles section. Update degraded-mode table.
   - `AGENTS.md` §3 (Snowflake): delete the section. Add a §3 (Data Layer) covering DuckDB conventions (read-only `data_client.py` boundary, no `SELECT *`, parameterized queries).
   - `AGENTS.md` §8 (Snowflake MCP): delete.
   - `AGENTS.md` §9 (semantic model): delete; the question patterns it lists move into the skill prompt as reasoning patterns.
   - `PRD.md`: data architecture section, update.
   - `system-diagram.md`: regenerate the Mermaid.
   - `frontend/src/routes/+layout.svelte` footer: drop the Snowflake Cortex link, add "Claude (Anthropic) · DuckDB · Cloudflare R2" credits.
   - `CortexChat.svelte` → consider rename to `AskChat.svelte` or similar. Drop the SQL-display block. Keep the chips. Coordinate with `/ask` response shape change.
   - `frontend/e2e/fixtures.js` `mockBackend` → update `/ask` mock response shape.

**Acceptance:**
- `make lint`, `make test`, `pnpm test`, `pnpm test:e2e`, `pnpm lhci` all green.
- Lighthouse thresholds (a11y 1.0, SEO 1.0, BP 0.98, perf 0.90) hold.
- One-week observation window: Cloud Run + Anthropic + R2 spend matches projected ~$5/mo or document why not.

---

## Phase 5 — Cutover and Snowflake teardown

**Deliverables:**

1. **Delete `app/snowflake_client.py`** and `app/prose_client.py` (Snowflake-specific).
2. **Drop `snowflake-connector-python` from `pyproject.toml`.** Run `uv sync` and verify nothing imports it.
3. **Remove Snowflake secrets from Cloud Run** (`SNOWFLAKE_*` env vars and the private-key secret).
4. **Suspend the Snowflake account** via the Snowflake console. Do not delete it for one billing cycle in case of post-cutover issue. After 30 days clean, delete.
5. **Remove `snowflake-mcp-config.yaml`** from the repo. Remove the Snowflake MCP server section from any local `.mcp.json` or Claude Code config.
6. **CHANGELOG entry** describing the migration.

**Acceptance:**
- `grep -ri snowflake .` returns only this file, the CHANGELOG entry, and historical commits.
- Cloud Run service has no Snowflake env vars.
- Anthropic + R2 + Cloud Run are the only three line items on the bill.

---

## Open questions for the user (ask before Phase 3)

1. **`/ask` `subregion_id?` — RESOLVED.** Stay explicit.
2. **Donate platforms — RESOLVED.** Buy Me a Coffee (`buymeacoffee.com/anchildress1`) + GitHub Sponsors (`github.com/sponsors/anchildress1`). Both wired in the footer.
3. **Data expansion — see new section below.** Confirm subset before Phase 3 starts.

---

## Phase 3.A — MSHA enforcement + fatality narrative expansion

This is the user's "I want the actual fatality reports, incidents, and how they classify the major shit" requirement. It expands the data corpus before Phase 3's tool catalog is finalized — adding tools after the agent is shipped is fine, but it's cheaper to do it once if we know the scope now.

### What MSHA actually publishes

Three tiers of relevant data, all public:

**Tier 1 — Structured bulk data** (pipe-delimited text files, MSHA Open Government Data Portal):

| Dataset | Why it matters | Rough size |
|---|---|---|
| **Violations** (since 2000) | Every citation issued. Filterable to S&S (Significant & Substantial — the "could reasonably cause serious injury" tier). The mine's enforcement history. | ~5M+ rows, ~200-500 MB Parquet |
| **107(a) Orders** (since 2000) | Imminent-danger withdrawal orders. The legal "stop work" hammer — when MSHA forcibly shuts down a section. This *is* the "major shit" classification. | ~few thousand rows, trivial size |
| **Inspections** (since 2000) | Linked to Violations by Event Number. Gives "what triggered the citation." Optional — only worth ingesting if we want inspection-history surface. | Large, defer unless needed |
| **Assessed Violations** | Penalty amounts. Lets the agent answer "how much has mine X been fined?" | ~few hundred MB Parquet |
| **Contested Violations** | Which citations the operator is fighting. Adds nuance to enforcement history. | Smaller |

**Tier 2 — Per-incident summary records** (Data.gov "MSHA Fatality Reports" dataset):

Structured rows with date, mine, location, accident type, mined material, victim count. Fast to ingest. Already a superset of the user's current `MSHA_ACCIDENTS` table for fatal events specifically.

**Tier 3 — Narrative investigation documents** (the gold):

| Document type | Format | What it gives |
|---|---|---|
| **Preliminary Accident Reports** | HTML/PDF, published days after a fatality | First-pass narrative, basic facts |
| **Fatalgrams** | 1-page PDF, educational | "Best practices" framing of the incident |
| **Fatal Investigation Reports** | Multi-page PDF, published 6-18 months later | Full root cause, contributing factors, citations issued, recommendations. The narrative the agent can quote. |

The historical TICL archive holds ~24,000 investigation documents (~33,000 victims) going back to MSHA's predecessor agencies.

### Recommended subset for Phase 3.A

Pick a defensible scope and ship it; do not try to ingest everything:

1. **Violations dataset, filtered to S&S, joined on `MINE_ID`** → new Parquet `mrt/violations_ss_by_mine.parquet`. Pre-aggregate "S&S count by mine, by year." Tool: `safety_violations(mine_id, year_range=None)`.
2. **107(a) Orders dataset, full** → `mrt/withdrawal_orders.parquet`. Tool: `withdrawal_orders(mine_id)`. Surface the most charged signal: "MSHA forced this mine to stop work N times since 2000."
3. **Assessed Violations totals by mine** → roll into `mrt/violations_ss_by_mine.parquet` as a `total_penalties` column. Tool: extend `safety_violations` to include penalties.
4. **Fatal Investigation Reports for coal-related fatalities, last 15 years** → scraped, text-extracted via Claude at build time, structured as `mrt/fatality_narratives.parquet` with columns:
   - `mine_id`
   - `incident_date`
   - `victim_count`
   - `cause_category` (Claude-classified into a controlled vocab: roof_fall, methane_ignition, equipment, electrical, etc.)
   - `fact_lines` (list of 2-5 short declarative sentences; see extraction rules below)
   - `contributing_factors` (list, Claude-extracted from MSHA's findings — verbs, not adjectives)
   - `citations_issued` (list of citation IDs, regex-extracted)
   - `report_source` (one of: `msha_final`, `state_wv`, `state_ky`, `state_pa`, `state_other`, `msha_preliminary`)
   - `report_status` (one of: `final`, `preliminary`)
   - `contest_status` (one of: `uncontested`, `contested`, `not_applicable` — `not_applicable` for state and preliminary reports where contest doesn't apply)
   - `report_pdf_url` (link back to the source — rendered as a source chip on every card; chip label reflects `report_source`)

   Estimated scope: ~200-400 PDFs for coal-only, ~50 MB Parquet after extraction.

   Tool: `fatality_narrative(mine_id, date=None)` returns the structured rows + URL to the source PDF. The agent surfaces facts; it does not paraphrase the report's prose, and it does not editorialize.

#### Source-priority rule (MSHA-final > state > preliminary)

For each incident, the build pipeline picks ONE report and extracts only from it. Never blend sources — they can disagree, and stitching them produces composite "facts" no single agency endorses. Priority:

1. **MSHA Fatal Investigation Report (final)** if it exists — extract from this and ONLY this. Set `report_source=msha_final`, `report_status=final`, populate `contest_status` from MSHA's contest dataset (any citation issued in the report being contested = `contested`).
2. **State investigation report (final)** if no MSHA final exists yet — extract from the state report (WV, KY, PA, etc. produce their own). Set `report_source=state_<abbr>`, `report_status=final`, `contest_status=not_applicable` (state reports follow a different appeals track; do not conflate).
3. **MSHA Preliminary Accident Report** as last resort if neither final exists yet — extract with explicit `report_status=preliminary` so the frontend can surface a "preliminary — subject to revision" label on the card. `contest_status=not_applicable`.

Re-run rule: when the build pipeline detects a final report has been published for an incident previously stored as preliminary or state-only, it **replaces** the row entirely. Never append. Never keep the old extraction "for history." Stale facts hurt more than missing ones.

5. **Include Contested Violations** as a `contest_status` field on `mrt/violations_ss_by_mine.parquet`. **Do not filter contested-but-unruled rows out** — most S&S citations get contested at first and rulings take 2-5 years; filtering on "ruled only" guts the dataset to a narrow window of old data. Surface the contest status as a small label in the rendered card ("12 S&S citations, 4 currently contested"). Reader weighs it; the data isn't suppressed; the context is honest.

6. **Pass on for now:** Inspections (huge, marginal value), Fatalgrams (Fatal Investigation Reports cover the same ground in more depth).

### Build pipeline implications

- **New script:** `scripts/scrape_msha_fatality_pdfs.py` — pulls PDFs, deduplicates, stores raw under `raw_pdfs/` in R2 (separate prefix from the working corpus). Respect `robots.txt`; throttle to 1-2 req/sec.
- **New script:** `scripts/extract_fatality_narratives.py` — for each PDF, calls Claude with a structured-extraction prompt, writes a row to the parquet. **Build-time cost:** ~$3-10 one-time for ~300 PDFs at Sonnet rates with prompt caching across the prompt template.
- **Refresh cadence:** annual is fine for fatality reports (they trail by 6-18 months anyway). Quarterly for the structured tier-1 datasets.
- **GitHub Action** (or local make target) to run the refresh and upload to R2.

### Extraction prompt rules — non-negotiable

The extraction prompt lives in `scripts/extract_fatality_narratives.py` (or a sibling `.md` file the script reads). It must enforce:

1. **No PII.** Replace all personal names — victim, foreman, supervisor, operator personnel, MSHA inspector — with role descriptors: "the miner", "the foreman", "the operator", "the inspector". Mine names and operator company names are public record and stay. If a PDF page has names in headers/captions, drop them at extraction.
2. **Strip the bureaucratic phrasing.** Convert MSHA's regulator prose into short declarative sentences. No "the investigation determined that the entity failed to ensure compliance with..." — write "the operator did not follow the approved ventilation plan."
3. **Facts only.** Each `fact_lines` entry must be a fact MSHA established in the report. No softening ("may have"), no amplifying ("egregiously"), no editorial frame ("a tragic preventable loss").
4. **Sentences are short.** Target 6-14 words per fact line. Long sentences are a signal you're paraphrasing instead of extracting.
5. **No comparison or pattern claims.** "This was the third fatality at the mine since 2019" is a comparison the agent must compute from the data, not a claim the extractor pulls from the PDF — and even then it belongs in a separate `pattern_context` field rendered with explicit data citations, not in `fact_lines`.
6. **Citations to MSHA are mandatory at the row level.** `report_pdf_url` is required; rows without it are dropped.

### Frontend display contract for fatality narratives

- **Cards live in their own section, not nested in the cost block.** The cost block is the author's voice (yours). The fatality narrative cards are the data's voice (the source report's facts, surfaced cleanly). Visual separation prevents the editorial weight of the cost block from leaking into the narrative cards or vice versa.
- **Each card renders:** date + victim count as the eyebrow, `fact_lines` as the card body in serif, a small mono source chip linking `report_pdf_url` (chip label varies: `[MSHA report ↗]` for `msha_final`, `[WV state report ↗]` for `state_wv`, `[MSHA preliminary ↗]` for `msha_preliminary`, etc.), and a `cause_category` tag.
- **Status labels render when not the canonical case.** If `report_status=preliminary`, render a small `preliminary — subject to revision` label on the card. If `contest_status=contested`, render a small `findings contested` label. Neither label suppresses the card; both add honest context.
- **Inline source chip on every card.** No footer disclaimer required — the source is always one click away from any claim. (Footer-level "this site uses AI" copy still optional but no longer load-bearing.)
- **Author voice belongs to the surrounding section chrome** (heading, sub, transitions), not to any extracted card content. Mixing them is a bug.

### Tool catalog updates (additions to Phase 3)

Append these to the Phase 3 tool list:

- `safety_violations(mine_id: int, year_range: tuple[int, int] | None = None) -> dict` — S&S count, total penalties, top violation types
- `withdrawal_orders(mine_id: int) -> list[dict]` — every 107(a) order, date and reason
- `fatality_narrative(mine_id: int, date: str | None = None) -> list[dict]` — investigation summaries with MSHA PDF URLs

### Skill prompt updates (runtime agent, distinct from the build-time extractor)

Teach Claude:
- The legal weight of a 107(a) order ("imminent danger withdrawal" — the strongest enforcement tool MSHA has).
- The S&S classification ("significant and substantial" — a citation tier predicting serious injury risk).
- The contest-status nuance: a contested-but-unruled citation is still data; surface the contest label, do not suppress.
- **Fatality narratives are passed through, not paraphrased.** When `fatality_narrative` is called, the agent renders the `fact_lines` as-is (or with minimal connective tissue) and includes the source URL chip. The agent does not rewrite, soften, amplify, or editorialize the facts. If the user asks "what happened," the answer is MSHA's facts plus the source link — full stop.
- **No comparative superlatives.** "Most dangerous mine in WV" is editorial. "Highest S&S count in WV in 2023" is factual *and* requires citing the rank computation. Default to factual; refuse the editorial framing even if the user asks for it.
- **Voice boundary.** The agent never inserts editorial framing of its own ("tragically", "preventably", "shockingly"). The site's editorial voice belongs to the page copy, not to the data layer or the agent's responses. This is a hard line.
- Refusal pattern: never speculate beyond what the investigation report concludes; never compare across mines without a tool-computed basis; never name individuals.

### Acceptance for Phase 3.A

- All four new Parquets in R2.
- Three new tools wired into the agent.
- `/ask "what happened at Upper Big Branch"` returns short declarative facts (no regulator prose, no editorial), with the MSHA report URL as a source chip.
- `/ask "which mines have been shut down by 107(a) orders"` returns a list of mine IDs with order counts.
- Spot-check 10 random extracted fatality rows: zero personal names, zero softening adverbs, zero amplifying adjectives, every row has a `report_pdf_url`, `report_source` and `report_status` populated, contest status correctly set per the source-priority rule.
- Verify source-priority: pick 3 incidents where MSHA final exists → confirm `report_source=msha_final`. Pick 1 recent incident where MSHA final does not yet exist but a state report does → confirm `report_source=state_<abbr>`. Pick 1 very recent incident with only a preliminary → confirm `report_status=preliminary` and the frontend renders the label.
- Frontend renders fatality cards in a dedicated section with the source chip on every card. Cost block remains untouched (still the author's voice).

---

## Sources for the data expansion

- [MSHA Open Government Initiative Portal](https://arlweb.msha.gov/opengovernmentdata/ogimsha.asp) — bulk pipe-delimited datasets
- [MSHA Data and Reports](https://www.msha.gov/data-and-reports) — entry point
- [MSHA Fatality Reports search](https://www.msha.gov/data-reports/fatality-reports/search) — per-incident reports
- [Data.gov MSHA Fatality Reports dataset](https://catalog.data.gov/dataset/msha-fatality-reports) — structured fatality summaries
- [Data.gov MSHA Accident Injuries Data Set](https://catalog.data.gov/dataset/msha-accident-injuries-data-set) — current source for the existing `MSHA_ACCIDENTS` table
