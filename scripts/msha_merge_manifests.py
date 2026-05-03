"""Concatenate per-year MSHA manifests into a single ``manifest.csv``.

The matrix-sharded refresh workflow scrapes each year independently and
each shard writes ``data/msha/manifest_YYYY.csv``. This script runs
after all shards (successful or not) finish: it walks the per-year files
and emits a single merged ``data/msha/manifest.csv`` for the downstream
interstitial scrape and parquet build.

Per-year files preserve their CSV header; only the first file's header
lands in the merged output. Empty per-year files (legitimate years with
no coal fatalities indexed, e.g. 2007) contribute nothing but still
count as successful shards.

Failure modes:

* No ``manifest_*.csv`` files at all → exit 1 (every shard failed; no
  point continuing the pipeline).
* A single per-year file with mismatched columns → exit 1 with the
  offending file path so the schema regression is visible.

Usage::

    uv run python -m scripts.msha_merge_manifests
    uv run python -m scripts.msha_merge_manifests \\
        --src data/msha --out data/msha/manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Per-year file naming. Anchored so a stray ``manifest.csv`` (the merged
# output we're about to write) cannot match — we never want to fold the
# previous merged output back into the new one.
_PER_YEAR_PATTERN = re.compile(r"^manifest_\d{4}\.csv$")


def discover_per_year_files(src: Path) -> list[Path]:
    """Return the per-year manifest CSVs under ``src``, sorted by year."""
    return sorted(p for p in src.glob("manifest_*.csv") if _PER_YEAR_PATTERN.match(p.name))


def merge(per_year: list[Path], out_path: Path) -> int:
    """Merge ``per_year`` files into ``out_path``. Returns row count."""
    if not per_year:
        raise SystemExit(
            "No per-year manifest files found — every shard appears to have failed. "
            "Re-run the workflow or inspect the failed shards before continuing."
        )

    canonical_header: list[str] | None = None
    total_rows = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    with tmp_path.open("w", newline="", encoding="utf-8") as out_fp:
        writer: csv.writer = csv.writer(out_fp)
        for path in per_year:
            with path.open(encoding="utf-8") as in_fp:
                reader = csv.reader(in_fp)
                try:
                    header = next(reader)
                except StopIteration:
                    logger.warning("Empty manifest file (no header): %s", path)
                    continue

                if canonical_header is None:
                    canonical_header = header
                    writer.writerow(canonical_header)
                elif header != canonical_header:
                    raise SystemExit(
                        f"Header mismatch in {path}: got {header}, expected "
                        f"{canonical_header}. Schema drift between shards — "
                        f"investigate scripts/msha_scrape_index.py before merging."
                    )

                file_rows = 0
                for row in reader:
                    writer.writerow(row)
                    file_rows += 1
                logger.info("%s → %d rows", path.name, file_rows)
                total_rows += file_rows

    tmp_path.replace(out_path)
    logger.info("Merged %d rows from %d per-year files → %s", total_rows, len(per_year), out_path)
    return total_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("data/msha"),
        help="Directory containing manifest_YYYY.csv files (default: data/msha).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/msha/manifest.csv"),
        help="Merged output path (default: data/msha/manifest.csv).",
    )
    args = parser.parse_args(argv)

    files = discover_per_year_files(args.src)
    merge(files, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
