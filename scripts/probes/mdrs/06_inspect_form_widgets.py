"""Inspect the 'Explore MSHA Datasets' dropdown — its options are
the canonical bulk datasets and may link directly to CSV/Excel
downloads (bypassing the broken zip).
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("/tmp/mdrs_ui")
URL = "http://www.msha.gov/data-and-reports/mine-data-retrieval-system?mineId=1512805"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="unearthed-coal-data/1.0 (+https://github.com/anchildress1/unearthed)",
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(15_000)
        mstr = next((f for f in page.frames if "microstrategy" in f.url), None)

        # Find every <select>
        selects = await mstr.query_selector_all("select")
        print(f"Found {len(selects)} <select> elements")
        for s in selects:
            try:
                if not await s.is_visible():
                    continue
                attrs = await s.evaluate("e => ({id: e.id, name: e.name, cls: e.className})")
                opts = await s.evaluate(
                    "e => Array.from(e.options).map(o => ({value: o.value, text: o.textContent}))"
                )
                print(f"\nselect {attrs}")
                for o in opts[:60]:
                    print(f"  value={o['value']!r}  text={o['text']!r}")
            except Exception as e:
                print(f"  err: {e}")

        # Look for any Mine ID field — try contenteditable, role=textbox, span/div masquerading as input
        print("\n=== alternative input candidates ===")
        for sel in [
            "[contenteditable='true']",
            "[role='textbox']",
            "div[id*='Mine' i]",
            "span[id*='Mine' i]",
            "*[name*='mineId' i]",
            "*[name*='mine_id' i]",
            "div.mstrInput",
            "td.mstrInput",
            ".prompt input",
            ".mstrPrompt input",
        ]:
            elems = await mstr.query_selector_all(sel)
            visible = []
            for e in elems[:20]:
                try:
                    if await e.is_visible():
                        attrs = await e.evaluate(
                            "e => ({tag: e.tagName, id: e.id, cls: e.className, "
                            "html: e.outerHTML.substring(0, 200)})"
                        )
                        visible.append(attrs)
                except Exception:
                    pass
            if visible:
                print(f"\n{sel}: {len(visible)}")
                for v in visible[:5]:
                    print(f"  {v}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
