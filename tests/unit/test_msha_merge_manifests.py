"""Unit tests for ``scripts.msha_merge_manifests``.

The matrix-sharded refresh workflow writes one ``manifest_YYYY.csv``
per year. This module verifies the merger's contract:

* discovery only matches the per-year naming pattern (never the merged
  output, never unrelated CSVs);
* merge preserves a single header, concatenates rows in year order,
  and exits cleanly if no per-year files exist or if a shard's header
  drifted from the canonical schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.msha_merge_manifests import discover_per_year_files, merge


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestDiscoverPerYearFiles:
    """Discovery must match the per-year pattern only."""

    def test_includes_only_manifest_year_files_sorted(self, tmp_path):
        _write(tmp_path / "manifest_2024.csv", ["a,b", "1,2"])
        _write(tmp_path / "manifest_2010.csv", ["a,b", "3,4"])
        _write(tmp_path / "manifest_2018.csv", ["a,b", "5,6"])
        # Decoys: must NOT be picked up.
        _write(tmp_path / "manifest.csv", ["decoy"])
        _write(tmp_path / "unrelated.csv", ["nope"])
        _write(tmp_path / "manifest_99.csv", ["short year"])
        _write(tmp_path / "manifest_20240.csv", ["long year"])

        names = [p.name for p in discover_per_year_files(tmp_path)]
        assert names == ["manifest_2010.csv", "manifest_2018.csv", "manifest_2024.csv"]


class TestMerge:
    """The merge step itself."""

    def test_concatenates_rows_with_single_header(self, tmp_path):
        a = tmp_path / "manifest_2024.csv"
        b = tmp_path / "manifest_2023.csv"
        _write(a, ["a,b", "1,2"])
        _write(b, ["a,b", "3,4"])
        out = tmp_path / "merged.csv"

        rows = merge([b, a], out)

        assert rows == 2
        # Sorted-input order is preserved (caller's responsibility); merge
        # emits whatever it's handed.
        assert out.read_text().splitlines() == ["a,b", "3,4", "1,2"]

    def test_empty_per_year_file_skipped_with_warning(self, tmp_path, caplog):
        non_empty = tmp_path / "manifest_2024.csv"
        empty = tmp_path / "manifest_2007.csv"
        _write(non_empty, ["a,b", "1,2"])
        empty.write_text("", encoding="utf-8")
        out = tmp_path / "merged.csv"

        with caplog.at_level("WARNING"):
            merge([empty, non_empty], out)

        assert any("Empty manifest file" in rec.message for rec in caplog.records)
        assert out.read_text().splitlines() == ["a,b", "1,2"]

    def test_no_files_aborts(self, tmp_path):
        with pytest.raises(SystemExit, match="every shard appears to have failed"):
            merge([], tmp_path / "merged.csv")

    def test_header_mismatch_aborts(self, tmp_path):
        a = tmp_path / "manifest_2024.csv"
        b = tmp_path / "manifest_2023.csv"
        _write(a, ["a,b", "1,2"])
        _write(b, ["a,c", "3,4"])  # drifted column

        with pytest.raises(SystemExit, match="Header mismatch"):
            merge([a, b], tmp_path / "merged.csv")
