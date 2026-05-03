"""Unit tests for ``scripts.msha_build_fatality_parquet``.

Verifies the merge + parquet-write pipeline against synthetic manifest +
interstitial inputs. Reading the parquet back with pyarrow proves the
schema binding holds end-to-end without needing DuckDB plumbing here.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from scripts import msha_build_fatality_parquet as builder


def _write_manifest(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "incident_date",
        "fatality_url",
        "mine_name",
        "location_raw",
        "mine_state",
        "accident_classification",
        "mine_controller",
        "mine_type",
        "primary_sic",
        "has_preliminary_report",
        "has_fatality_alert",
        "has_final_report",
        "final_report_interstitial_url",
    ]
    with path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_interstitials(path: Path, records: list[dict]) -> None:
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


@pytest.fixture
def fixtures(tmp_path):
    manifest_path = tmp_path / "manifest.csv"
    inter_path = tmp_path / "interstitials.json"
    out_path = tmp_path / "mrt" / "fatality_narratives.parquet"
    return manifest_path, inter_path, out_path


class TestTruthy:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("True", True),
            ("true", True),
            ("TRUE", True),
            ("False", False),
            ("", False),
            ("foo", False),
        ],
    )
    def test_csv_boolean_normalization(self, value, expected):
        assert builder._truthy(value) is expected


class TestMergeRecords:
    def test_joins_manifest_with_interstitial_on_fatality_url(self):
        manifest = [
            {
                "fatality_url": "https://x.test/foo",
                "incident_date": "2024-09-28",
                "mine_name": "Leer Mine",
                "mine_controller": "Arch Resources Inc",
                "mine_state": "WV",
                "mine_type": "Underground",
                "accident_classification": "Machinery",
                "primary_sic": "Coal (Bituminous)",
                "has_preliminary_report": "True",
                "has_fatality_alert": "True",
                "has_final_report": "True",
                "final_report_interstitial_url": "https://x.test/foo/final-report",
                "location_raw": "Leer Mine - Taylor, West Virginia",
            }
        ]
        interstitials = {
            "https://x.test/foo": {
                "fatality_url": "https://x.test/foo",
                "mine_id": "46-09192",
                "city": "Thornton",
                "county": "Taylor",
                "state": "WV",
                "accident_type_label": "Underground (Coal) Fatal Machinery Accident",
                "incident_date": "2024-09-28",
                "pdf_url": "https://x.test/foo.pdf",
                "pdf_filename": "Final Report - Leer Mine.pdf",
                "sections": {
                    "OVERVIEW": "On September 28, ... the electrician was injured.",
                    "ROOT CAUSE ANALYSIS": "The mine operator did not have a written policy.",
                    "CONCLUSION": "The accident occurred because ...",
                    "ENFORCEMENT ACTIONS": "1. A 103(k) order was issued.",
                },
                "pii_warning": False,
            }
        }
        records = builder.merge_records(manifest, interstitials)
        assert len(records) == 1
        rec = records[0]
        assert rec.MINE_ID == "46-09192"
        assert rec.MINE_NAME == "Leer Mine"
        assert rec.MINE_OPERATOR == "Arch Resources Inc"
        assert rec.MINE_COUNTY == "Taylor"
        assert rec.MINE_CITY == "Thornton"
        assert rec.MINE_STATE == "WV"
        assert rec.REPORT_STATUS == "final"
        assert rec.REPORT_SOURCE == "msha_final"
        assert rec.SECTION_OVERVIEW.startswith("On September 28")
        assert "103(k)" in rec.SECTION_ENFORCEMENT_ACTIONS
        assert rec.PII_WARNING is False

    def test_manifest_row_without_interstitial_falls_back(self):
        """A fatality with no final report has no interstitial — the row must
        still appear in the parquet so downstream counts are honest."""
        manifest = [
            {
                "fatality_url": "https://x.test/recent",
                "incident_date": "2026-04-30",
                "mine_name": "Recent Mine",
                "mine_controller": "RecentCo",
                "mine_state": "WV",
                "mine_type": "Surface",
                "accident_classification": "Slip or Fall of Person",
                "primary_sic": "Coal (Bituminous)",
                "has_preliminary_report": "False",
                "has_fatality_alert": "False",
                "has_final_report": "False",
                "final_report_interstitial_url": "",
                "location_raw": "Recent Mine - Charleston, West Virginia",
            }
        ]
        records = builder.merge_records(manifest, {})
        assert len(records) == 1
        rec = records[0]
        assert rec.MINE_ID == ""
        assert rec.MINE_NAME == "Recent Mine"
        assert rec.MINE_STATE == "WV"
        assert rec.REPORT_STATUS == "none"
        assert rec.REPORT_SOURCE == ""
        assert rec.SECTION_OVERVIEW == ""

    def test_preliminary_only_row_marks_status_preliminary(self):
        manifest = [
            {
                "fatality_url": "https://x.test/prelim",
                "incident_date": "2026-04-03",
                "mine_name": "Ohio County Mine",
                "mine_controller": "ACNR Holdings Inc",
                "mine_state": "WV",
                "mine_type": "Underground",
                "accident_classification": "Powered Haulage",
                "primary_sic": "Coal (Bituminous)",
                "has_preliminary_report": "True",
                "has_fatality_alert": "False",
                "has_final_report": "False",
                "final_report_interstitial_url": "",
                "location_raw": "Ohio County Mine - Dallas West Virginia",
            }
        ]
        records = builder.merge_records(manifest, {})
        assert records[0].REPORT_STATUS == "preliminary"
        assert records[0].REPORT_SOURCE == "msha_preliminary"


class TestBuildArrowTable:
    def test_table_columns_match_schema(self):
        manifest = [
            {
                "fatality_url": "https://x.test/foo",
                "incident_date": "2024-01-01",
                "mine_name": "X",
                "mine_controller": "X",
                "mine_state": "WV",
                "mine_type": "Surface",
                "accident_classification": "X",
                "primary_sic": "Coal (Bituminous)",
                "has_preliminary_report": "False",
                "has_fatality_alert": "False",
                "has_final_report": "False",
                "final_report_interstitial_url": "",
                "location_raw": "X",
            }
        ]
        records = builder.merge_records(manifest, {})
        table = builder.build_arrow_table(records)
        assert table.column_names == list(builder.SCHEMA_COLUMNS)

    def test_pii_warning_typed_as_bool(self):
        manifest = [
            {
                "fatality_url": "https://x.test/foo",
                "has_final_report": "False",
                "has_preliminary_report": "False",
                "has_fatality_alert": "False",
            }
        ]
        records = builder.merge_records(manifest, {})
        table = builder.build_arrow_table(records)
        assert str(table.schema.field("PII_WARNING").type) == "bool"

    def test_string_columns_typed_as_string(self):
        manifest = [
            {
                "fatality_url": "https://x.test/foo",
                "has_final_report": "False",
                "has_preliminary_report": "False",
                "has_fatality_alert": "False",
            }
        ]
        records = builder.merge_records(manifest, {})
        table = builder.build_arrow_table(records)
        for name in builder.SCHEMA_COLUMNS:
            if name == "PII_WARNING":
                continue
            assert str(table.schema.field(name).type) == "string"


class TestWriteParquet:
    def test_writes_atomic_parquet_readable_by_pyarrow(self, fixtures):
        _, _, out_path = fixtures
        manifest = [
            {
                "fatality_url": "https://x.test/foo",
                "incident_date": "2024-09-28",
                "mine_name": "Leer Mine",
                "mine_controller": "Arch Resources Inc",
                "mine_state": "WV",
                "mine_type": "Underground",
                "accident_classification": "Machinery",
                "primary_sic": "Coal (Bituminous)",
                "has_final_report": "False",
                "has_preliminary_report": "False",
                "has_fatality_alert": "False",
                "final_report_interstitial_url": "",
                "location_raw": "Leer Mine - Taylor, West Virginia",
            }
        ]
        records = builder.merge_records(manifest, {})
        builder.write_parquet(records, out_path)
        assert out_path.exists()
        # No leftover .tmp
        assert not out_path.with_suffix(out_path.suffix + ".tmp").exists()
        # Round-trip read
        table = pq.read_table(out_path)
        assert table.num_rows == 1
        assert table.column("MINE_NAME").to_pylist() == ["Leer Mine"]


class TestMainCli:
    def test_writes_parquet_from_files(self, fixtures, capsys):
        manifest_path, inter_path, out_path = fixtures
        _write_manifest(
            manifest_path,
            [
                {
                    "fatality_url": "https://x.test/foo",
                    "incident_date": "2024-09-28",
                    "mine_name": "Leer Mine",
                    "mine_controller": "Arch Resources Inc",
                    "mine_state": "WV",
                    "mine_type": "Underground",
                    "accident_classification": "Machinery",
                    "primary_sic": "Coal (Bituminous)",
                    "has_preliminary_report": "True",
                    "has_fatality_alert": "True",
                    "has_final_report": "True",
                    "final_report_interstitial_url": "https://x.test/foo/final-report",
                    "location_raw": "Leer Mine - Taylor, West Virginia",
                }
            ],
        )
        _write_interstitials(
            inter_path,
            [
                {
                    "fatality_url": "https://x.test/foo",
                    "mine_id": "46-09192",
                    "city": "Thornton",
                    "county": "Taylor",
                    "state": "WV",
                    "accident_type_label": "Underground (Coal) Fatal Machinery Accident",
                    "incident_date": "2024-09-28",
                    "pdf_url": "https://x.test/foo.pdf",
                    "pdf_filename": "Final Report.pdf",
                    "sections": {
                        "OVERVIEW": "...",
                        "ROOT CAUSE ANALYSIS": "...",
                        "CONCLUSION": "...",
                        "ENFORCEMENT ACTIONS": "...",
                    },
                    "pii_warning": False,
                }
            ],
        )
        rc = builder.main(
            [
                "--manifest",
                str(manifest_path),
                "--interstitials",
                str(inter_path),
                "--out",
                str(out_path),
            ]
        )
        assert rc == 0
        table = pq.read_table(out_path)
        assert table.num_rows == 1
        assert table.column("MINE_ID").to_pylist() == ["46-09192"]

    def test_returns_error_when_manifest_missing(self, tmp_path):
        rc = builder.main(
            [
                "--manifest",
                str(tmp_path / "nonexistent.csv"),
                "--interstitials",
                str(tmp_path / "inter.json"),
                "--out",
                str(tmp_path / "out.parquet"),
            ]
        )
        assert rc == 2
