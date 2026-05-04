"""Round 2: longer wait, persist full HTML bodies, search for mine markers."""

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

OUT_DIR = Path("/tmp/mdrs_probe2")
OUT_DIR.mkdir(exist_ok=True)
TARGET_MINE_ID = "1512805"  # Leer Mine
URL = f"http://www.msha.gov/data-and-reports/mine-data-retrieval-system?mineId={TARGET_MINE_ID}"

DATA_HOSTS = ("microstrategy.msha.gov", "www.msha.gov")

async def main():
    summaries = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="unearthed-coal-data/1.0 (+https://github.com/anchildress1/unearthed)"
        )
        page = await context.new_page()

        async def on_response(resp):
            if not any(h in resp.url for h in DATA_HOSTS):
                return
            ct = resp.headers.get("content-type", "")
            try:
                body = await resp.body()
            except Exception:
                body = b""
            # Persist HTML responses we get back from MSTR
            if "html" in ct.lower() or "xml" in ct.lower() or "json" in ct.lower():
                fname = re.sub(r"[^a-zA-Z0-9]+", "_", resp.url)[-90:]
                (OUT_DIR / f"{resp.status}_{fname}.txt").write_bytes(
                    f"URL: {resp.url}\nStatus: {resp.status}\nContent-Type: {ct}\n\n".encode()
                    + body
                )
            summaries.append({
                "url": resp.url,
                "status": resp.status,
                "ct": ct,
                "len": len(body),
                "has_mine_id": TARGET_MINE_ID.encode() in body,
                "has_leer": b"leer" in body.lower(),
            })

        page.on("response", on_response)

        print(f"Loading {URL} (45s wait this time)")
        await page.goto(URL, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(45_000)
        # Print any frames found
        for frame in page.frames:
            try:
                fcontent = await frame.content()
                contains_mine = TARGET_MINE_ID in fcontent or "Leer" in fcontent
                print(f"Frame name={frame.name!r}: len={len(fcontent)} hasMineId={TARGET_MINE_ID in fcontent} hasLeer={'leer' in fcontent.lower()}")
                if contains_mine:
                    (OUT_DIR / f"frame_{frame.name or 'main'}.html").write_text(fcontent)
            except Exception as e:
                print(f"  frame error: {e}")
        await browser.close()

    summary_out = OUT_DIR / "summary.json"
    summary_out.write_text(json.dumps(summaries, indent=2))
    hits = [s for s in summaries if s["has_mine_id"] or s["has_leer"]]
    print(f"\n{len(summaries)} responses, {len(hits)} contain '{TARGET_MINE_ID}' or 'leer'")
    for h in hits[:10]:
        print(f"  {h['status']}  ct={h['ct']}  len={h['len']}  url={h['url'][:140]}")


if __name__ == "__main__":
    asyncio.run(main())
