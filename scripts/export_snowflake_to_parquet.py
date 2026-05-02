"""Export Snowflake tables to local Parquet files.

Reads each table named in the manifest below, writes one Parquet file per
table under ``data/parquet/{layer}/{name}.parquet``, and validates the row
count of the written file against ``SELECT COUNT(*)`` from Snowflake.
**Fails loudly on mismatch** — the migration spec calls out silent data
loss as the worst possible outcome.

Usage::

    uv run python -m scripts.export_snowflake_to_parquet            # all tables
    uv run python -m scripts.export_snowflake_to_parquet emissions  # one alias

Output directory defaults to ``./data/parquet``; override with
``--out`` if you need to write somewhere else.

``SELECT *`` is used here on purpose — we want every column, the result
is materialized exactly once at export time, and the perf-driven
"specify columns" rule in AGENTS.md §3 governs runtime queries against
the columnar warehouse. An export to local disk is neither.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq
import snowflake.connector

from app.snowflake_client import _get_connection

# Snowflake does not allow parameter binding for table names — that part of
# the SQL has to be interpolated. To keep the SELECT/COUNT call sites
# defensible, every fully-qualified name in the manifest is checked against
# this strict pattern at module load: three uppercase identifier segments
# (DB.SCHEMA.TABLE), letters/digits/underscore only. Anything else aborts
# import — Semgrep's CWE-89 concern is structurally unreachable.
_FQ_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*$")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportTarget:
    """One row of the export manifest.

    ``alias`` is the CLI-friendly short name. ``layer`` maps to the bucket
    prefix (``raw`` or ``mrt``) so the output file lands at
    ``data/parquet/{layer}/{filename}.parquet`` and uploads cleanly to
    ``s3://unearthed-data/{layer}/{filename}.parquet``.
    """

    alias: str
    layer: str
    filename: str
    fully_qualified: str


_MANIFEST: tuple[ExportTarget, ...] = (
    ExportTarget("msha_mines", "raw", "msha_mines", "UNEARTHED_DB.RAW.MSHA_MINES"),
    ExportTarget(
        "msha_production",
        "raw",
        "msha_quarterly_production",
        "UNEARTHED_DB.RAW.MSHA_QUARTERLY_PRODUCTION",
    ),
    ExportTarget("msha_accidents", "raw", "msha_accidents", "UNEARTHED_DB.RAW.MSHA_ACCIDENTS"),
    ExportTarget(
        "eia_receipts",
        "raw",
        "eia_923_fuel_receipts",
        "UNEARTHED_DB.RAW.EIA_923_FUEL_RECEIPTS",
    ),
    ExportTarget("eia_plants", "raw", "eia_860_plants", "UNEARTHED_DB.RAW.EIA_860_PLANTS"),
    ExportTarget(
        "subregion_lookup",
        "raw",
        "plant_subregion_lookup",
        "UNEARTHED_DB.RAW.PLANT_SUBREGION_LOOKUP",
    ),
    ExportTarget(
        "v_mine_for_plant",
        "mrt",
        "v_mine_for_plant",
        "UNEARTHED_DB.MRT.V_MINE_FOR_PLANT",
    ),
    ExportTarget(
        "v_mine_for_subregion",
        "mrt",
        "v_mine_for_subregion",
        "UNEARTHED_DB.MRT.V_MINE_FOR_SUBREGION",
    ),
    ExportTarget(
        "mine_plant_for_subregion",
        "mrt",
        "mine_plant_for_subregion",
        "UNEARTHED_DB.MRT.MINE_PLANT_FOR_SUBREGION",
    ),
    ExportTarget(
        "emissions",
        "mrt",
        "emissions_by_plant",
        "UNEARTHED_DB.MRT.EMISSIONS_BY_PLANT",
    ),
)


def _safe_table_ref(target: ExportTarget) -> str:
    """Re-validate the manifest entry's qualified name on every use.

    Belt-and-suspenders against a future contributor adding a manifest
    entry that smuggles SQL through the qualified-name field. The pattern
    rejects everything except ``DB.SCHEMA.TABLE`` triplets composed of
    uppercase-letter / digit / underscore tokens — no whitespace, no
    quotes, no semicolons.
    """
    fq = target.fully_qualified
    if not _FQ_NAME_PATTERN.fullmatch(fq):
        raise RuntimeError(
            f"Refusing to interpolate suspicious table name: {fq!r}. "
            "Manifest entries must match DB.SCHEMA.TABLE in uppercase."
        )
    return fq


# Sanity-check the manifest at import time so a malformed entry never
# reaches a query — fail loudly here, not at first export.
for _t in _MANIFEST:
    _safe_table_ref(_t)


def _resolve_targets(aliases: list[str]) -> list[ExportTarget]:
    if not aliases:
        return list(_MANIFEST)
    by_alias = {t.alias: t for t in _MANIFEST}
    unknown = [a for a in aliases if a not in by_alias]
    if unknown:
        raise SystemExit(f"Unknown alias(es): {unknown}. Known aliases: {sorted(by_alias)}")
    return [by_alias[a] for a in aliases]


def _export_one(target: ExportTarget, out_root: Path) -> None:
    """Read one table from Snowflake, write Parquet, validate row count.

    ``fq`` is interpolated directly into the SQL because Snowflake's
    parameter binding does not cover identifiers — only literal values.
    Safety is established by ``_safe_table_ref``: the qualified name is
    re-validated against a strict allowlist regex on every export, and
    the entire manifest is checked at module import. Semgrep CWE-89 is a
    structural false positive here.
    """
    fq = _safe_table_ref(target)
    logger.info("Exporting %s → %s/%s.parquet", fq, target.layer, target.filename)
    conn = _get_connection()
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        # Authoritative count first — if Snowflake reports N rows and the
        # parquet writer ends up with M, the assertion below tells us the
        # connector dropped rows mid-fetch instead of silently lying.
        cur.execute(f"SELECT COUNT(*) AS C FROM {fq}")  # nosemgrep
        row = cur.fetchone()
        expected = int(row["C"])
    finally:
        cur.close()

    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {fq}")  # nosemgrep
        table = cur.fetch_arrow_all()
    finally:
        cur.close()

    actual = 0 if table is None else table.num_rows
    if actual != expected:
        raise RuntimeError(
            f"Row count mismatch for {fq}: "
            f"COUNT(*) reported {expected}, parquet has {actual}. "
            "Refusing to write — investigate before re-running."
        )

    out_path = out_root / target.layer / f"{target.filename}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if table is None:
        # An empty table still needs a parquet file with the right schema —
        # otherwise downstream readers fall through to "file missing"
        # instead of "table is empty." Snowflake's connector returns None
        # only when the result set has zero rows; recover the schema with
        # a separate metadata-only query.
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT * FROM {fq} LIMIT 0")  # nosemgrep
            table = cur.fetch_arrow_all()
        finally:
            cur.close()
        if table is None:
            raise RuntimeError(
                f"Could not determine schema for {fq} — "
                "even the LIMIT 0 query returned no Arrow table."
            )
    pq.write_table(table, out_path)
    logger.info("  → wrote %d rows to %s", actual, out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "aliases",
        nargs="*",
        help="Specific manifest aliases to export (default: all).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/parquet"),
        help="Output directory (default: ./data/parquet).",
    )
    args = parser.parse_args(argv)

    targets = _resolve_targets(args.aliases)
    out_root: Path = args.out.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    failures: list[tuple[str, str]] = []
    for target in targets:
        try:
            _export_one(target, out_root)
        except Exception as exc:
            logger.exception("Export failed for %s", target.alias)
            failures.append((target.alias, str(exc)))

    if failures:
        logger.error("%d export(s) failed:", len(failures))
        for alias, msg in failures:
            logger.error("  %s: %s", alias, msg)
        return 1
    logger.info("All %d export(s) completed.", len(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
