# PRD — `unearthed`

**Tagline:** Find the coal mine under contract to your local power plant. Watch it die in real time. Ask it questions.

**Repo name:** `unearthed`
**Description (for repo settings):** A live data product that shows any US resident which specific coal mine supplies their local power plant, using joined federal data from MSHA and EIA. Two AI voices: Google Gemini writes the emotional indictment, Snowflake Cortex answers factual questions about the data in natural language. Built for the DEV Weekend Challenge: Earth Day Edition.

**Status:** Draft — for submission by Monday 2026-04-20 06:59 UTC
**Author:** Ashley
**Sponsor categories targeted:** Google Gemini (primary), Snowflake Cortex (primary — genuine AI use, not bare warehouse)

---

## 1. Problem Statement

Americans pay a monthly electric bill that quietly finances specific, named mountains being removed and specific, named seams being cut. Most people cannot name a single coal mine, let alone *their* mine — the one operating under contract to the power plant that serves their grid. The abstraction is load-bearing for the industry: you cannot grieve what you cannot see.

Public federal data (MSHA Mines, MSHA Quarterly Production, EIA-923 Fuel Receipts, EIA-860 Plants) already records every monthly coal shipment from every US mine to every US power plant at MSHA-Mine-ID granularity. The data exists. It has never been assembled into a consumer experience that names the contract between a user's refrigerator and a specific county in Appalachia, Wyoming, or Illinois.

**Cost of not solving:** Earth Day content recycles the same abstract statistics ("coal emits X tons of CO2") that have demonstrably failed to move behavior for fifty years. Specificity — *your* mine, *your* operator, *your* county — is a different emotional instrument.

## 2. Goals

1. **Ship a working, submittable artifact to DEV by 2026-04-20 06:59 UTC.** Measured by: submission accepted, completion badge received.
2. **Qualify for two sponsor prize categories (Gemini + Snowflake Cortex)** with genuine, non-trivial use of each. Measured by: both categories tagged in the submission post; Gemini drives the emotional prose, Cortex drives factual Q&A and inline SQL AI.
3. **Produce a dev.to post that earns ≥100 reactions and ≥20 comments in the first 72 hours.** Measured by: dev.to analytics.
4. **Deliver plant-level granularity, not state-level.** Measured by: the rendered output names a specific receiving power plant and a specific source mine with coordinates, operator, and annual tonnage under contract.
5. **Render a repeatable, shareable reveal moment** — a map zoom from user location → local power plant → source mine, with indictment prose keyed to that specific chain, plus a natural-language Q&A interface against the underlying data. Measured by: shareable URL, per-user differentiated output, working Cortex Analyst chat.

## 3. Non-Goals

1. **No user accounts, no persistence, no login.** Auth is scope poison for a weekend ship. Every visit is stateless.
2. **No real-time EIA API integration.** EIA-923 is published annually on a ~12-month lag; using the 2024 annual release (published late 2025) is fine and avoids the need for an EIA API key at runtime.
3. **No worldwide coverage.** US only. Reason: MSHA + EIA data is US-specific; international equivalents require a different data spine.
4. **No recent or named-individual photography.** Hero images are pre-1980 public-domain archival only. Reason: ethics and legal risk of putting living miners in a guilt art piece without consent.
5. **No appliance-level per-watt physics simulation.** The appliance toggles are emotional affordances, not engineering. Each toggle applies a fixed coefficient to the particle rate. Reason: simulation fidelity is not what makes the product work.
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
- **US7.** As a visitor, I want to toggle appliances on/off and watch the tonnage rate visibly change, so that I feel the connection between my consumption and the mine.
- **US8.** As a visitor, I want to share my specific result via a URL or image, so that I can spread the experience to my network with my mine's name in the share text.
- **US9.** As a visitor, I want to ask natural-language questions about my mine or my grid ("how much did this mine produce last year?", "what other plants buy from this operator?") and receive real answers pulled from the federal data, so that my curiosity can deepen past the initial reveal.
- **US10.** As a visitor unsure what to ask, I want to tap pre-built question chips ("Is this mine still active?", "Who else buys from this operator?") and still get the natural-language experience, so that I am not forced to come up with questions cold.

