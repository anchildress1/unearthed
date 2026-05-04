"""Scrape MSHA MDRS enforcement data per mine via headless Chromium.

MSHA's bulk-zip endpoints are corrupt past ~1% of payload (see
``MIGRATION.md`` Phase 3.A). This module is the live alternative: drive
the MSHA Mine Data Retrieval System (MDRS) MicroStrategy dashboard to
fetch per-mine Violations, 107(a) Orders, Assessed Violations, and
Contested Violations.

The MSHA OGI portal is `https://arlweb.msha.gov/OpenGovernmentData/`
(broken zips). MDRS is at `https://www.msha.gov/data-and-reports/mine-data-retrieval-system`,
which embeds an iframe to `https://microstrategy.msha.gov/MicroStrategy/asp/Main.aspx?...`.
The mine drill-in flow inside that iframe is:

1. Click ``#mstr92`` (a ``mstrmojo-SimpleObjectInputBox``).
2. Type the 7-digit mine ID. An autocomplete popup appears as
   ``.mstrmojo-Popup-content``.
3. Click the matching ``.mstrmojo-Popup-content .item`` to lock the
   selection.
4. Click the visible "Submit" widget — a ``mstrmojo-DocButton CaptionOnly hasLink``
   with text content "Submit". Coordinate-based clicks are required;
   the widget's ID is timestamped per session so we cannot pin a
   stable selector and instead match by class + text.
5. The MSTR document re-renders with the per-mine reports
   (Violations / 107(a) Orders / Assessed / Contested / Inspections).

URL-based shortcuts (Library REST, classic TaskProc, ``evt=3140``
export, ``valuePromptAnswers``) are all locked or broken; see
``scripts/probes/mdrs/README.md`` for the full disqualification list.

Politeness: throttle defaults to 2 s between mines. MSHA publishes no
rate-limit guidance; this is the conservative ceiling for a federal
public-data site we already throttle the fatality scrape against.

Usage::

    uv run python -m scripts.mdrs_scrape_enforcement \\
        --mine-ids 4609192 0103354 1202215 \\
        --out data/msha/enforcement/

    # or feed mine IDs from a file (one per line)
    uv run python -m scripts.mdrs_scrape_enforcement \\
        --mine-ids-file data/msha/active_coal_mine_ids.txt \\
        --out data/msha/enforcement/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Import inside main() so test-time imports of this module do not require
# Playwright to be installed if a caller is only exercising the pure
# helpers below.
try:
    from playwright.async_api import Frame, Page, async_playwright
except ImportError:
    Frame = Page = None  # type: ignore[assignment,misc]
    async_playwright = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MDRS_URL = "https://www.msha.gov/data-and-reports/mine-data-retrieval-system"
# MSHA's MicroStrategy serves a degraded "mstr-unsupported-browser"
# layout (the SimpleObjectInputBox widgets do not render) when the UA
# does not look like a real desktop Chrome. We pin a current Chrome
# UA and accept the slight ick of UA-spoofing because the alternative
# is a non-functional scrape. The polite identifier moves to a custom
# header instead so MSHA's logs still see who we are.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)
POLITE_HEADER = ("X-Unearthed-Source", "https://github.com/anchildress1/unearthed")
DEFAULT_THROTTLE_SECONDS = 2.0
LOAD_TIMEOUT_MS = 90_000
LOAD_SETTLE_MS = 20_000
WIDGET_RENDER_MS = 2_500
POST_SUBMIT_MS = 8_000

# Selectors. Numeric ``mstr<N>`` IDs change between sessions, so we
# fingerprint by widget class + the placeholder/label text MSHA
# attaches to each search box. See scripts/probes/mdrs/README.md.
MINE_ID_BOX_CLASS = ".mstrmojo-SimpleObjectInputBox"
SUBMIT_BUTTON_FINGERPRINT = ("Submit", "mstrmojo-DocButton")
MINE_ID_PATTERN = re.compile(r"^\d{7}$")

VIOLATION_RE = re.compile(r"\bViolation(?:s)?\b")
# `\b` boundaries don't work after `)` (both sides are non-word chars),
# so anchor the right edge with a positive look-ahead onto the natural
# follow-on chars MSHA's HTML uses (whitespace, tag close, end of string).
ORDER_107_RE = re.compile(r"\b107\(a\)(?=\s|<|$)")
ASSESSED_RE = re.compile(r"\bAssessed\b")
CONTESTED_RE = re.compile(r"\bContested\b")


class MdrsError(RuntimeError):
    """Raised when the MDRS interaction breaks in a way the caller cares about."""


class MineNotFound(MdrsError):
    """The mine ID did not match any record in MSHA's active database."""


