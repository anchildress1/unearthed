# unearthed — TODO

Living backlog. Add freely; resolve by deleting or moving to a CHANGELOG.

The Snowflake → R2 + DuckDB + Claude migration has its own phased brief: see [MIGRATION.md](./MIGRATION.md). The items below are the skinny version of that doc; do not let them drift from it.

## Migrate off Snowflake (target: ~$5/mo, see MIGRATION.md)

- [x] **Phase 0** — R2 bucket, Cloudflare API token, Anthropic key in Cloud Run secrets, bucket layout decided.
- [x] **Phase 1** — `scripts/export_snowflake_to_parquet.py`, `scripts/upload_to_r2.py`, `app/data_client.py` (DuckDB over httpfs), `/emissions/{plant}` migrated. Live cutover pending: R2 must have the Parquet files before deploying.
- [x] **Phase 2** — `/mine-for-me` and `/h3-density` migrated to DuckDB. H3 computed via `h3-py` at query time. Code-complete (PR #15); live cutover pending data upload.
- [ ] **Phase 3** — Replace Cortex Analyst with Claude Sonnet 4.6 + tool-using agent. Pre-bake mine narratives at build time. Replace Cortex Complete H3 summary.
- [ ] **Phase 4** — Hardening: question-hash cache, rate limit on `/ask`, Cloud Run config (`--min-instances=0 --cpu-throttling`), doc sync (AGENTS.md, PRD, footer credits, CortexChat rename).
- [ ] **Phase 5** — Cutover, one-week soak, tear down Snowflake account, drop `snowflake-connector-python`.

## Phase 1 / 2 live cutover checklist

- [ ] Run `scripts/export_snowflake_to_parquet.py` — validate row counts against Snowflake.
- [ ] Run `scripts/upload_to_r2.py` — confirm all Parquet paths exist under `s3://unearthed-data/`.
- [ ] Deploy Phase 2 image with `DATA_BASE_URL` + R2 secrets bound.
- [ ] Smoke-test: `curl /emissions/COLSTRIP`, `curl /mine-for-me` (SRVC), `curl /h3-density?resolution=4`.

## Cloud Run config

- [ ] Set `--min-instances=0`.
- [ ] Set `--cpu-throttling`.
- [ ] Audit container image size; trim if > 300 MB.

## Add more data — Phase 3.A (full scope in [MIGRATION.md](./MIGRATION.md))

- [ ] MSHA Violations dataset filtered to S&S, joined on mine_id. Tool: `safety_violations(mine_id)`.
- [ ] MSHA 107(a) Orders dataset. Tool: `withdrawal_orders(mine_id)`.
- [ ] MSHA Assessed Violations as `total_penalties` column in violations Parquet.
- [ ] MSHA Fatal Investigation Reports (PDFs) scraped + Claude-extracted into `fatality_narratives.parquet`. No PII, no editorial, source-priority rule enforced.
- [ ] Build pipeline: `scripts/scrape_msha_fatality_pdfs.py` + `scripts/extract_fatality_narratives.py`. Quarterly GitHub Action.
- [ ] Frontend: dedicated fatality-cards section (separate from cost block), source chip on every card.
