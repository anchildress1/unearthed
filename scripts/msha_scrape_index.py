"""Scrape the MSHA fatality search index for coal incidents.

Walks the Drupal-backed search at
``/data-and-reports/fatality-reports/search`` filtered to coal
(``field_mine_category_target_id=191``), one year at a time, paginating
``page=0,1,2,...`` until a page returns zero ``.views-row`` elements. Each
row carries enough metadata to build the manifest entry without ever
hitting the per-incident interstitial — that's the next pipeline step's
job.

The scraper is deliberately split from the parser:

* :func:`parse_search_page` is a pure function over HTML bytes, so unit
  tests cover schema drift on the MSHA side without making network calls.
* :func:`iter_year_pages` owns pagination and dedupe.
* :func:`fetch_search_page` is the only function that touches the
  network; tests inject a fake ``fetcher`` callable.

Output is CSV (``data/msha/manifest.csv`` by default). CSV beats Parquet
for an intermediate manifest: it is human-eyeballable, version-control
friendly, and the downstream parquet-builder reads it once and writes the
columnar artifact in one step.

Refresh discipline: this script is idempotent at the row level. Re-runs
overwrite the manifest with whatever the live site currently shows.
Fatalities are append-only at MSHA — incidents do not get retracted —
but report links (preliminary → final) flip over time, which is exactly
the signal the next stage needs to detect.

Usage::

    uv run python -m scripts.msha_scrape_index                    # 2007-current
    uv run python -m scripts.msha_scrape_index --year 2025
    uv run python -m scripts.msha_scrape_index --years 2010-2015
    uv run python -m scripts.msha_scrape_index --out data/msha/manifest.csv \\
        --throttle 1.5
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import re
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx
from lxml import html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Earliest year covered by the modern search interface; older incidents live
# at arlweb.msha.gov/fatals/indices/ and would need a separate parser. The
# Phase 3.A scope intentionally bounds itself to the modern era.
EARLIEST_MODERN_YEAR = 2007

# Drupal taxonomy IDs discovered by inspecting the search form's radio inputs.
# These are stable across the site's lifetime — they're entity IDs, not slugs.
COAL_CATEGORY_ID = "191"

SEARCH_URL = "https://www.msha.gov/data-and-reports/fatality-reports/search"

# Polite identifier so MSHA's logs see who is fetching. The contact URL points
# back to the project repo; if MSHA needs to reach out, it has somewhere to land.
USER_AGENT = "unearthed-coal-data/1.0 (+https://github.com/anchildress1/unearthed)"

# Default delay between requests. MSHA publishes no rate limit; one request per
# second is the conservative ceiling for scraping a federal site.
DEFAULT_THROTTLE_SECONDS = 1.0

# Hard ceiling on pages per year. The form caps page size around 30; the worst
# year on record (~70 fatalities) needs 3 pages. This guard prevents an infinite
# loop if MSHA ever stops returning empty pages and starts looping the result set.
MAX_PAGES_PER_YEAR = 50

# Full-name → 2-letter abbreviation, longest-first matters because "West Virginia"
# would otherwise greedily match "Virginia" inside "West Virginia".
_STATE_NAMES: dict[str, str] = {
    "Alabama": "AL",
    "Alaska": "AK",
    "American Samoa": "AS",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Guam": "GU",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Northern Mariana Islands": "MP",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Puerto Rico": "PR",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virgin Islands": "VI",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}
_STATE_PATTERN = re.compile(r"\b(" + "|".join(sorted(_STATE_NAMES, key=len, reverse=True)) + r")\b")


@dataclass(frozen=True)
class FatalityRow:
    """One scraped incident from the search index.

    Field choices: everything the search page exposes plus three boolean
    flags signalling which downstream PDFs exist. Booleans live alongside
    the URL so manifest consumers can filter without re-parsing.
    """

    incident_date: str  # ISO YYYY-MM-DD
    fatality_url: str  # absolute URL to the interstitial parent page
    mine_name: str
    location_raw: str
    mine_state: str  # 2-letter abbreviation, empty if unparseable
    accident_classification: str
    mine_controller: str
    mine_type: str
    primary_sic: str
    has_preliminary_report: bool
    has_fatality_alert: bool
    has_final_report: bool
    final_report_interstitial_url: str  # absolute URL or empty

    @property
    def is_coal(self) -> bool:
        """True when MSHA classifies the SIC under a coal heading."""
        return "coal" in self.primary_sic.lower()


def _absolute(url: str) -> str:
    """Promote a relative href to an absolute msha.gov URL."""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.msha.gov{url}"
    return f"https://www.msha.gov/{url}"


def _strip_label(text: str) -> str:
    """Drop the leading ``Label:`` chrome and collapse whitespace."""
    if ":" in text:
        text = text.split(":", 1)[1]
    return " ".join(text.split())


def _extract_state(location: str) -> str:
    """Pull the 2-letter state abbreviation out of a free-form location.

    Location format observed: ``<Mine Name> - <City>, <State>`` and a
    comma-less variant (``Dallas West Virginia``). Mine names sometimes
    contain other state names (``Ohio County Mine - Dallas West Virginia``),
    so we take the *rightmost* match — the state always trails the
    location text. Longest-first alternation handles ``West Virginia``
    vs. ``Virginia``. Returns empty string if no state name is present.
    """
    matches = list(_STATE_PATTERN.finditer(location))
    if not matches:
        return ""
    return _STATE_NAMES[matches[-1].group(1)]


def _parse_iso_date(span_datetime: str | None, fallback_url: str) -> str:
    """Resolve the incident date.

    Prefers the ISO ``datetime=...`` attribute embedded in the report-link
    button (always present when at least one report exists). Falls back to
    parsing the URL slug (``/2024/september-28-2024-fatality``) when the
    incident has no published reports yet — a brand-new fatality on the
    search page may have neither preliminary nor alert link.
    """
    if span_datetime:
        try:
            return (
                dt.datetime.fromisoformat(span_datetime.replace("Z", "+00:00")).date().isoformat()
            )
        except ValueError:
            logger.warning("Unparseable datetime %r — falling back to URL slug", span_datetime)

    # Slug pattern: /<...>/YYYY/<month>-<day>-<YYYY>-fatality(-N)?
    slug_match = re.search(r"/(\d{4})/([a-z]+)-(\d{1,2})-(\d{4})-fatality", fallback_url)
    if not slug_match:
        return ""
    year_dir, month_name, day, year_in_slug = slug_match.groups()
    try:
        return (
            dt.datetime.strptime(f"{month_name} {day} {year_in_slug}", "%B %d %Y")
            .date()
            .isoformat()
        )
    except ValueError:
        logger.warning("Unparseable URL slug %r", fallback_url)
        return ""


def parse_search_page(content: bytes) -> list[FatalityRow]:
    """Parse one search results page into structured fatality rows.

    Pure function: takes HTML bytes, returns dataclass instances. Network
    calls happen elsewhere. The MSHA page is server-rendered Drupal — the
    structure is stable per release and we key off the ``views-field-*``
    classes Drupal generates, not the visual layout.
    """
    tree = html.fromstring(content)
    rows: list[FatalityRow] = []

    for row_node in tree.cssselect(".views-row"):
        title_link = row_node.cssselect(".views-field-title a")
        if not title_link:
            # A views-row without a title is broken HTML; skip it rather than
            # blow up the entire scrape on one malformed result.
            continue
        a = title_link[0]
        fatality_url = _absolute(a.get("href") or "")
        title_text = (a.text or "").strip()

        def field(class_suffix: str) -> str:
            nodes = row_node.cssselect(f".views-field-field-{class_suffix}")
            return _strip_label(nodes[0].text_content()) if nodes else ""

        accident_classification = field("accident-classification")
        location_raw = field("location-at-fatality")
        mine_controller = field("mine-controller")
        mine_type = field("mine-type")
        primary_sic = field("primary-sic")

        # Mine name is the segment before the first "-" in the location string.
        mine_name = location_raw.split(" - ", 1)[0].strip() if " - " in location_raw else ""

        # Report buttons: at most one of each kind. The href ends with the
        # report type slug, which makes the boolean flags trivial.
        def link_for(kind: str) -> str:
            anchors = row_node.cssselect(f'a[href$="/{kind}"]')
            return _absolute(anchors[0].get("href")) if anchors else ""

        prelim = link_for("preliminary-report")
        alert = link_for("fatality-alert")
        final = link_for("final-report")

        # The earliest report-bearing button always carries the canonical
        # ISO datetime. Prefer preliminary (always first chronologically),
        # then alert, then final.
        datetime_attr = ""
        for anchor_kind in ("preliminary-report", "fatality-alert", "final-report"):
            spans = row_node.cssselect(f'a[href$="/{anchor_kind}"] span[datetime]')
            if spans:
                datetime_attr = spans[0].get("datetime") or ""
                break

        incident_date = _parse_iso_date(datetime_attr, fatality_url)
        if not incident_date:
            # The title still embeds the human date ("April 30, 2026 Fatality").
            # Last resort before giving up.
            try:
                incident_date = (
                    dt.datetime.strptime(title_text.replace(" Fatality", "").strip(), "%B %d, %Y")
                    .date()
                    .isoformat()
                )
            except ValueError:
                logger.warning(
                    "Could not resolve incident date for %s; leaving blank", fatality_url
                )

        rows.append(
            FatalityRow(
                incident_date=incident_date,
                fatality_url=fatality_url,
                mine_name=mine_name,
                location_raw=location_raw,
                mine_state=_extract_state(location_raw),
                accident_classification=accident_classification,
                mine_controller=mine_controller,
                mine_type=mine_type,
                primary_sic=primary_sic,
                has_preliminary_report=bool(prelim),
                has_fatality_alert=bool(alert),
                has_final_report=bool(final),
                final_report_interstitial_url=final,
            )
        )
    return rows


def fetch_search_page(year: int, page: int, *, throttle: float = DEFAULT_THROTTLE_SECONDS) -> bytes:
    """Fetch one page of search results. Honors the throttle delay."""
    params = {
        "field_mine_category_target_id": COAL_CATEGORY_ID,
        "year": str(year),
        "page": str(page),
    }
    url = f"{SEARCH_URL}?{urlencode(params)}"
    logger.info("GET %s", url)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    if throttle > 0:
        time.sleep(throttle)
    return response.content


def iter_year_pages(
    year: int,
    *,
    fetcher: Callable[[int, int], bytes] | None = None,
    max_pages: int = MAX_PAGES_PER_YEAR,
) -> Iterator[FatalityRow]:
    """Yield every fatality row for ``year``, paginating until empty.

    ``fetcher`` defaults to the live :func:`fetch_search_page`; tests
    inject a callable that returns canned bytes.
    """
    fetcher = fetcher or (lambda y, p: fetch_search_page(y, p))
    seen: set[str] = set()
    for page in range(max_pages):
        rows = parse_search_page(fetcher(year, page))
        if not rows:
            return
        new_count = 0
        for row in rows:
            if row.fatality_url in seen:
                continue
            seen.add(row.fatality_url)
            new_count += 1
            yield row
        # MSHA pagination occasionally repeats the last page; bail if a page
        # contributes zero new rows so we do not loop forever on a stuck cursor.
        if new_count == 0:
            logger.info("Year %d page %d yielded only duplicates — stopping", year, page)
            return
    logger.warning("Year %d hit MAX_PAGES_PER_YEAR=%d; truncating", year, max_pages)


def write_manifest(rows: list[FatalityRow], out_path: Path) -> None:
    """Atomically write the manifest CSV.

    Writes to a sibling ``.tmp`` file then renames so a crashed scrape
    cannot leave a half-written manifest that downstream scripts would
    mistakenly consume.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    fieldnames = list(FatalityRow.__dataclass_fields__.keys())
    with tmp_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    tmp_path.replace(out_path)
    logger.info("Wrote %d rows to %s", len(rows), out_path)