@dataclass
class MineEnforcement:
    """Per-mine output of one drill-in. Counts plus the raw HTML so the
    parquet builder can re-extract structured rows offline.
    """

    mine_id: str
    drilled_in: bool
    violation_marker_count: int = 0
    order_107a_marker_count: int = 0
    assessed_marker_count: int = 0
    contested_marker_count: int = 0
    iframe_html: str = ""
    notes: list[str] = field(default_factory=list)


def validate_mine_id(mine_id: str) -> str:
    """Return ``mine_id`` after normalizing.

    MSHA Mine IDs are 7 digits. The hyphenated form ``NN-NNNNN`` is the
    human-friendly rendering; we strip the hyphen and reject anything
    that doesn't reduce to 7 digits.
    """
    candidate = mine_id.strip().replace("-", "")
    if not MINE_ID_PATTERN.match(candidate):
        raise ValueError(f"Mine ID must be 7 digits; got {mine_id!r}")
    return candidate


def count_markers(iframe_html: str) -> dict[str, int]:
    """Count enforcement-tab markers in the rendered iframe HTML.

    Pure helper so unit tests don't need a live browser. The drill-in
    page surfaces section headers like "Violations", "107(a) Orders",
    "Assessed Violations", "Contested Violations" multiple times. The
    counts are a coarse signal that the drill-in landed; richer
    extraction lives in the parquet builder once the per-tab DOM
    structure is reverse-engineered (TODO).
    """
    return {
        "violation": len(VIOLATION_RE.findall(iframe_html)),
        "order_107a": len(ORDER_107_RE.findall(iframe_html)),
        "assessed": len(ASSESSED_RE.findall(iframe_html)),
        "contested": len(CONTESTED_RE.findall(iframe_html)),
    }


async def _find_mine_id_widget(frame: Frame):
    """Locate the Mine ID ``SimpleObjectInputBox``.

    The two search boxes on the page (Mine ID, Mine Name) share class
    but each carries its placeholder text directly inside its DOM
    subtree (e.g. "Search by Mine ID by typing here.."). We pick the
    one that contains "Mine ID" but not "Mine name" (case-insensitive
    on "name" so "Mine Name" / "mine name" both reject).
    """
    boxes = await frame.query_selector_all(MINE_ID_BOX_CLASS)
    for box in boxes:
        try:
            if not await box.is_visible():
                continue
        except Exception:
            continue
        text = await box.text_content() or ""
        if "Mine ID" in text and "mine name" not in text.lower():
            return box
    raise MdrsError(
        "Mine ID search widget not found — MDRS layout changed; "
        "re-run scripts/probes/mdrs/06_inspect_form_widgets.py to map it"
    )


async def _wait_for_iframe(page: Page, debug_dir: Path | None = None) -> Frame:
    """Wait for the MicroStrategy iframe to appear, then for the
    SimpleObjectInputBox widgets inside it to render.

    MSTR's mojo framework loads in async stages: the iframe HTML
    arrives quickly but the form widgets are rebuilt by JS several
    seconds later. ``wait_for_selector`` polls until the widget is
    actually present rather than guessing a fixed sleep.

    On failure, dumps a screenshot + iframe HTML to ``debug_dir`` so
    a remote operator can see whether MSHA is in its Friday-evening
    maintenance window or has shipped a layout change.
    """
    await page.goto(MDRS_URL, wait_until="networkidle", timeout=LOAD_TIMEOUT_MS)
    frame = None
    for _attempt in range(12):
        await page.wait_for_timeout(2_500)
        frame = next(
            (f for f in page.frames if "microstrategy" in f.url and "pendo" not in f.url),
            None,
        )
        if frame is None:
            continue
        try:
            await frame.wait_for_selector(MINE_ID_BOX_CLASS, state="visible", timeout=2_500)
            return frame
        except Exception:
            continue
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(debug_dir / "no_widgets.png"), full_page=True)
        if frame is not None:
            (debug_dir / "iframe_no_widgets.html").write_text(
                await frame.content(), encoding="utf-8"
            )
    raise MdrsError(
        "MicroStrategy iframe did not surface SimpleObjectInputBox widgets — "
        "check network / MSHA maintenance window or re-discover selectors"
    )


