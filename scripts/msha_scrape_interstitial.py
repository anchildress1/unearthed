"""Parse MSHA Final Report interstitial pages into structured records.

Late discovery: every Final Report has a parallel HTML rendering at
``/data-reports/fatality-reports/<year>/<slug>/final-report``. The page
exposes a ``.field--name-body`` block whose content mirrors the PDF
exactly — same h2 section headings, same paragraphs. That collapses
two pipeline steps (download PDF, extract text from PDF) into one HTML
fetch, and removes the AGPL-licensed PyMuPDF concern entirely.

The interstitial body always carries these h2 sections:

    OVERVIEW
    GENERAL INFORMATION
    DESCRIPTION OF THE ACCIDENT
    INVESTIGATION OF THE ACCIDENT
    DISCUSSION
    ROOT CAUSE ANALYSIS
    CONCLUSION
    ENFORCEMENT ACTIONS
    APPENDIX <letter> – Persons Participating in the Investigation

PII discipline: the spec calls for no personal names in the surfaced
data. The middle four sections (DESCRIPTION, INVESTIGATION, DISCUSSION,
APPENDIX) attribute every action to a named individual — those are
dropped wholesale. The kept sections (OVERVIEW, ROOT CAUSE ANALYSIS,
CONCLUSION, ENFORCEMENT ACTIONS) reference roles ("the mine operator",
"the foreman") and only intermittently surface the victim's name —
that one name is redacted by extracting it from the OVERVIEW first
sentence and word-boundary replacing it across all kept sections.

Pure-function design: :func:`parse_interstitial_page` takes HTML bytes
and returns an :class:`InterstitialReport`. :func:`fetch_interstitial`
is the network call. :func:`process_manifest` wires them together over
a manifest CSV produced by ``scripts.msha_scrape_index``.

Usage::

    uv run python -m scripts.msha_scrape_interstitial                # default paths
    uv run python -m scripts.msha_scrape_interstitial \\
        --manifest data/msha/manifest.csv \\
        --out data/msha/interstitials.json \\
        --throttle 1.0
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import re
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from lxml import html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = "unearthed-coal-data/1.0 (+https://github.com/anchildress1/unearthed)"
DEFAULT_THROTTLE_SECONDS = 1.0

# Sections we extract for runtime synthesis. The middle four (DESCRIPTION,
# INVESTIGATION, DISCUSSION, APPENDIX) are dropped because every paragraph
# attributes actions to named individuals. ENFORCEMENT ACTIONS, ROOT CAUSE
# ANALYSIS, OVERVIEW and CONCLUSION read facts against roles ("the mine
# operator", "the foreman") with at most one personal name (the victim) that
# we redact below.
KEPT_SECTIONS: tuple[str, ...] = (
    "OVERVIEW",
    "ROOT CAUSE ANALYSIS",
    "CONCLUSION",
    "ENFORCEMENT ACTIONS",
)

# Mine ID format: "ID No. NN-NNNNN" anywhere in the report's preamble.
_MINE_ID_PATTERN = re.compile(r"ID\s+No\.\s+(\d{2}-\d{4,6})", re.IGNORECASE)

# Accident-type label appears in the preamble as
# "Underground (Coal) Fatal Machinery Accident <Date>" — capture up to "Accident".
_ACCIDENT_TYPE_PATTERN = re.compile(
    r"((?:Underground|Surface)\s*\([^)]+\)\s+Fatal\s+[A-Za-z\s]+?Accident)",
    re.IGNORECASE,
)

# Location: "<City>, <County> County, <State> ID No.". The preamble has no
# clean delimiter between operator and city (the operator name flows
# straight into the city), so we constrain ``city`` to a single TitleCased
# token — every coal-town fatality on file matches this. ``county`` allows
# 1-2 words ("St. Charles County" would not, but no coal county uses one).
# ``state`` allows 1-2 words to cover "West Virginia" / "New Mexico".
_LOCATION_PATTERN = re.compile(
    r"(?P<city>[A-Z][a-zA-Z]+),\s+"
    r"(?P<county>(?:[A-Z][a-zA-Z]+\s+){0,1}[A-Z][a-zA-Z]+)\s+County,\s+"
    r"(?P<state>(?:[A-Z][a-zA-Z]+\s+){0,1}[A-Z][a-zA-Z]+)\s+ID\s+No\."
)


def _normalize_whitespace(text: str) -> str:
    """Collapse any Unicode whitespace (incl. NBSP ``\\xa0``) into single spaces.

    Drupal renders ``&nbsp;`` between fields, which survives as ``\\xa0`` in
    ``etree.text_content()`` output and breaks regexes that expect ASCII
    space. ``str.split()`` (no args) treats every Unicode whitespace as a
    delimiter, so a join-after-split is a one-line normalizer.
    """
    return " ".join(text.split())


# Victim-introduction pattern in OVERVIEW first sentences:
#   "Colton Walls, a 34-year-old electrician with 14 years..."
#   "Colton Walls a 34-year-old electrician..."  (raw extraction sometimes drops the comma)
# We capture name, age, role so we can redact the name across all kept sections.
_VICTIM_INTRO_PATTERN = re.compile(
    r"\b([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'.\-]+){1,3}),?\s+a\s+(\d{2})-year-old\s+([A-Za-z][A-Za-z\s\-]*?)(?:\s+with\s+\d+|\s+was\s+|,)",
)

# Long state name → 2-letter abbreviation. Reused from the index scraper would
# create a circular import; the list is short and stable, so it lives here too.
_STATE_NAMES: dict[str, str] = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
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
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


@dataclass(frozen=True)
class InterstitialReport:
    """Structured form of one MSHA Final Report interstitial page."""

    fatality_url: str  # parent /<year>/<slug>
    final_report_url: str  # /<year>/<slug>/final-report
    pdf_url: str  # absolute URL to the source PDF on msha.gov
    pdf_filename: str  # basename for citation labels

    mine_id: str  # "46-09192", or empty if not found
    city: str  # "Thornton" — town the mine sits in
    county: str  # "Taylor" — county name without the "County" suffix
    state: str  # 2-letter, or empty
    accident_type_label: str  # "Underground (Coal) Fatal Machinery Accident"
    incident_date: str  # ISO, or empty

    sections: dict[str, str]  # KEPT_SECTIONS keys → PII-redacted text

    pii_warning: bool  # True if redaction may have left edge-case names


def _absolute(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"https://www.msha.gov{url}"
    return f"https://www.msha.gov/{url}"


def _walk_sections(body_el) -> dict[str, str]:
    """Split the body element into ``{h2_text: paragraph_text}`` chunks.

    h2 elements are flat siblings inside ``.field--name-body`` (Drupal does
    not nest them). For each h2 we accumulate the textual content of every
    following sibling until the next h2 — a deterministic walk.
    """
    sections: dict[str, str] = {}
    current_heading: str | None = None
    buffer: list[str] = []

    def flush():
        if current_heading is not None:
            sections[current_heading] = " ".join(" ".join(buffer).split())

    # Iterate top-level descendants in document order; the body field
    # flattens the report into siblings so a top-level walk is sufficient.
    for child in body_el.iter():
        if child.tag == "h2":
            flush()
            current_heading = " ".join((child.text_content() or "").split())
            buffer = []
        elif child.text and current_heading is not None:
            buffer.append(child.text)
        if child.tail and current_heading is not None:
            buffer.append(child.tail)
    flush()
    return sections


def _extract_metadata(preamble_text: str) -> dict[str, str]:
    """Pull mine_id / accident_type_label / city / county / state from preamble."""
    out: dict[str, str] = {
        "mine_id": "",
        "accident_type_label": "",
        "city": "",
        "county": "",
        "state": "",
    }

    if m := _MINE_ID_PATTERN.search(preamble_text):
        out["mine_id"] = m.group(1)

    if m := _ACCIDENT_TYPE_PATTERN.search(preamble_text):
        out["accident_type_label"] = " ".join(m.group(1).split())

    if m := _LOCATION_PATTERN.search(preamble_text):
        out["city"] = " ".join(m.group("city").split())
        out["county"] = " ".join(m.group("county").split())
        full_state = " ".join(m.group("state").split())
        out["state"] = _STATE_NAMES.get(full_state, "")

    return out


def _extract_date_from_label(label: str) -> str:
    """Parse the trailing date out of an accident-type label / preamble.

    Reports embed the incident date right after the accident-type label:
    ``... Fatal Machinery Accident September 28, 2024 Leer Mine ...``
    """
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        label,
    )
    if not match:
        return ""
    try:
        return (
            dt.datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%B %d %Y")
            .date()
            .isoformat()
        )
    except ValueError:
        return ""


def _redact_victim(sections: dict[str, str]) -> tuple[dict[str, str], bool]:
    """Strip the victim's name from the kept sections.

    Strategy: scan OVERVIEW for the canonical "<Name>, a <age>-year-old
    <role>" pattern. If found, replace the full name (and standalone
    last name) with "the <role>" across every kept section.

    Returns ``(redacted_sections, pii_warning)``. The warning fires when
    the OVERVIEW had a name pattern but downstream sections still contain
    a long word starting with an uppercase letter that wasn't a known
    role term — a heuristic signal that an investigator/foreman name
    might have leaked through.
    """
    overview = sections.get("OVERVIEW", "")
    intro_match = _VICTIM_INTRO_PATTERN.search(overview)
    if not intro_match:
        # No identifiable victim intro — pass sections through unchanged
        # but flag PII warning so the agent knows to be cautious.
        return sections, True

    full_name = intro_match.group(1).strip()
    role = intro_match.group(3).strip().lower()
    role_phrase = f"the {role}"

    # Build name pieces to redact: full name plus the trailing last-name token.
    # First names are common (Mike, John) and word-boundary substituting them
    # would over-redact; last names are far less ambiguous.
    pieces = [full_name]
    last_name = full_name.split()[-1]
    if len(last_name) > 3 and last_name[0].isupper():
        pieces.append(rf"\bMr\.\s+{re.escape(last_name)}\b")
        pieces.append(rf"\bMrs\.\s+{re.escape(last_name)}\b")
        pieces.append(rf"\bMs\.\s+{re.escape(last_name)}\b")
        pieces.append(rf"\b{re.escape(last_name)}\b")

    redacted: dict[str, str] = {}
    for heading, text in sections.items():
        for pattern in pieces:
            text = re.sub(pattern, role_phrase, text)
        redacted[heading] = text

    # Heuristic: any consecutive Capitalized Title-Cased word pair left in
    # CONCLUSION or OVERVIEW that isn't a known mine/operator term is a hint
    # something slipped through. Cheap to compute, useful for downstream QA.
    suspicious = re.search(
        r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b",
        redacted.get("CONCLUSION", "") + " " + redacted.get("OVERVIEW", ""),
    )
    return redacted, bool(suspicious)


def parse_interstitial_page(
    content: bytes, *, fatality_url: str, final_report_url: str
) -> InterstitialReport:
    """Parse one Final Report interstitial HTML into an :class:`InterstitialReport`.

    Pure function: no network, no filesystem. Tests cover schema drift on the
    MSHA side by feeding captured HTML.
    """
    tree = html.fromstring(content)

    # PDF link lives in .field--name-field-final-pdf — this is the citation
    # URL the runtime agent surfaces alongside any extracted text.
    pdf_url = ""
    pdf_filename = ""
    pdf_links = tree.cssselect(".field--name-field-final-pdf a")
    if pdf_links:
        pdf_url = _absolute(pdf_links[0].get("href") or "")
        # Prefer the anchor text if present (already cleaned), fall back to URL basename.
        anchor_text = (pdf_links[0].text or "").strip()
        pdf_filename = anchor_text or pdf_url.rsplit("/", 1)[-1]

    body_nodes = tree.cssselect(".field--name-body")
    if not body_nodes:
        # Page exists but has no body field — return a minimal record so
        # the manifest writer can flag this row for manual review.
        return InterstitialReport(
            fatality_url=fatality_url,
            final_report_url=final_report_url,
            pdf_url=pdf_url,
            pdf_filename=pdf_filename,
            mine_id="",
            city="",
            county="",
            state="",
            accident_type_label="",
            incident_date="",
            sections={},
            pii_warning=False,
        )

    body_el = body_nodes[0]
    all_sections = _walk_sections(body_el)

    # Drupal sometimes splits the body into multiple `.field--name-body`
    # children (address blocks, footer). Merge any extras we collect off the
    # second/third nodes if their h2 set overlaps — but the first body node
    # is always the report. Defer to it.

    # Identify the preamble — text before the first h2 — for metadata.
    preamble_chunks: list[str] = []
    for child in body_el.iter():
        if child.tag == "h2":
            break
        if child.text:
            preamble_chunks.append(child.text)
        if child.tail:
            preamble_chunks.append(child.tail)
    preamble_text = _normalize_whitespace(" ".join(preamble_chunks))
    metadata = _extract_metadata(preamble_text)

    # Mine name and operator come from the manifest CSV, not from the
    # interstitial preamble — duplicating the parse risks two slightly
    # different versions of the same string in downstream joins.

    incident_date = _extract_date_from_label(preamble_text)

    # Filter sections: keep only those we want to expose, then redact PII.
    kept: dict[str, str] = {}
    for heading, text in all_sections.items():
        normalized = " ".join(heading.split()).upper()
        if normalized in KEPT_SECTIONS:
            kept[normalized] = text
    redacted, pii_warning = _redact_victim(kept)

    return InterstitialReport(
        fatality_url=fatality_url,
        final_report_url=final_report_url,
        pdf_url=pdf_url,
        pdf_filename=pdf_filename,
        mine_id=metadata["mine_id"],
        city=metadata["city"],
        county=metadata["county"],
        state=metadata["state"],
        accident_type_label=metadata["accident_type_label"],
        incident_date=incident_date,
        sections=redacted,
        pii_warning=pii_warning,
    )


def fetch_interstitial(
    final_report_url: str, *, throttle: float = DEFAULT_THROTTLE_SECONDS
) -> bytes:
    """Fetch the HTML of one Final Report interstitial."""
    logger.info("GET %s", final_report_url)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(final_report_url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    if throttle > 0:
        time.sleep(throttle)
    return response.content


def process_manifest(
    manifest_path: Path,
    out_path: Path,
    *,
    fetcher: Callable[[str], bytes] | None = None,
) -> int:
    """Walk the manifest CSV, fetch each Final Report interstitial, write JSON.

    Output format is JSON (not parquet) because the per-incident records have
    nested ``sections`` dicts of varying keys. The downstream parquet builder
    flattens this into a row-oriented schema.

    Skips rows where ``has_final_report`` is ``False`` — those incidents have
    no final report yet and the agent can fall back to the preliminary text
    or just the structured metadata.
    """
    fetcher = fetcher or fetch_interstitial
    out_records: list[dict] = []

    with manifest_path.open(encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            if row.get("has_final_report", "").lower() != "true":
                continue
            url = row["final_report_interstitial_url"]
            try:
                content = fetcher(url)
            except httpx.HTTPError as exc:
                logger.warning("Skipping %s: %s", url, exc)
                continue
            report = parse_interstitial_page(
                content,
                fatality_url=row["fatality_url"],
                final_report_url=url,
            )
            out_records.append(asdict(report))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fp:
        json.dump(out_records, fp, indent=2, ensure_ascii=False)
    tmp_path.replace(out_path)
    logger.info("Wrote %d interstitial records to %s", len(out_records), out_path)
    return len(out_records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/msha/manifest.csv"),
        help="Manifest CSV produced by msha_scrape_index (default: data/msha/manifest.csv).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/msha/interstitials.json"),
        help="Per-incident interstitial JSON output (default: data/msha/interstitials.json).",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=DEFAULT_THROTTLE_SECONDS,
        help=f"Seconds between requests (default: {DEFAULT_THROTTLE_SECONDS}).",
    )
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        logger.error("Manifest not found at %s — run msha_scrape_index first.", args.manifest)
        return 2

    fetcher = lambda url: fetch_interstitial(url, throttle=args.throttle)  # noqa: E731
    count = process_manifest(args.manifest, args.out, fetcher=fetcher)
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