def _parse_year_arg(value: str) -> list[int]:
    """Accept ``2024`` or ``2010-2015`` and return the inclusive year list."""
    if "-" in value:
        start_str, end_str = value.split("-", 1)
        start, end = int(start_str), int(end_str)
        if start > end:
            raise argparse.ArgumentTypeError(f"Year range start > end: {value}")
        return list(range(start, end + 1))
    return [int(value)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--year", type=int, help="Single year (e.g. 2025).")
    group.add_argument(
        "--years",
        type=_parse_year_arg,
        help="Inclusive year range (e.g. 2010-2015).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/msha/manifest.csv"),
        help="Manifest CSV output path (default: data/msha/manifest.csv).",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=DEFAULT_THROTTLE_SECONDS,
        help=f"Seconds between requests (default: {DEFAULT_THROTTLE_SECONDS}).",
    )
    args = parser.parse_args(argv)

    if args.year:
        years = [args.year]
    elif args.years:
        years = args.years
    else:
        years = list(range(EARLIEST_MODERN_YEAR, dt.date.today().year + 1))

    fetcher = lambda y, p: fetch_search_page(y, p, throttle=args.throttle)  # noqa: E731

    all_rows: list[FatalityRow] = []
    for year in years:
        logger.info("Scraping year %d", year)
        year_rows = list(iter_year_pages(year, fetcher=fetcher))
        logger.info("  → %d incidents", len(year_rows))
        all_rows.extend(year_rows)

    write_manifest(all_rows, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