async def _click_submit(page: Page, frame: Frame) -> None:
    """Click the visible "Submit" mstrmojo-DocButton next to the Mine ID input.

    The widget has no stable id and no role=button. We fingerprint by
    class + text content + bbox.width via JS, then page-level click
    using iframe-relative coords (Playwright's element.click sometimes
    misses the mojo widget's own click handler).
    """
    submits = await frame.evaluate(
        """
        () => {
            const out = [];
            document.querySelectorAll('*').forEach(el => {
                if ((el.textContent || '').trim() !== 'Submit') return;
                if (!el.className || !el.className.includes('mstrmojo-DocButton')) return;
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;
                out.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            });
            return out;
        }
        """
    )
    if not submits:
        raise MdrsError("Submit button not found — MDRS layout may have changed")
    # Prefer the topmost candidate (Mine ID Submit — Mine Name Submit is below it).
    submits.sort(key=lambda b: b["y"])
    target = submits[0]
    iframe_handle = await page.query_selector("iframe#iframe1")
    bbox = await iframe_handle.bounding_box()
    cx = bbox["x"] + target["x"] + target["w"] // 2
    cy = bbox["y"] + target["y"] + target["h"] // 2
    await page.mouse.click(cx, cy)


async def drill_mine(page: Page, mine_id: str, debug_dir: Path | None = None) -> MineEnforcement:
    """Run the four-step drill-in for a single mine ID.

    Side-effects: navigates the page, types into the search widget,
    clicks the autocomplete entry, clicks Submit. The iframe HTML at
    the end of this dance is captured into the returned record.
    """
    mine_id = validate_mine_id(mine_id)
    record = MineEnforcement(mine_id=mine_id, drilled_in=False)
    frame = await _wait_for_iframe(page, debug_dir=debug_dir)

    target = await _find_mine_id_widget(frame)

    await target.click()
    await page.wait_for_timeout(500)
    await page.keyboard.type(mine_id, delay=80)
    await page.wait_for_timeout(WIDGET_RENDER_MS)

    # Pick the autocomplete match, or surface MineNotFound.
    popup_text = await frame.evaluate(
        "() => { const p = document.querySelector('.mstrmojo-Popup-content'); "
        "return p ? p.textContent.trim() : ''; }"
    )
    if "No elements match" in popup_text:
        record.notes.append("autocomplete returned 'No elements match'")
        raise MineNotFound(f"Mine ID {mine_id} did not match an MDRS record")

    item = None
    for handle in await frame.query_selector_all(".mstrmojo-Popup-content .item"):
        try:
            text = (await handle.text_content() or "").strip()
        except Exception:
            continue
        if text == mine_id and await handle.is_visible():
            item = handle
            break
    if not item:
        raise MdrsError(f"Autocomplete popup did not surface a clickable match for {mine_id}")
    await item.click()
    await page.wait_for_timeout(1_500)

    await _click_submit(page, frame)
    await page.wait_for_timeout(POST_SUBMIT_MS)

    # Re-grab the iframe (URL may have rewritten) and capture state.
    frame2 = next(
        (f for f in page.frames if "microstrategy" in f.url and "pendo" not in f.url),
        None,
    )
    if not frame2:
        raise MdrsError("MicroStrategy iframe disappeared after submit")
    record.iframe_html = await frame2.content()
    counts = count_markers(record.iframe_html)
    record.violation_marker_count = counts["violation"]
    record.order_107a_marker_count = counts["order_107a"]
    record.assessed_marker_count = counts["assessed"]
    record.contested_marker_count = counts["contested"]
    # Drill-in is "successful" when the post-submit page has more
    # enforcement markers than the pre-submit page (which baselines at
    # 2 occurrences of "Violation" from the static dataset metadata).
    record.drilled_in = counts["violation"] > 2 or counts["order_107a"] > 2
    return record