### Secondary persona: DEV challenge judge

- **US9.** As a judge, I want to see a writeup that clearly explains what was built, how Gemini and Snowflake were used, and why it matters, so that I can evaluate relevance, creativity, technical execution, and writing quality quickly.
- **US10.** As a judge, I want to run the demo and receive a working result for my own location without setup, so that I can evaluate whether the feature actually functions end-to-end.

### Edge cases

- **Location outside the US.** Show a graceful "US grid data only — try the state picker to see what a US resident sees" fallback.
- **Location in a state with no active coal mines supplying local plants** (e.g., California, Hawaii). Show the mine supplying the nearest coal-burning plant that feeds any part of their eGRID subregion, or fall back to the national median contract.
- **Gemini API failure.** Fall back to a pre-rendered template with data interpolated (no AI prose) rather than breaking.
- **Snowflake query timeout.** Cache the top mine per subregion as a static JSON fallback keyed by subregion ID.
- **Cortex Analyst misfires on a user question.** Display the generated SQL plus a "I could not answer that confidently" message. Honesty beats a hallucinated number.
- **User types a question outside the data model's scope** ("what's the weather?"). Semantic model guardrails reject; UI offers the chip suggestions instead.

## 5. Requirements

### P0 — Must-Have (feature does not ship without these)

**P0-1. Data pipeline into Snowflake.**
- Four source datasets loaded: MSHA Mines (current), MSHA Quarterly Production (through 2024), EIA-923 Fuel Receipts (2024 annual, published 2025), EIA-860 Plants (2024 annual, published 2025).
- Filtered to coal only. Keyed by MSHA Mine ID.
- Two views: `v_mine_for_plant` (mine rankings per plant) and `v_mine_for_subregion` (aggregated mine rankings per eGRID subregion).
- Materialized factual-summary column on `v_mine_for_subregion` populated by `SNOWFLAKE.CORTEX.COMPLETE` — a 2-3 sentence factual recap per top mine, generated inline in SQL at build time.

**Acceptance criteria:**
- Given the four source files loaded, when I query `v_mine_for_subregion` for subregion `SRVC` (WV/VA), then I get back a ranked list of at least 5 source mines with operator names, coordinates, 2024 annual tonnage, and a Cortex-generated factual summary string.
- Query returns in under 2 seconds on an XS Snowflake warehouse.
- Cortex COMPLETE summary column is populated for every row with no nulls.

**P0-2. Geolocation → eGRID subregion lookup.**
- Browser geolocation API with permission prompt.
- Local point-in-polygon against bundled eGRID subregion GeoJSON (~500 KB asset).
- Manual state-picker fallback when permission is denied or geolocation fails.

**Acceptance criteria:**
- Given I grant location permission in Charleston WV, when the page loads, then the detected subregion is `SRVC` within 2 seconds.
- Given I deny permission, when I select "West Virginia" from the fallback dropdown, then subregion is inferred as `SRVC`.
- Given I am outside the US, when the page loads, then I see a graceful fallback message and can still use the state picker.

**P0-3. Cloud Run API endpoint.**
- Single endpoint: `POST /mine-for-me` with body `{subregion_id}`.
- Executes the Snowflake query, calls Gemini for prose, returns JSON: `{mine, plant, tons, prose, user_coords, mine_coords, plant_coords}`.
- FastAPI framework, Python 3.11+, matches the pattern from the "dragon smelter" project.

**Acceptance criteria:**
- Given a valid subregion ID, when I POST to the endpoint, then I get back a JSON payload with all required fields within 5 seconds.
- Given Snowflake is down, when I POST, then the endpoint falls back to a cached static JSON and returns a result with a `degraded: true` flag.
- Given Gemini is down, when I POST, then the endpoint falls back to a templated string and returns a result with `degraded: true`.

