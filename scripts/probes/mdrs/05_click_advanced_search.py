"""Step 3: click 'Advanced Search - Mines' link, then explore the
search form. Also try clicking a 'Submit' link to see what's inside the
default Mines panel.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("/tmp/mdrs_ui")
URL = "http://www.msha.gov/data-and-reports/mine-data-retrieval-system?mineId=1512805"


async def report_form_state(frame, label: str):
    """Dump every visible input/textarea/select after a click."""
    print(f"\n--- {label} ---")
    sels = ["input", "textarea", "select", "[contenteditable='true']"]
    for sel in sels:
        elems = await frame.query_selector_all(sel)
        for el in elems:
            try:
                if not await el.is_visible():
                    continue
                attrs = await el.evaluate(
                    "e => ({tag: e.tagName, id: e.id, name: e.name, "
                    "type: e.type, value: e.value, placeholder: e.placeholder, "
                    "cls: e.className})"
                )
                if attrs.get("type") in ("hidden",):
                    continue
                print(f"  {attrs}")
            except Exception:
                pass


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
        assert mstr, "no MSTR iframe"

        # Click "Advanced Search - Mines"
        link = await mstr.query_selector('a:has-text("Advanced Search - Mines")')
        if link:
            print("Clicking 'Advanced Search - Mines'…")
            await link.click()
            await page.wait_for_timeout(8_000)
            # iframe URL might have changed; refresh frame ref
            mstr2 = next((f for f in page.frames if "microstrategy" in f.url), None)
            print(f"After click, MSTR URL = {mstr2.url[:200]}")
            await page.screenshot(path=str(OUT / "after_advanced_search.png"), full_page=True)
            html = await mstr2.content()
            (OUT / "after_advanced_search.html").write_text(html)
            await report_form_state(mstr2, "Advanced Search - Mines page")

            # Look for any visible link / button text on this page
            anchors = await mstr2.query_selector_all("a")
            visible_anchor_texts = []
            for a in anchors[:80]:
                try:
                    if await a.is_visible():
                        text = (await a.text_content() or "").strip()
                        if text:
                            visible_anchor_texts.append(text[:60])
                except Exception:
                    pass
            print(f"\nVisible anchor texts after Advanced Search click ({len(visible_anchor_texts)}):")
            for t in visible_anchor_texts[:40]:
                print(f"  - {t}")
        else:
            print("'Advanced Search - Mines' link NOT found")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
