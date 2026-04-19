# PRD — `unearthed`

**Tagline:** Find the coal mine under contract to your local power plant. Watch it die in real time. Ask it questions.

**Repo name:** `unearthed`
**Description (for repo settings):** A live data product that shows any US resident which specific coal mine supplies their local power plant, using joined federal data from MSHA and EIA. Snowflake Cortex Analyst answers factual questions about the data in natural language. Built for the DEV Weekend Challenge: Earth Day Edition.

**Status:** Draft — for submission by Monday 2026-04-20 06:59 UTC
**Author:** Ashley
**Sponsor categories targeted:** Snowflake Cortex (primary — genuine AI use, not bare warehouse)

---

## 1. Problem Statement

Americans pay a monthly electric bill that quietly finances specific, named mountains being removed and specific, named seams being cut. Most people cannot name a single coal mine, let alone *their* mine — the one operating under contract to the power plant that serves their grid. The abstraction is load-bearing for the industry: you cannot grieve what you cannot see.

Public federal data (MSHA Mines, MSHA Quarterly Production, EIA-923 Fuel Receipts, EIA-860 Plants) already records every monthly coal shipment from every US mine to every US power plant at MSHA-Mine-ID granularity. The data exists. It has never been assembled into a consumer experience that names the contract between a user's refrigerator and a specific county in Appalachia, Wyoming, or Illinois.

**Cost of not solving:** Earth Day content recycles the same abstract statistics ("coal emits X tons of CO2") that have demonstrably failed to move behavior for fifty years. Specificity — *your* mine, *your* operator, *your* county — is a different emotional instrument.

## 2. Goals

1. **Ship a working, submittable artifact to DEV by 2026-04-20 06:59 UTC.** Measured by: submission accepted, completion badge received.
2. **Qualify for the Snowflake Cortex sponsor prize category** with genuine, non-trivial use. Measured by: category tagged in the submission post; Cortex drives factual Q&A via semantic model.
3. **Produce a dev.to post that earns ≥100 reactions and ≥20 comments in the first 72 hours.** Measured by: dev.to analytics.
4. **Deliver plant-level granularity, not state-level.** Measured by: the rendered output names a specific receiving power plant and a specific source mine with coordinates, operator, and annual tonnage under contract.
5. **Render a repeatable, shareable reveal moment** — a map zoom from user location → local power plant → source mine, with indictment prose keyed to that specific chain, plus a natural-language Q&A interface against the underlying data. Measured by: shareable URL, per-user differentiated output, working Cortex Analyst chat.

## 3. Non-Goals

1. **No user accounts, no persistence, no login.** Auth is scope poison for a weekend ship. Every visit is stateless.
2. **No real-time EIA API integration.** EIA-923 is published annually on a ~12-month lag; using the 2024 annual release (published late 2025) is fine and avoids the need for an EIA API key at runtime.
3. **No worldwide coverage.** US only. Reason: MSHA + EIA data is US-specific; international equivalents require a different data spine.
4. **No recent or named-individual photography.** Reason: ethics and legal risk of putting living miners in a guilt art piece without consent.
5. **No appliance-level per-watt physics simulation.** Out of scope.
6. **No carbon footprint calculator.** Adjacent but different product. Done to death. Explicitly left for someone else.
7. **No agentic utility-account integration (Auth0 for Agents).** Considered, rejected for scope. The static grid-mix lookup is sufficient for v1.

## 4. User Stories

### Primary persona: curious US resident reading dev.to on a laptop

- **US1.** As a visitor, I want to see my specific coal mine named within 10 seconds of opening the page, so that the abstraction of "coal power" becomes concrete.
- **US2.** As a visitor, I want to grant or decline location permission with a single click, so that I am not forced into sharing location but can if I want the tailored experience.
- **US3.** As a visitor who denies geolocation, I want to pick my state from a dropdown, so that I can still see a relevant result without sharing precise location.
- **US4.** As a visitor, I want to watch a cinematic map zoom from my location to the source mine via the intermediary power plant, so that I understand the *contract* — not just the mine's existence, but its relationship to my grid.
- **US5.** As a visitor, I want to read 3–5 sentences of prose that name the mine's operator, county, annual tonnage, and the specific power plant buying from them, so that the data feels personal rather than abstract.
- **US6.** As a visitor, I want to see a running tonnage ticker that counts up while I stay on the page, so that the cost scales with my continued presence.
- **US8.** As a visitor, I want to share my specific result via a URL, so that I can spread the experience to my network with my mine's name in the share text.
- **US9.** As a visitor, I want to ask natural-language questions about my mine or my grid ("how much did this mine produce last year?", "what other plants buy from this operator?") and receive real answers pulled from the federal data, so that my curiosity can deepen past the initial reveal.
- **US10.** As a visitor unsure what to ask, I want to tap pre-built question chips ("Is this mine still active?", "Who else buys from this operator?") and still get the natural-language experience, so that I am not forced to come up with questions cold.

