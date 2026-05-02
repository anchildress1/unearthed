# unearthed — TODO

Living backlog. Add freely; resolve by deleting or moving to a CHANGELOG.

The Snowflake → R2 + DuckDB + Claude migration has its own phased brief: see [MIGRATION.md](./MIGRATION.md). The items below are the skinny version of that doc; do not let them drift from it.

## Migrate off Snowflake (target: ~$5/mo, see MIGRATION.md)

- [ ] **Phase 0** — R2 bucket, Cloudflare API token, Anthropic key in Cloud Run secrets, bucket layout decided. Manual setup; no code dependency.
- [x] **Phase 1** — Snowflake → Parquet export (`scripts/export_snowflake_to_parquet.py`), R2 upload (`scripts/upload_to_r2.py`), `app/data_client.py` (DuckDB over httpfs), `/emissions/{plant}` migrated. Live cutover requires Phase 0 to land first; the live `curl` spot-check from MIGRATION.md §Phase 1 stays open until R2 actually has the parquet.
- [ ] **Phase 2** — Migrate `/mine-for-me` and `/h3-density` to DuckDB. `/ask` still on Cortex Analyst at end of phase.
- [ ] **Phase 3** — Replace Cortex Analyst with Claude Sonnet 4.6 + tools. Pre-bake mine narratives at build time. Replace Cortex Complete H3 summary.
- [ ] **Phase 4** — Hardening: question-hash cache, rate limit on `/ask`, Cloud Run config, doc sync (AGENTS.md, PRD, system-diagram, footer credits).
- [ ] **Phase 5** — Cutover, observe one week, tear down Snowflake account, drop `snowflake-connector-python`.

## Cloud Run cost fix (target: $0-1/mo from current $3-5)

- [ ] Set `--min-instances=0`.
- [ ] Set `--cpu-throttling` (CPU only during requests, not always-allocated).
- [ ] Audit container image size; trim if >300MB.
- [ ] Audit health-check / uptime ping frequency. Anything more than 1/5min is paying to stay warm.

## Add more data — Phase 3.A (full scope in [MIGRATION.md](./MIGRATION.md))

- [ ] **MSHA Violations dataset** filtered to S&S, joined on mine_id, with contest status preserved. New tool: `safety_violations(mine_id)`.
- [ ] **MSHA 107(a) Orders dataset.** New tool: `withdrawal_orders(mine_id)`. Surfaces forced shutdowns — the strongest enforcement signal MSHA has.
- [ ] **MSHA Assessed Violations** rolled into the violations parquet as `total_penalties`.
- [ ] **MSHA Fatal Investigation Reports (PDFs)** scraped, Claude-extracted at build time into `fatality_narratives.parquet` as short declarative `fact_lines` (no PII, no regulator prose, no editorial). **Source-priority:** MSHA final > state final > MSHA preliminary. One source per incident, never blended. Re-extract & replace when a final supersedes a preliminary. Surface `report_status` and `contest_status` labels on the card.
- [ ] Build pipeline: `scripts/scrape_msha_fatality_pdfs.py` + `scripts/extract_fatality_narratives.py`. GitHub Action for quarterly refresh.
- [ ] Skill prompt: teach Claude the legal weight of 107(a), the S&S tier, the contest-status nuance, and the **voice boundary** — author voice in page chrome, MSHA facts in the data layer, never the two shall touch.
- [ ] Frontend: dedicated fatality-cards section (separate from cost block), source chip on every card, cost block untouched.

## Site polish

- [ ] **Donate button** — wire to chosen platform (Buy Me a Coffee / Ko-fi / GitHub Sponsors / Stripe). Footer placeholder is in place.
- [ ] Add `og:image` + Twitter card meta.
- [ ] Lighthouse re-audit after migration.