**P0-4. Map reveal sequence with MapLibre GL.**
- Map loads zoomed out, then animates: user location → power plant → source mine.
- Arc line drawn between the three points.
- Pins with labels for each stop.

**Acceptance criteria:**
- Given a successful API response, when the map sequence runs, then it completes within 8 seconds from payload to final zoom.
- Given a mobile viewport (≥375px wide), when the sequence runs, then all three pins and labels are readable without horizontal scroll.

**P0-5. PixiJS particle overlay with tonnage ticker.**
- Hero image (one of two, routed by mine type — surface vs underground) fades in after map sequence.
- Coal-dust particle simulation runs on top.
- Tonnage ticker counts up at rate = `annual_tons / seconds_in_year`, displayed to two decimal places.

**Acceptance criteria:**
- Given the map sequence completes, when the hero image fades in, then particles begin within 500ms.
- Given I remain on the page for 60 seconds, when I look at the ticker, then it has incremented by a visible amount.
- Given I'm on a low-end laptop, when particles render, then frame rate stays above 30 FPS (ParticleContainer sprite batching required).

**P0-6. Gemini-generated indictment prose.**
- Prompt input: `{mine_name, mine_operator, mine_county, mine_state, mine_type, plant_name, plant_operator, tons_latest_year, tons_year, subregion_id}`.
- Output: 3–5 sentences naming the mine, the plant, the operator, and the tonnage. Grief-coded register. No cheerful hedging.
- Cached per-subregion at the API layer to minimize Gemini calls (TTL: until the next deploy).

**Acceptance criteria:**
- Given a mine record for Hobet (WV), when Gemini renders prose, then the output contains the strings `Hobet`, the operator name, the county name, and the tonnage figure.
- Given the same subregion requested twice within 5 minutes, when the second request hits the API, then it returns cached prose without a second Gemini call.

**P0-7. Share URL with mine name in metadata.**
- URL structure: `unearth.app/?m=hobet-wv` (or similar slug).
- Open Graph tags populated with mine name, share image, and a 1-sentence hook.

**Acceptance criteria:**
- Given I arrive at the page via a share URL, when the page loads, then it jumps straight to that mine's reveal without re-geolocating.
- Given a Twitter or LinkedIn preview is generated, when the share URL is pasted, then the preview shows the mine name and a hook sentence.

**P0-8. Cortex Analyst "Ask your grid" chat.**
- Semantic model YAML defined over the 5 raw tables (MSHA_MINES, MSHA_QUARTERLY_PRODUCTION, EIA_923_FUEL_RECEIPTS, EIA_860_PLANTS, PLANT_SUBREGION_LOOKUP). MRT views serve `/mine-for-me` via hand-written SQL, not Analyst. Restricted to safe, meaningful questions: mine production over time, plant-to-mine contracts, operator-level rollups, subregion-level totals.
- Frontend: a text input + 3-5 pre-built question chips appear below the indictment prose. Tapping a chip fires the question through Cortex Analyst; typing is also supported.
- Chat transcript displays: the user's question, the generated SQL (collapsed by default, expandable), and the natural-language answer.
- FastAPI endpoint `POST /ask` wraps the Snowflake Cortex Analyst REST call.

**Acceptance criteria:**
- Given I am on the reveal page for Hobet (WV), when I tap the chip "How much has this mine produced since 2020?", then within 5 seconds I see a numeric answer backed by real `production` table data and the generated SQL expandable.
- Given I type a question outside the semantic model's scope, when I submit, then I see a graceful "I can answer questions about mines, plants, shipments, and operators — try one of these:" with the chips highlighted.
- Given the Cortex Analyst endpoint errors, when I submit, then I see a fallback message and the reveal page continues to function normally.

