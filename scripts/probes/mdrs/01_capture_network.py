"""Probe MSHA MDRS to capture every network request the MicroStrategy
iframe makes when drilling into a single mine. Goal: discover whether
the data is fetchable via plain HTTP (XHR replay) or whether we must
keep a real browser open for every scrape session."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

OUT_DIR = Path("/tmp/mdrs_probe")
OUT_DIR.mkdir(exist_ok=True)
TARGET_MINE_ID = "1512805"  # Leer Mine — known good test mine
URL = f"http://www.msha.gov/data-and-reports/mine-data-retrieval-system?mineId={TARGET_MINE_ID}"


async def main():
    requests = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="unearthed-coal-data/1.0 (+https://github.com/anchildress1/unearthed)"
        )
        page = await context.new_page()

        # Capture every network request and response so we can see what
        # MSTR fires after the iframe loads.
        async def on_request(req):
            requests.append({
                "phase": "request",
                "url": req.url,
                "method": req.method,
                "resource_type": req.resource_type,
                "headers": dict(req.headers),
                "post_data": req.post_data[:500] if req.post_data else None,
            })

        async def on_response(resp):
            try:
                body_preview = (await resp.body())[:1500]
            except Exception:
                body_preview = b""
            requests.append({
                "phase": "response",
                "url": resp.url,
                "status": resp.status,
                "content_type": resp.headers.get("content-type", ""),
                "body_preview_hex": body_preview[:200].hex(),
                "body_preview_text": body_preview[:600].decode("latin-1", errors="replace"),
            })

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"Loading {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        # Let the iframe and its XHRs settle
        await page.wait_for_timeout(15_000)

        # Try to also navigate INTO the iframe
        for frame in page.frames:
            print(f"Frame: name={frame.name!r} url={frame.url}")
        await browser.close()

    out = OUT_DIR / "requests.json"
    out.write_text(json.dumps(requests, indent=2))
    print(f"Captured {len(requests)} request/response events → {out}")

    # Quick summary: distinct domains + resource types
    domains = {}
    for r in requests:
        if r["phase"] != "response":
            continue
        host = r["url"].split("//")[1].split("/")[0]
        domains.setdefault(host, []).append((r["status"], r["url"][:120], r["content_type"]))
    print("\n=== domains seen ===")
    for host, entries in domains.items():
        print(f"  {host}: {len(entries)} responses")
        for status, url, ct in entries[:3]:
            print(f"    {status} {ct} — {url}")


if __name__ == "__main__":
    asyncio.run(main())