### Secondary persona: DEV challenge judge

- **US9.** As a judge, I want to see a writeup that clearly explains what was built, how Snowflake Cortex was used, and why it matters, so that I can evaluate relevance, creativity, technical execution, and writing quality quickly.
- **US10.** As a judge, I want to run the demo and receive a working result for my own location without setup, so that I can evaluate whether the feature actually functions end-to-end.

### Edge cases

- **Location outside the US.** Show a graceful "US grid data only — try the state picker to see what a US resident sees" fallback.
- **Location in a state with no active coal mines supplying local plants** (e.g., California, Hawaii). Show the mine supplying the nearest coal-burning plant that feeds any part of their eGRID subregion, or fall back to the national median contract.
- **Snowflake query timeout.** Cache the top mine per subregion as a static JSON fallback keyed by subregion ID.
- **Cortex Analyst misfires on a user question.** Display the generated SQL plus a "I could not answer that confidently" message. Honesty beats a hallucinated number.
- **User types a question outside the data model's scope** ("what's the weather?"). Semantic model guardrails reject; UI offers the chip suggestions instead.

## 5. Requirements

### P0 — Must-Have (feature does not ship without these)

**P0-1. Data pipeline into Snowflake.**
- Four source datasets loaded: MSHA Mines (current), MSHA Quarterly Production (through 2024), EIA-923 Fuel Receipts (2024 annual, published 2025), EIA-860 Plants (2024 annual, published 2025).
- Filtered to coal only. Keyed by MSHA Mine ID.
- Two views: `V_MINE_FOR_PLANT` (mine rankings per plant) and `V_MINE_FOR_SUBREGION` (aggregated mine rankings per eGRID subregion).
- Materialized factual-summary column on `V_MINE_FOR_SUBREGION` populated by `SNOWFLAKE.CORTEX.COMPLETE` — a 2-3 sentence factual recap per top mine, generated inline in SQL at build time.

**Acceptance criteria:**
- Given the four source files loaded, when I query `V_MINE_FOR_SUBREGION` for subregion `SRVC` (WV/VA), then I get back a ranked list of at least 5 source mines with operator names, coordinates, 2024 annual tonnage, and a Cortex-generated factual summary string.
- Query returns in under 2 seconds on an XS Snowflake warehouse.
- Cortex COMPLETE summary column is populated for every row with no nulls.

**P0-2. Geolocation → eGRID subregion lookup.**
- Browser geolocation API with permission prompt.
- Local point-in-polygon against bundled eGRID subregion GeoJSON (~1 MB asset).
- Manual state-picker fallback when permission is denied or geolocation fails.

**Acceptance criteria:**
- Given I grant location permission in Charleston WV, when the page loads, then the detected subregion is `SRVC` within 2 seconds.
- Given I deny permission, when I select "West Virginia" from the fallback dropdown, then subregion is inferred as `SRVC`.
- Given I am outside the US, when the page loads, then I see a graceful fallback message and can still use the state picker.

**P0-3. Cloud Run API endpoint.**
- `POST /mine-for-me` with body `{subregion_id}`.
- Executes the Snowflake query, returns JSON: `{mine, plant, tons, prose, mine_coords, plant_coords, degraded}`.
- FastAPI framework, Python 3.12.

**Acceptance criteria:**
- Given a valid subregion ID, when I POST to the endpoint, then I get back a JSON payload with all required fields within 5 seconds.
- Given Snowflake is down, when I POST, then the endpoint falls back to a cached static JSON and returns a result with a `degraded: true` flag.

**P0-4. Map reveal sequence with MapLibre GL.**
- Map loads zoomed out, then animates: user location → power plant → source mine.
- Arc line drawn between the three points.
- Pins with labels for each stop.

**Acceptance criteria:**
- Given a successful API response, when the map sequence runs, then it completes within 8 seconds from payload to final zoom.
- Given a mobile viewport (≥375px wide), when the sequence runs, then all three pins and labels are readable without horizontal scroll.

**P0-5. Tonnage ticker.**
- Tonnage ticker counts up at rate = `annual_tons / seconds_in_year`, displayed to two decimal places.
- Appears in the info panel after the map reveal sequence.

**Acceptance criteria:**
- Given I remain on the page for 60 seconds, when I look at the ticker, then it has incremented by a visible amount.

**P0-6. Share URL.**
- URL structure: `/?m=SRVC` (eGRID subregion ID).
- Open Graph tags updated client-side with mine name after reveal.

**Acceptance criteria:**
- Given I arrive at the page via a share URL, when the page loads, then it jumps straight to that subregion's reveal without re-geolocating.