**P0-9. DEV submission post.**
- Published on dev.to using the challenge template.
- Hero gif (≤6 seconds) showing the reveal sequence + a secondary gif showing the Cortex Analyst chat in action.
- Writeup explains: what it does, why, how Gemini is used for prose, how Snowflake Cortex is used for both inline SQL AI (COMPLETE) and natural-language Q&A (Analyst), data sources, tech stack.
- Tags: `#devchallenge #earthdaychallenge #googleai #snowflake` (plus per-challenge-guidance tags).

**Acceptance criteria:**
- Given the post is published, when I read it, then the Gemini section shows the actual prompt used and at least one example of the generated prose.
- Given the post is published, when I read it, then the Snowflake section shows: one of the two views' SQL (with the Cortex COMPLETE call visible), the semantic model snippet for Cortex Analyst, and one example user question with its generated SQL and answer.

### P1 — Should-Have (fast-follow if time)

- **P1-1.** Free-form Cortex Analyst input (unguarded by chips). Users type anything; semantic model rejects out-of-scope; honest "I can't answer that" for misfires.
- **P1-2.** Appliance toggles (fridge, AC, router, screen) that modulate the particle/ticker rate with fixed coefficients.
- **P1-3.** "Memorial wall" below the hero — a scrollable list of the top 20 source mines in the visitor's subregion.
- **P1-4.** Per-mine slug URLs (not just per-subregion) for deeper share specificity.

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
| Prize categories qualified | 2 (Gemini + Snowflake) | 2 + completion badge | Post tags + writeup content |
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
| Which Cortex LLM model for COMPLETE (llama3-8b vs mistral-large vs claude-3-5-sonnet)? | Ashley | Non-blocking — start with llama3-8b for cost/speed, switch if prose is flat |
| Semantic model YAML scope: which 4-6 question patterns do we explicitly support in Cortex Analyst? | Ashley | Blocking — must draft Friday prep so chip labels and YAML match |
| Which specific hero images from LoC / Wikimedia do we use, and are they confirmed public domain with clear provenance? | Ashley | Blocking — needs Friday curation |
| Does the "dragon smelter" FastAPI pattern work as-is for Snowflake's Python connector + Cortex Analyst REST API, or does it need an async wrapper? | Ashley | Non-blocking — sync is fine; Cortex Analyst is a plain REST POST |
| Do we want a splash page / intro copy before the reveal, or does the reveal start immediately on click? | Ashley | Non-blocking — design call |
| Should we record the hero gif with a real browser + real location, or stage it? | Ashley | Non-blocking — stage it for the demo, noting in writeup |
| What Gemini model tier and token budget? | Ashley | Non-blocking — start with Flash for cost |

## 8. Timeline Considerations

**Hard deadline:** DEV submission by **2026-04-20 06:59 UTC** (Monday morning).

**Build window constraints:**
- Thursday 2026-04-16 (today) — unavailable
- Friday 2026-04-17 — available for prep work (data staging, image curation, prompt drafting)
- Saturday 2026-04-18 — unavailable morning, available afternoon/evening for Snowflake setup + map/geolocation build
- Sunday 2026-04-19 — available for PixiJS overlay, Gemini integration, Cloud Run deploy, dev.to writeup
- Monday 2026-04-20 — buffer for submission only

**Phasing:**

| Block | Duration | Scope |
|---|---|---|
| Friday prep (Claude-assisted) | ~4 hrs | Build `mines.json`, filter MSHA data, download EIA-923, download EIA-860, curate 2 hero images, bundle eGRID GeoJSON, draft Gemini prompt, validate SQL against local duckdb, **draft semantic model YAML + 4-5 supported question patterns for Cortex Analyst** |
| Sat PM: Snowflake + API | ~5 hrs | Load 4 tables via Snowsight, create 2 views, add Cortex COMPLETE column, upload semantic model, test Cortex Analyst in Snowsight chat, validate query, FastAPI scaffold, `/mine-for-me` + `/ask` endpoints, Gemini integration |
| Sat night: Map + geolocation | ~3 hrs | MapLibre scene, zoom sequence, geolocation flow, state-picker fallback |
| Sun AM: PixiJS + chat UI | ~4 hrs | ParticleContainer, tonnage ticker, hero image fade, Cortex Analyst chip UI + text input, chat transcript rendering |
| Sun PM: Deploy + writeup | ~3 hrs | Cloud Run deploy, dev.to post, two gifs (reveal + chat), submission |

