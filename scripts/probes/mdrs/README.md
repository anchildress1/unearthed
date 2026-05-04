# MDRS reverse-engineering probes

These scripts are not part of the production pipeline. They map MSHA's
MDRS (Mine Data Retrieval System) MicroStrategy dashboard so a future
scraper has a foothold instead of starting from zero. Run order matches
the filename prefix.

## Status

The production scraper at `scripts/mdrs_scrape_enforcement.py` runs end-to-end against a single mine (verified with mine ID `4609192`, Leer Mine). It loads MDRS, finds the Mine ID search widget, types, clicks the autocomplete match, clicks Submit, and captures the per-mine HTML. Drill-in confirmed via `drilled_in: true` and 6 violation markers in the response.

What still needs building: the per-mine page captures Mine Information (operator, address). Inside that page are clickable `mstrmojo-DocTextfield hasLink` widgets that drill INTO the Violations / 107(a) Orders / Inspections dashboards. Next session's work is to navigate each of those dashboards and extract the structured rows from their `mstrmojo-Grid` tables. The captured HTML contains a `Violations` widget with onclick handlers and a `Click to open Mine Inspections dashboard` title — both real navigable links from the per-mine landing.

## What we know

MDRS lives at `https://www.msha.gov/data-and-reports/mine-data-retrieval-system?mineId=<N>`. The outer page is a thin Drupal shell around an `iframe#iframe1` pointing at `https://microstrategy.msha.gov/MicroStrategy/asp/Main.aspx?...documentID=B546031C492F99BEAB6BCCB91635B608&...`. The `documentID` is the MDRS dashboard's MSTR Document ID; it is stable across sessions.

Three frames load on the page:

1. The outer Drupal page (carries the `mineId` URL param — but it is not propagated into the iframe; ignore)
2. The MSTR document iframe (the actual app)
3. A `pendoFrame` analytics widget (ignore)

**The production scraper requires a real Chrome User-Agent.** MSHA's MicroStrategy serves a degraded layout with class `mstr-unsupported-browser` when the UA does not match a current desktop Chrome, and the `mstrmojo-SimpleObjectInputBox` widgets do not render in that mode. The scraper pins a current Chrome UA and moves the polite project identifier to a custom `X-Unearthed-Source` header.

## What works and what doesn't

- The deep-link `?mineId=N` is **not** auto-passed into the iframe. Visiting `?mineId=1512805` shows the same MDRS landing as `?mineId=`; the iframe never sees the param. So URL-based deep linking is out.
- The MSTR iframe issues 51 network calls on load — all CSS/JS/HTML chrome, **zero** data-bearing XHRs on landing. Data appears only after in-app interaction.
- The Mine ID / Mine Name search inputs are `mstrmojo-SimpleObjectInputBox` widgets (NOT the `mstrmojo-DocTextfield` widgets we initially probed). Each is identifiable by the placeholder text inside its DOM subtree (`Search by Mine ID by typing here..` / `Search by Mine name by typing here..`).
- Five top-level tabs (Mines, Contractors, State / County, Controller, Operator) render as `<input type="submit">` with non-stable session IDs but a stable `mstrmojo-ButtonItem` class. Clicking "Mines" does nothing visible — it is already the default tab.
- Three of 13 `mstrmojo-DocTextfield`s on the per-mine landing carry class `hasLink` and `title="Click on the link to view the report"`. Those are the report drill-in points (Number of Hours Worked / Average Number of Employees / Coal Production — all employment reports, not enforcement).
- The Submit widget next to each search box is `mstrmojo-DocButton CaptionOnly hasLink` with text content "Submit". It needs **page-level mouse click at iframe-relative coords** to fire — `playwright.element.click()` sometimes misses the mojo handler. Two visible ones; the topmost (lower y) is the Mine ID submit, the second is Mine Name.
- The autocomplete popup on type is `.mstrmojo-Popup-content`, with each match as a `.item` child. "No elements match your search" populates the popup when MSTR's active-mine database has no hit.

## What's left

The production scraper drills to per-mine and captures the Mine Information page. To complete Tier 1 enforcement ingestion, the next session needs to:

1. Find the `Violations` and `Inspections` clickable links on the per-mine page (`mstrmojo-DocTextfield hasLink` widgets with `title="Click to open Mine Inspections dashboard"` and similar).
2. Click each link → MSTR loads a separate dashboard document for that report inside the same iframe.
3. Wait for the grid to render — should be `mstrmojo-Grid` or `mstrmojo-RWGridGraph` table elements.
4. Read header row + data rows; emit one CSV per mine per dashboard.
5. Aggregate per-mine CSVs into the canonical `mrt/violations_ss_by_mine.parquet` and `mrt/withdrawal_orders.parquet` (schemas in `MIGRATION.md` Phase 3.A).

## API shortcuts that are NOT available (all locked, do not retry)

We tested every reasonable URL-based shortcut before committing to DOM scraping. Recording the dead ends so a future run does not relitigate them.

- **MSTR Library REST API** (`/MicroStrategyLibrary/api/...`) — every endpoint returns `500 Internal server error.`. Library is installed on the server (the dashboard reports Library content) but the public surface blocks the API.
- **MSTR classic TaskProc API** (`/MicroStrategy/asp/TaskProc.aspx?taskId=...`) — connects (200) but every meaningful task (`login`, `getSessionState`, `getCurrentUserInfo`, `getServerStatus`, `createSession`, `browseFolder`, `getFolderContents`, `reportExecute`) returns 500 or empty body across `loginMode=1`, `loginMode=8` (guest), `loginMode=16`, GET and POST.
- **MSTR `evt=3140` (export to Excel)** — returns 449 KB of HTML that renders the modern Library dashboard, then JS-errors with `Cannot read properties of undefined (reading 'getSelectedPanel')`. No actual file download is triggered.
- **Other `evt=` codes tested**: `2048001` (open document, default — works but renders the full UI), `3046` (export, returns "Error" page), `3067` (export, returns "Error" page).
- **URL-based prompt answers** (`valuePromptAnswers`, `elementsPromptAnswers`, `promptAnswerMode`) — accepted by the URL but the mineId is not honored; the document opens at its empty default state regardless of param.

The conclusion is durable: the only public surface that returns mine-level data is the rendered HTML inside the iframe, after a real click sequence into a `mstrmojo-DocTextfield`.

## Alternative we should still pursue

Email `mshadata@dol.gov` for either (a) the codec spec for the broken bulk zips, or (b) a flat-CSV mirror of the same data. Either solves Tier 1 ingestion in a more durable way than scraping a 20-year-old MicroStrategy app. See `MIGRATION.md` Phase 3.A for the larger context.

## Running the probes

Each is self-contained. Run from the repo root:

```sh
uv run python -m scripts.probes.mdrs.01_capture_network
uv run python -m scripts.probes.mdrs.02_inspect_html_bodies
uv run python -m scripts.probes.mdrs.03_dump_iframe_dom
uv run python -m scripts.probes.mdrs.04_click_tabs
uv run python -m scripts.probes.mdrs.05_click_advanced_search
uv run python -m scripts.probes.mdrs.06_inspect_form_widgets
```

Outputs land under `/tmp/mdrs_probe*` and `/tmp/mdrs_ui` (HTML dumps, screenshots, request captures). Reset by deleting those temp directories before each run.

Requires `playwright` (already a dev dep) plus `playwright install chromium` once per environment.