async def scrape_mines(
    mine_ids: list[str], out_dir: Path, throttle_seconds: float = DEFAULT_THROTTLE_SECONDS
) -> int:
    """Iterate ``mine_ids`` sequentially, drilling each mine once.

    Per-mine HTML lands at ``out_dir/<mine_id>.html``; per-mine summary
    JSON at ``out_dir/<mine_id>.json``. Failures (MineNotFound,
    MdrsError) are logged and skipped — the run continues so a single
    bad mine does not poison the whole batch.
    """
    if async_playwright is None:
        raise SystemExit(
            "Playwright is not installed. Run `uv sync` then "
            "`uv run playwright install chromium` once per environment."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    succeeded = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1440, "height": 1100},
                extra_http_headers={POLITE_HEADER[0]: POLITE_HEADER[1]},
            )
            page = await ctx.new_page()
            for mine_id in mine_ids:
                try:
                    record = await drill_mine(page, mine_id, debug_dir=out_dir / "_debug")
                except MineNotFound:
                    logger.warning("mine_id=%s not found in MDRS", mine_id)
                    continue
                except MdrsError as exc:
                    logger.warning("mine_id=%s scrape failed: %s", mine_id, exc)
                    continue

                html_path = out_dir / f"{record.mine_id}.html"
                summary_path = out_dir / f"{record.mine_id}.json"
                html_path.write_text(record.iframe_html, encoding="utf-8")
                summary_path.write_text(
                    json.dumps(
                        {
                            "mine_id": record.mine_id,
                            "drilled_in": record.drilled_in,
                            "violation_marker_count": record.violation_marker_count,
                            "order_107a_marker_count": record.order_107a_marker_count,
                            "assessed_marker_count": record.assessed_marker_count,
                            "contested_marker_count": record.contested_marker_count,
                            "notes": record.notes,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                logger.info(
                    "mine_id=%s drilled_in=%s viol=%d 107a=%d",
                    record.mine_id,
                    record.drilled_in,
                    record.violation_marker_count,
                    record.order_107a_marker_count,
                )
                succeeded += 1
                if throttle_seconds > 0:
                    await page.wait_for_timeout(int(throttle_seconds * 1000))
        finally:
            await browser.close()
    return succeeded


def _parse_mine_ids(args: argparse.Namespace) -> list[str]:
    """Resolve mine IDs from ``--mine-ids`` and/or ``--mine-ids-file``."""
    ids: list[str] = []
    if args.mine_ids:
        ids.extend(args.mine_ids)
    if args.mine_ids_file:
        for line in args.mine_ids_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                ids.append(line)
    if not ids:
        raise SystemExit("No mine IDs supplied (use --mine-ids or --mine-ids-file)")
    # Deduplicate while preserving input order.
    seen: set[str] = set()
    unique: list[str] = []
    for raw in ids:
        try:
            normalized = validate_mine_id(raw)
        except ValueError as exc:
            logger.warning("Skipping invalid mine ID %r: %s", raw, exc)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mine-ids", nargs="*", default=[], help="Mine IDs to scrape (7 digits each)"
    )
    parser.add_argument(
        "--mine-ids-file",
        type=Path,
        default=None,
        help="File with one mine ID per line; '#' starts a comment",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/msha/enforcement"),
        help="Output directory (default: data/msha/enforcement/)",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=DEFAULT_THROTTLE_SECONDS,
        help=f"Seconds between mines (default: {DEFAULT_THROTTLE_SECONDS})",
    )
    args = parser.parse_args(argv)
    mine_ids = _parse_mine_ids(args)
    logger.info("Scraping %d mines into %s", len(mine_ids), args.out)
    succeeded = asyncio.run(scrape_mines(mine_ids, args.out, args.throttle))
    logger.info("Done: %d/%d mines scraped", succeeded, len(mine_ids))
    return 0 if succeeded > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
