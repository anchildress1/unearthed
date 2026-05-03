"""Build ``mrt/fatality_narratives.parquet`` from the manifest + interstitials.

Joins :mod:`scripts.msha_scrape_index` output (one row per fatality, with
search-index metadata) with :mod:`scripts.msha_scrape_interstitial` output
(per-incident structured sections) on ``fatality_url`` and writes a single
columnar artifact the runtime agent queries via DuckDB.

Schema rationale: column names are UPPERCASE to match the convention the
existing data_client SQL uses against the rest of the corpus (see
``EMISSIONS_BY_PLANT``, ``MINE_PLANT_FOR_SUBREGION``). One row per
fatality incident — the same mine appears multiple times if it has
multiple fatalities, and that is exactly what the agent needs to compute
"<mine> has had N fatalities since <year>" without a separate aggregation.

The ``SECTION_*`` columns hold the raw extracted prose for runtime
synthesis: the agent reads them inside its tool-call response and renders
the answer in the user's voice. Column-level nullability matters — many
incidents have no final report yet, so the section columns are empty
strings (not null) for those rows. DuckDB reads "" as text without
ceremony.

Usage::

    uv run python -m scripts.msha_build_fatality_parquet                 # default paths
    uv run python -m scripts.msha_build_fatality_parquet \\
        --manifest data/msha/manifest.csv \\
        --interstitials data/msha/interstitials.json \\
        --out data/parquet/mrt/fatality_narratives.parquet
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# Output schema — one row per fatality. Column names are UPPERCASE to match
# the rest of the data_client corpus. Section columns hold raw HTML-derived
# prose; the runtime agent does the synthesis at request time.
SCHEMA_COLUMNS: tuple[str, ...] = (
    "MINE_ID",
    "INCIDENT_DATE",
    "MINE_NAME",
    "MINE_OPERATOR",
    "MINE_STATE",
    "MINE_COUNTY",
    "MINE_CITY",
    "MINE_TYPE",
    "ACCIDENT_CLASSIFICATION",
    "ACCIDENT_TYPE_LABEL",
    "PRIMARY_SIC",
    "FATALITY_URL",
    "REPORT_STATUS",
    "REPORT_SOURCE",
    "FINAL_REPORT_URL",
    "PDF_URL",
    "PDF_FILENAME",
    "SECTION_OVERVIEW",
    "SECTION_ROOT_CAUSE_ANALYSIS",
    "SECTION_CONCLUSION",
    "SECTION_ENFORCEMENT_ACTIONS",
    "PII_WARNING",
)


@dataclass(frozen=True)
class FatalityRecord:
    """Joined manifest + interstitial row, the unit of the parquet."""

    MINE_ID: str
    INCIDENT_DATE: str
    MINE_NAME: str
    MINE_OPERATOR: str
    MINE_STATE: str
    MINE_COUNTY: str
    MINE_CITY: str
    MINE_TYPE: str
    ACCIDENT_CLASSIFICATION: str
    ACCIDENT_TYPE_LABEL: str
    PRIMARY_SIC: str
    FATALITY_URL: str
    REPORT_STATUS: str  # "final" | "preliminary" | "none"
    REPORT_SOURCE: str  # "msha_final" | "msha_preliminary" | ""
    FINAL_REPORT_URL: str
    PDF_URL: str
    PDF_FILENAME: str
    SECTION_OVERVIEW: str
    SECTION_ROOT_CAUSE_ANALYSIS: str
    SECTION_CONCLUSION: str
    SECTION_ENFORCEMENT_ACTIONS: str
    PII_WARNING: bool


def _load_manifest(path: Path) -> list[dict]:
    """Read the manifest CSV into a list of dicts.

    Booleans come through as the strings ``"True"`` / ``"False"`` because
    csv.DictReader has no type information; conversion lives at the merge
    site so the manifest format stays portable.
    """
    with path.open(encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def _load_interstitials(path: Path) -> dict[str, dict]:
    """Read the interstitials JSON and key by ``fatality_url`` for join."""
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    return {rec["fatality_url"]: rec for rec in records}


def _truthy(value: str) -> bool:
    """CSV booleans arrive as 'True' / 'False' strings; normalize them."""
    return str(value).strip().lower() == "true"


def _resolve_county_from_manifest(location_raw: str) -> str:
    """Best-effort county extraction from the manifest's ``location`` field.

    Format: ``<Mine Name> - <City>, <State>``. The manifest does not carry
    county at all — so we return empty and let the interstitial fill it.
    """
    return ""


def merge_records(manifest: list[dict], interstitials: dict[str, dict]) -> list[FatalityRecord]:
    """Join one manifest row with at most one interstitial record."""
    out: list[FatalityRecord] = []
    for row in manifest:
        url = row.get("fatality_url", "")
        inter = interstitials.get(url, {})

        has_final = _truthy(row.get("has_final_report", "False"))
        has_prelim = _truthy(row.get("has_preliminary_report", "False"))
        sections = inter.get("sections", {}) or {}

        # Report status / source signal what the agent can quote from. ``final``
        # outranks ``preliminary`` outranks ``none``. The agent's skill prompt
        # uses these flags to decide whether to surface section text or fall
        # back to the search-index metadata only.
        if has_final and inter:
            report_status = "final"
            report_source = "msha_final"
        elif has_prelim:
            report_status = "preliminary"
            report_source = "msha_preliminary"
        else:
            report_status = "none"
            report_source = ""

        # Prefer interstitial values where they exist (richer, more authoritative);
        # fall back to manifest values where the interstitial lacks the field.
        out.append(
            FatalityRecord(
                MINE_ID=str(inter.get("mine_id") or ""),
                INCIDENT_DATE=str(inter.get("incident_date") or row.get("incident_date") or ""),
                MINE_NAME=str(row.get("mine_name") or ""),
                MINE_OPERATOR=str(row.get("mine_controller") or ""),
                MINE_STATE=str(inter.get("state") or row.get("mine_state") or ""),
                MINE_COUNTY=str(
                    inter.get("county")
                    or _resolve_county_from_manifest(row.get("location_raw", ""))
                ),
                MINE_CITY=str(inter.get("city") or ""),
                MINE_TYPE=str(row.get("mine_type") or ""),
                ACCIDENT_CLASSIFICATION=str(row.get("accident_classification") or ""),
                ACCIDENT_TYPE_LABEL=str(inter.get("accident_type_label") or ""),
                PRIMARY_SIC=str(row.get("primary_sic") or ""),
                FATALITY_URL=url,
                REPORT_STATUS=report_status,
                REPORT_SOURCE=report_source,
                FINAL_REPORT_URL=str(row.get("final_report_interstitial_url") or ""),
                PDF_URL=str(inter.get("pdf_url") or ""),
                PDF_FILENAME=str(inter.get("pdf_filename") or ""),
                SECTION_OVERVIEW=str(sections.get("OVERVIEW") or ""),
                SECTION_ROOT_CAUSE_ANALYSIS=str(sections.get("ROOT CAUSE ANALYSIS") or ""),
                SECTION_CONCLUSION=str(sections.get("CONCLUSION") or ""),
                SECTION_ENFORCEMENT_ACTIONS=str(sections.get("ENFORCEMENT ACTIONS") or ""),
                PII_WARNING=bool(inter.get("pii_warning", False)),
            )
        )
    return out


def build_arrow_table(records: list[FatalityRecord]) -> pa.Table:
    """Materialize the joined records as a pyarrow Table.

    Column order matches :data:`SCHEMA_COLUMNS` so DuckDB's positional
    binding stays predictable across rebuilds. All section columns are
    string-typed (not ``binary``) — DuckDB reads them as ``VARCHAR`` and
    the agent's tool wrapper hands them to the LLM as plain text.
    """
    cols: dict[str, list] = {name: [] for name in SCHEMA_COLUMNS}
    for rec in records:
        for name in SCHEMA_COLUMNS:
            cols[name].append(getattr(rec, name))

    schema = pa.schema(
        [(name, pa.bool_() if name == "PII_WARNING" else pa.string()) for name in SCHEMA_COLUMNS]
    )
    arrays = [pa.array(cols[name], type=schema.field(name).type) for name in SCHEMA_COLUMNS]
    return pa.Table.from_arrays(arrays, schema=schema)


def write_parquet(records: list[FatalityRecord], out_path: Path) -> None:
    """Atomic write of the parquet via .tmp + rename."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = build_arrow_table(records)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    pq.write_table(table, tmp_path)
    tmp_path.replace(out_path)
    logger.info("Wrote %d rows to %s", len(records), out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/msha/manifest.csv"),
        help="Manifest CSV from msha_scrape_index (default: data/msha/manifest.csv).",
    )
    parser.add_argument(
        "--interstitials",
        type=Path,
        default=Path("data/msha/interstitials.json"),
        help=(
            "Interstitial JSON from msha_scrape_interstitial "
            "(default: data/msha/interstitials.json)."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/parquet/mrt/fatality_narratives.parquet"),
        help="Output parquet path.",
    )
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        logger.error("Manifest not found at %s — run msha_scrape_index first.", args.manifest)
        return 2

    manifest = _load_manifest(args.manifest)
    interstitials = _load_interstitials(args.interstitials)
    logger.info(
        "Loaded %d manifest rows + %d interstitial records",
        len(manifest),
        len(interstitials),
    )

    records = merge_records(manifest, interstitials)
    write_parquet(records, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