**Total build hours:** ~15-16. P1 appliance toggles / free-form chat input are the first cuts if slipping.

**Biggest risks:**
1. **Cortex Analyst semantic model churn.** Writing a YAML that actually routes the 4-5 chip questions to correct SQL can eat more than 2 hours if it fights you. Mitigation: start with a minimal YAML covering only the chip questions, not open-ended NL. If Analyst is still flaky by Sunday noon, degrade P0-8 to "Cortex COMPLETE answers chip questions via hand-written SQL templates" — still Cortex, still AI, ships.
2. **Cortex COMPLETE column generation cost/time.** ~500 mines × 1 LLM call each ≈ cheap but not instant. Run it Friday as part of ETL prep, not Sunday. Mitigation: bake the column during initial table load so it's done by Saturday.
3. Hero image curation rabbit hole. Mitigation: pick 2 images Friday, move on. No perfectionism.
4. MapLibre zoom choreography taking longer than expected. Mitigation: if zoom sequence is janky by Sunday noon, cut to an instant cross-fade between 3 map views.
5. **Snowflake → FastAPI auth.** Key-pair auth is less cranky than user/password for prod. Mitigation: use Snowflake's `snowflake-connector-python` with key-pair auth from Sat AM onward. Store private key as Cloud Run secret.

---

## Tech Stack (locked)

- **Frontend:** Vanilla JS or a light framework of Ashley's choosing. MapLibre GL JS for the map. PixiJS for the particle overlay. Stacked-canvas approach to keep them cooperating. Chat UI for Cortex Analyst: plain HTML form + chip buttons + transcript div.
- **Backend:** Python 3.11 + FastAPI, matching the "dragon smelter" pattern. Two endpoints: `/mine-for-me` (reveal payload) and `/ask` (Cortex Analyst pass-through).
- **Data platform:** Snowflake ($400 / 30-day free trial). 4 base tables + 2 views + 1 materialized Cortex-generated factual-summary column. XS warehouse.
- **AI — emotional:** Google Gemini (Flash tier).
- **AI — factual:** Snowflake Cortex — `CORTEX.COMPLETE` (llama3-8b default) inline in SQL for summary column; Cortex Analyst with hand-written semantic model YAML for NL Q&A.
- **Deploy:** Cloud Run. Private key for Snowflake stored as Secret Manager secret.
- **Assets:** Bundled GeoJSON (eGRID subregions, ~500 KB), 2 hero images (pre-1980 public domain), fallback per-subregion JSON, semantic model YAML checked into repo.

## Data Sources (locked)

| Source | Format | Use | License |
|---|---|---|---|
| MSHA Mines | CSV (pipe-delimited, from zip) | Mine registry, coordinates, operator, county | Public domain (US gov) |
| MSHA Quarterly Production | CSV | Tonnage per mine per quarter | Public domain |
| EIA-923 Fuel Receipts (2024 annual, published 2025) | XLSX | Coal shipments: mine → plant → tons | Public domain |
| EIA-860 Plants (2024 annual, published 2025) | XLSX | Plant locations, capacity, subregion | Public domain |
| EPA eGRID subregion boundaries | GeoJSON | Point-in-polygon for user location | Public domain |
| Library of Congress archival photos | JPG/TIFF | Hero imagery (surface + underground) | Public domain (pre-1980, curated) |

---

*End of PRD.*
