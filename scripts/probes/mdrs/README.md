# MDRS reverse-engineering probes

These scripts are not part of the production pipeline. They map MSHA's
MDRS (Mine Data Retrieval System) MicroStrategy dashboard so a future
scraper has a foothold instead of starting from zero. Run order matches
the filename prefix.

## What we know

MDRS lives at `http://www.msha.gov/data-and-reports/mine-data-retrieval-system?mineId=<N>`. The outer page is a thin Drupal shell around an `iframe#iframe1` pointing at `https://microstrategy.msha.gov/MicroStrategy/asp/Main.aspx?...documentID=B546031C492F99BEAB6BCCB91635B608&...`. The `documentID` is the MDRS dashboard's MSTR Document ID; it is stable across sessions.

Three frames load on the page:

1. The outer Drupal page (carries the `mineId` URL param)
2. The MSTR document iframe (the actual app)
3. A `pendoFrame` analytics widget (ignore)

## What works and what doesn't

- The deep-link `?mineId=N` is **not** auto-passed into the iframe. Visiting `?mineId=1512805` shows the same MDRS landing as `?mineId=`; the iframe never sees the param. So URL-based deep linking is out.
- The MSTR iframe issues 51 network calls on load — all CSS/JS/HTML chrome, **zero** data-bearing XHRs. There is no plain-HTTP API surface to replay; the data appears only after in-app interaction.
- The visible "Mine ID" / "Mine Name" inputs on screen are **not** standard `<input>` elements. They are MSTR `mstrmojo-DocTextfield` divs (custom widgets). Standard Playwright input selectors miss them; `query_selector_all('.mstrmojo-DocTextfield')` finds 13.
- Five top-level tabs (Mines, Contractors, State / County, Controller, Operator) render as `<input type="submit">` with stable IDs (`vK2846`, `vK47`, `vW3919`, `vK3089`, `vK3096`). Clicking "Mines" does nothing visible — it is already the default tab.
- Three of the 13 textfields carry class `hasLink` and `title="Click on the link to view the report"`. Those are the report drill-in points.
- "Advanced Search - Mines" anchor click does not navigate (clicked, no DOM mutation observed within 8 s). May need a right-button click or a real mouse event simulation.

## The Path forward

MDRS data flows like this in the human UI:

1. User lands on MDRS with the dashboard already open
2. User types Mine ID into a `mstrmojo-DocTextfield` widget at iframe-local `(131, 216)`
3. User clicks "Submit"
4. MSTR fires an internal "execute prompt" event that loads the per-mine report
5. The mine-detail view exposes per-dataset drill-in links (Violations, 107(a) Orders, Assessed, Contested, Inspections)

The scraper needs to simulate that interaction sequence. Sticking points:

- `mstrmojo-DocTextfield` is not focusable as a plain element. It uses an internal `valueNode` div with custom click/focus handlers that mutate state via mojo's event bus. Standard `playwright.click()` lands on the wrapper but does not enter edit mode; need to click the `.mstrmojo-DocTextfield-valueNode` inner div, or use the page-level `keyboard.press('Tab')` flow to focus it the way a real user would.
- The "Submit" button (anchor in the captured HTML) needs investigation — it may be an `<a onclick="...">` whose handler only fires on a real mouse event, not a synthetic click.
- After Submit, we need to wait on `mstrApp.isReady()` (or equivalent) and re-frame the iframe before reading the new DOM.

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
