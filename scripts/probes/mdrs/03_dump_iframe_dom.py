"""Map the MDRS UI surface so the scraper has known selectors before
we write any drill-down logic. Steps:

1. Load the outer page (with mineId hint).
2. Wait for the MSTR iframe to settle.
3. Take a screenshot of the rendered iframe.
4. Dump the iframe DOM tree (just structure: tag + id + class + text snippet).
5. Probe for likely search-input selectors and report-grid containers.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("/tmp/mdrs_ui")
OUT.mkdir(exist_ok=True)
TARGET = "1512805"  # Leer Mine
URL = f"http://www.msha.gov/data-and-reports/mine-data-retrieval-system?mineId={TARGET}"

# Likely search-input candidates — MSTR's mojo framework names these
# variously. Cast a wide net so the dump tells us what's actually there.
SEARCH_PROBES = [
    'input[type="text"]',
    'input[type="search"]',
    'input[placeholder*="Mine" i]',
    'input[placeholder*="ID" i]',
    'input[placeholder*="Search" i]',
    'input[name*="mine" i]',
    'input[id*="mine" i]',
    'input[id*="search" i]',
    'input[id*="prompt" i]',
    'input.mstrInput',
    "[role='searchbox']",
]

GRID_PROBES = [
    'table',
    '.mstrGrid',
    '.mstrRWDocument',
    '.mojo-Grid',
    '[class*="Grid"]',
    '[class*="grid"]',
    '[role="grid"]',
]


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="unearthed-coal-data/1.0 (+https://github.com/anchildress1/unearthed)",
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        print(f"Loading {URL}")
        await page.goto(URL, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(20_000)

        # Take a screenshot for human eyeball inspection
        await page.screenshot(path=str(OUT / "outer.png"), full_page=True)

        # Find the MSTR iframe explicitly
        mstr_frame = None
        for f in page.frames:
            if "microstrategy" in f.url:
                mstr_frame = f
                break

        if not mstr_frame:
            print("NO MSTR iframe found — bailing")
            return

        print(f"\nMSTR frame URL: {mstr_frame.url}")
        # Save full frame HTML
        html = await mstr_frame.content()
        (OUT / "mstr_frame.html").write_text(html)
        print(f"Saved full iframe HTML ({len(html)} bytes) → mstr_frame.html")

        # Probe for inputs
        print("\n=== input elements in MSTR iframe ===")
        for selector in SEARCH_PROBES:
            try:
                elements = await mstr_frame.query_selector_all(selector)
                if elements:
                    print(f"  {selector}: {len(elements)} matches")
                    for el in elements[:3]:
                        try:
                            tag = await el.evaluate("e => e.tagName")
                            attrs = await el.evaluate(
                                "e => ({id: e.id, name: e.name, "
                                "placeholder: e.placeholder, type: e.type, "
                                "cls: e.className})"
                            )
                            visible = await el.is_visible()
                            print(f"    {tag}  {attrs}  visible={visible}")
                        except Exception as e:
                            print(f"    err: {e}")
            except Exception as e:
                print(f"  {selector}: probe failed: {e}")

        # Probe for grids/tables
        print("\n=== grid/table candidates ===")
        for selector in GRID_PROBES:
            try:
                count = await mstr_frame.locator(selector).count()
                if count:
                    print(f"  {selector}: {count} matches")
            except Exception as e:
                print(f"  {selector}: probe failed: {e}")

        # Probe for any "Mine ID", "Search", "Submit" buttons
        print("\n=== button candidates ===")
        for sel in ["button", "input[type='button']", "input[type='submit']", "[role='button']"]:
            try:
                buttons = await mstr_frame.query_selector_all(sel)
                visible = []
                for b in buttons[:50]:
                    if await b.is_visible():
                        text = (await b.text_content() or "").strip()
                        attrs = await b.evaluate("e => ({id: e.id, name: e.name, value: e.value, cls: e.className})")
                        visible.append((text[:40], attrs))
                if visible:
                    print(f"  {sel}: {len(visible)} visible")
                    for t, a in visible[:8]:
                        print(f"    text={t!r}  {a}")
            except Exception as e:
                print(f"  {sel}: err: {e}")

        # Take a screenshot of just the iframe frame
        try:
            iframe_handle = await page.query_selector("iframe#iframe1")
            if iframe_handle:
                await iframe_handle.screenshot(path=str(OUT / "mstr_iframe.png"))
                print("\nSaved iframe screenshot → mstr_iframe.png")
        except Exception as e:
            print(f"iframe screenshot err: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