**P0-7. Cortex Analyst "Ask your grid" chat.**
- Semantic model YAML defined over the 5 raw tables (MSHA_MINES, MSHA_QUARTERLY_PRODUCTION, EIA_923_FUEL_RECEIPTS, EIA_860_PLANTS, PLANT_SUBREGION_LOOKUP). MRT views serve `/mine-for-me` via hand-written SQL, not Analyst. Restricted to safe, meaningful questions: mine production over time, plant-to-mine contracts, operator-level rollups, subregion-level totals.
- Frontend: a text input + 3-5 pre-built question chips appear below the indictment prose. Tapping a chip fires the question through Cortex Analyst; typing is also supported.
- Chat transcript displays: the user's question, the generated SQL (collapsed by default, expandable), and the natural-language answer.
- FastAPI endpoint `POST /ask` wraps the Snowflake Cortex Analyst REST call.

**Acceptance criteria:**
- Given I am on the reveal page for Hobet (WV), when I tap the chip "How much has this mine produced since 2020?", then within 5 seconds I see a numeric answer backed by real `production` table data and the generated SQL expandable.
- Given I type a question outside the semantic model's scope, when I submit, then I see a graceful "I can answer questions about mines, plants, shipments, and operators — try one of these:" with the chips highlighted.
- Given the Cortex Analyst endpoint errors, when I submit, then I see a fallback message and the reveal page continues to function normally.

**P0-8. DEV submission post.**
- Published on dev.to using the challenge template.
- Hero gif (≤6 seconds) showing the reveal sequence + a secondary gif showing the Cortex Analyst chat in action.
- Writeup explains: what it does, why, how Snowflake Cortex Analyst is used for NL Q&A, data sources, tech stack.
- Tags: `#devchallenge #earthdaychallenge #snowflake` (plus per-challenge-guidance tags).

**Acceptance criteria:**
- Given the post is published, when I read it, then the Snowflake section shows: the semantic model snippet for Cortex Analyst, and one example user question with its generated SQL and answer.

### P1 — Should-Have (fast-follow if time)

- **P1-1.** Free-form Cortex Analyst input (unguarded by chips). Users type anything; semantic model rejects out-of-scope; honest "I can't answer that" for misfires.
- **P1-2.** Per-mine slug URLs (not just per-subregion) for deeper share specificity.
- **P1-3.** Replace Gemini prose with Cortex Analyst-generated data summary using worker stats, production trends, and plant counts from Snowflake.

### P2 — Future Considerations (design in but do not build)

- **P2-1.** International expansion (requires a different data spine: IEA, EEA).
- **P2-2.** Auth0-for-Agents integration to pull the visitor's actual kWh from their utility account for true per-household tonnage.
- **P2-3.** Historical view — animate a mine's tonnage over the past decade to show its arc.
- **P2-4.** Non-coal fuels (natural gas well → plant contracts have different emotional weight but same architectural pattern).
- **P2-5.** Cortex Search over MSHA violation records for per-operator safety history (requires adding the MSHA Violations dataset).

## 6. Success Metrics

### Leading indicators (first 72 hours post-submission)

| Metric | Success | Stretch | Measurement |
|---|---|---|---|
| DEV submission accepted | Yes | — | Submission page confirms |
| Prize categories qualified | 1 (Snowflake) | 1 + completion badge | Post tags + writeup content |
| dev.to reactions | ≥100 | ≥500 | dev.to analytics |
| dev.to comments | ≥20 | ≥75 | dev.to analytics |
| Unique visitors to deployed app | ≥500 | ≥2,000 | Cloud Run logs / analytics |
| Share-back rate (visitors posting their mine name) | ≥5% of commenters | ≥15% | Manual tally of comments mentioning a mine name |

### Lagging indicators (10-day window to winner announcement)

| Metric | Success | Stretch | Measurement |
|---|---|---|---|
| Prize won | Any of 10 | Category-specific (Gemini or Snowflake) | 2026-04-30 announcement |
| GitHub stars on repo | ≥25 | ≥100 | GitHub |
| External shares (outside dev.to) | Detectable | Frontpage of any subreddit, HN, etc. | Search, referral logs |

## 7. Open Questions

