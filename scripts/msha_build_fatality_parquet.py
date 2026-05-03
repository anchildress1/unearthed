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


def _resolve_report_status(*, has_final: bool, has_prelim: bool) -> tuple[str, str]:
    """Return ``(REPORT_STATUS, REPORT_SOURCE)`` from manifest flags alone.

    Status reflects what MSHA has *published*, not whether the build pipeline
    successfully fetched the interstitial — keying off ``has_final`` only
    keeps the two signals consistent: a row with ``has_final=True`` always
    reads ``REPORT_STATUS='final'`` even if section text is missing because
    the interstitial fetch failed. The companion ``SECTION_*`` columns and
    ``MINE_ID`` field tell the runtime whether the deeper extraction landed.
    """
    if has_final:
        return ("final", "msha_final")
    if has_prelim:
        return ("preliminary", "msha_preliminary")
    return ("none", "")


def _first_str(*values) -> str:
    """Return the first non-empty value coerced to ``str``, else ``""``.

    Centralizing this fallback chain keeps :func:`_build_record` readable
    and below the cognitive-complexity ceiling — ``or`` chains inside an
    assignment expression count toward the surrounding function's score.
    """
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def _build_record(row: dict, inter: dict) -> FatalityRecord:
    """Build one :class:`FatalityRecord` by joining a manifest row with its
    (possibly empty) interstitial dict.

    Interstitial values win where they exist — they are the more
    authoritative source — and fall back to manifest values otherwise.
    The manifest's ``location_raw`` carries no county; interstitial fills
    it.
    """
    sections = inter.get("sections") or {}
    has_final = _truthy(row.get("has_final_report", "False"))
    has_prelim = _truthy(row.get("has_preliminary_report", "False"))
    status, source = _resolve_report_status(has_final=has_final, has_prelim=has_prelim)
    return FatalityRecord(
        MINE_ID=_first_str(inter.get("mine_id")),
        INCIDENT_DATE=_first_str(inter.get("incident_date"), row.get("incident_date")),
        MINE_NAME=_first_str(row.get("mine_name")),
        MINE_OPERATOR=_first_str(row.get("mine_controller")),
        MINE_STATE=_first_str(inter.get("state"), row.get("mine_state")),
        MINE_COUNTY=_first_str(inter.get("county")),
        MINE_CITY=_first_str(inter.get("city")),
        MINE_TYPE=_first_str(row.get("mine_type")),
        ACCIDENT_CLASSIFICATION=_first_str(row.get("accident_classification")),
        ACCIDENT_TYPE_LABEL=_first_str(inter.get("accident_type_label")),
        PRIMARY_SIC=_first_str(row.get("primary_sic")),
        FATALITY_URL=row.get("fatality_url", ""),
        REPORT_STATUS=status,
        REPORT_SOURCE=source,
        FINAL_REPORT_URL=_first_str(row.get("final_report_interstitial_url")),
        PDF_URL=_first_str(inter.get("pdf_url")),
        PDF_FILENAME=_first_str(inter.get("pdf_filename")),
        SECTION_OVERVIEW=_first_str(sections.get("OVERVIEW")),
        SECTION_ROOT_CAUSE_ANALYSIS=_first_str(sections.get("ROOT CAUSE ANALYSIS")),
        SECTION_CONCLUSION=_first_str(sections.get("CONCLUSION")),
        SECTION_ENFORCEMENT_ACTIONS=_first_str(sections.get("ENFORCEMENT ACTIONS")),
        PII_WARNING=bool(inter.get("pii_warning", False)),
    )


def merge_records(manifest: list[dict], interstitials: dict[str, dict]) -> list[FatalityRecord]:
    """Join each manifest row with at most one interstitial record."""
    return [
        _build_record(row, interstitials.get(row.get("fatality_url", ""), {})) for row in manifest
    ]


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
