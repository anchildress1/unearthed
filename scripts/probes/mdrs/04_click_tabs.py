"""Step 2: click each top-level tab in turn and capture what UI surfaces.
Looking for the Mine ID search input that should appear under "Mines".
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("/tmp/mdrs_ui")
OUT.mkdir(exist_ok=True)
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

        mstr_frame = next((f for f in page.frames if "microstrategy" in f.url), None)
        if not mstr_frame:
            print("no MSTR iframe — bailing")
            return

        # Find the 5 top tabs
        tab_handles = await mstr_frame.query_selector_all('input[type="submit"]')
        tab_info = []
        for h in tab_handles:
            try:
                if not await h.is_visible():
                    continue
                attrs = await h.evaluate(
                    "e => ({id: e.id, name: e.name, value: e.value, cls: e.className})"
                )
                tab_info.append((h, attrs))
            except Exception:
                pass
        print(f"Found {len(tab_info)} visible submit buttons")
        for _, a in tab_info:
            print(f"  {a}")

        # The "Mines" tab is already selected; try clicking it explicitly
        # to see if the deep-linked mineId triggers anything.
        mines_tab = next(
            (h for h, a in tab_info if a.get("value") == "Mines"), None
        )
        if mines_tab:
            print("\nClicking 'Mines' tab")
            await mines_tab.click()
            await page.wait_for_timeout(8_000)
            # Re-scrape iframe after the click
            html_after = await mstr_frame.content()
            (OUT / "mstr_after_mines.html").write_text(html_after)
            await page.screenshot(path=str(OUT / "after_mines.png"), full_page=True)
            print(f"Saved iframe HTML after Mines click ({len(html_after)} bytes)")

            # Look for inputs again
            visible_inputs = []
            inputs = await mstr_frame.query_selector_all("input")
            for el in inputs:
                try:
                    if not await el.is_visible():
                        continue
                    attrs = await el.evaluate(
                        "e => ({id: e.id, name: e.name, type: e.type, "
                        "placeholder: e.placeholder, value: e.value, cls: e.className})"
                    )
                    if attrs.get("type") not in ("hidden",):
                        visible_inputs.append(attrs)
                except Exception:
                    pass
            print(f"\nVisible inputs after Mines click: {len(visible_inputs)}")
            for a in visible_inputs[:20]:
                print(f"  {a}")

            # Sub-tabs / new buttons that appeared
            new_buttons = []
            for sel in ["button", "input[type='submit']", "input[type='button']"]:
                els = await mstr_frame.query_selector_all(sel)
                for b in els:
                    if not await b.is_visible():
                        continue
                    text = (await b.text_content() or "").strip()[:60]
                    val = await b.evaluate("e => e.value || ''")
                    cls = await b.evaluate("e => e.className")
                    new_buttons.append((sel, text, val, cls))
            print(f"\nVisible buttons after Mines click: {len(new_buttons)}")
            for sel, t, v, c in new_buttons[:20]:
                print(f"  {sel} text={t!r} value={v!r} cls={c[:40]!r}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