| Question | Owner | Blocking? |
|---|---|---|
| Snowflake free-trial account confirmed | Ashley | **Resolved** — $400 / 30-day trial active |
| ~~Which Cortex LLM model for COMPLETE?~~ | Ashley | **Resolved** — Gemini removed. Cortex Complete re-introduced on `openai-gpt-5.2` for short safety prose (injuries-first, fatalities-second). Swapped from `openai-gpt-5-chat` after its 2026-03-01 Snowflake deprecation. Cortex Analyst drives the `/ask` NL→SQL chat. |
| Semantic model YAML scope: which 4-6 question patterns do we explicitly support in Cortex Analyst? | Ashley | Blocking — must draft Friday prep so chip labels and YAML match |
| ~~Which specific hero images?~~ | Ashley | **Resolved** — hero images removed from UI; OG meta only |
| Does the "dragon smelter" FastAPI pattern work as-is for Snowflake's Python connector + Cortex Analyst REST API, or does it need an async wrapper? | Ashley | Non-blocking — sync is fine; Cortex Analyst is a plain REST POST |
| Do we want a splash page / intro copy before the reveal, or does the reveal start immediately on click? | Ashley | Non-blocking — design call |
| Should we record the hero gif with a real browser + real location, or stage it? | Ashley | Non-blocking — stage it for the demo, noting in writeup |
| ~~What Gemini model tier?~~ | Ashley | **Resolved** — Gemini removed entirely |

## 8. Timeline Considerations

**Hard deadline:** DEV submission by **2026-04-20 06:59 UTC** (Monday morning).

**Build window constraints:**
- Thursday 2026-04-16 (today) — unavailable
- Friday 2026-04-17 — available for prep work (data staging, image curation, prompt drafting)
- Saturday 2026-04-18 — unavailable morning, available afternoon/evening for Snowflake setup + map/geolocation build
- Sunday 2026-04-19 — available for UI polish, Cloud Run deploy, dev.to writeup
- Monday 2026-04-20 — buffer for submission only

**Phasing:**

| Block | Duration | Scope |
|---|---|---|
| Friday prep (Claude-assisted) | ~4 hrs | Build `mines.json`, filter MSHA data, download EIA-923, download EIA-860, bundle eGRID GeoJSON, validate SQL against local duckdb, **draft semantic model YAML + 4-5 supported question patterns for Cortex Analyst** |
| Sat PM: Snowflake + API | ~5 hrs | Load 4 tables via Snowsight, create 2 views, upload semantic model, test Cortex Analyst in Snowsight chat, validate query, FastAPI scaffold, `/mine-for-me` + `/ask` endpoints |
| Sat night: Map + geolocation | ~3 hrs | MapLibre satellite basemap, zoom sequence with animated flow lines, geolocation flow, state-picker fallback |
| Sun AM: Chat UI + polish | ~4 hrs | Tonnage ticker, Cortex Analyst chip UI + text input, chat transcript rendering |
| Sun PM: Deploy + writeup | ~3 hrs | Cloud Run deploy, dev.to post, two gifs (reveal + chat), submission |

**Total build hours:** ~15-16. P1 appliance toggles / free-form chat input are the first cuts if slipping.

**Biggest risks:**
1. **Cortex Analyst semantic model churn.** Writing a YAML that actually routes the 4-5 chip questions to correct SQL can eat more than 2 hours if it fights you. Mitigation: start with a minimal YAML covering only the chip questions, not open-ended NL.
2. MapLibre zoom choreography taking longer than expected. Mitigation: if zoom sequence is janky by Sunday noon, cut to an instant cross-fade between 3 map views.
3. **Snowflake → FastAPI auth.** Key-pair auth is less cranky than user/password for prod. Mitigation: use Snowflake's `snowflake-connector-python` with key-pair auth from Sat AM onward. Store private key as Cloud Run secret.

---

## Tech Stack (locked)

- **Frontend:** Vanilla JS. MapLibre GL JS for the map (ESRI satellite basemap, animated flow lines). Chat UI for Cortex Analyst: plain HTML form + chip buttons + transcript div.
- **Backend:** Python 3.12 + FastAPI. Two endpoints: `/mine-for-me` (reveal payload) and `/ask` (Cortex Analyst pass-through).
- **Data platform:** Snowflake ($400 / 30-day free trial). 5 base tables + 2 views. XS warehouse.
- **AI:** Snowflake Cortex Analyst with hand-written semantic model YAML for NL Q&A.
- **Deploy:** Cloud Run. Private key for Snowflake stored as Secret Manager secret.
- **Assets:** Bundled GeoJSON (eGRID subregions, ~1 MB), fallback per-subregion JSON (19 files), semantic model YAML checked into repo.

## Data Sources (locked)

| Source | Format | Use | License |
|---|---|---|---|
| MSHA Mines | CSV (pipe-delimited, from zip) | Mine registry, coordinates, operator, county | Public domain (US gov) |
| MSHA Quarterly Production | CSV | Tonnage per mine per quarter | Public domain |
| EIA-923 Fuel Receipts (2024 annual, published 2025) | XLSX | Coal shipments: mine → plant → tons | Public domain |
| EIA-860 Plants (2024 annual, published 2025) | XLSX | Plant locations, capacity, subregion | Public domain |
| EPA eGRID subregion boundaries | GeoJSON | Point-in-polygon for user location | Public domain |

---

*End of PRD.*
