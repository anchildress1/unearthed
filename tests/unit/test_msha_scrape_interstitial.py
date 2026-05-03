"""Unit tests for ``scripts.msha_scrape_interstitial``.

The captured fixture (``interstitial_final_2024_leer.html``) is a real
MSHA Final Report interstitial trimmed to the parser-relevant fields.
The encoding is preserved as UTF-8 bytes (with the meta charset header)
so non-breaking spaces survive lxml's text extraction the way they do
on the live page.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import msha_scrape_interstitial as parser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "msha"
LEER_FIXTURE = FIXTURE_DIR / "interstitial_final_2024_leer.html"


@pytest.fixture(scope="module")
def leer_report() -> parser.InterstitialReport:
    content = LEER_FIXTURE.read_bytes()
    return parser.parse_interstitial_page(
        content,
        fatality_url="https://www.msha.gov/data-reports/fatality-reports/2024/september-28-2024-fatality",
        final_report_url="https://www.msha.gov/data-reports/fatality-reports/2024/september-28-2024-fatality/final-report",
    )


class TestParseInterstitialPdfLink:
    def test_pdf_url_extracted_and_absolute(self, leer_report):
        assert leer_report.pdf_url.startswith("https://www.msha.gov/")
        assert leer_report.pdf_url.endswith("Leer%20Mine.pdf")

    def test_pdf_filename_uses_anchor_text_when_present(self, leer_report):
        assert leer_report.pdf_filename == ("September 28, 2024 - Final Report - Leer Mine.pdf")


class TestParseInterstitialMetadata:
    def test_extracts_msha_mine_id(self, leer_report):
        """Mine ID format is ``NN-NNNNN`` and must be lifted out of the
        preamble verbatim — it's the join key with the rest of the corpus."""
        assert leer_report.mine_id == "46-09192"

    def test_extracts_city_county_state(self, leer_report):
        assert leer_report.city == "Thornton"
        assert leer_report.county == "Taylor"
        assert leer_report.state == "WV"

    def test_extracts_accident_type_label(self, leer_report):
        assert leer_report.accident_type_label == "Underground (Coal) Fatal Machinery Accident"

    def test_extracts_iso_incident_date(self, leer_report):
        assert leer_report.incident_date == "2024-09-28"


class TestParseInterstitialSections:
    def test_only_kept_sections_present(self, leer_report):
        """DESCRIPTION OF THE ACCIDENT, INVESTIGATION OF THE ACCIDENT,
        DISCUSSION, and APPENDIX A are intentionally dropped because they
        attribute every action to a named individual."""
        assert set(leer_report.sections.keys()) == set(parser.KEPT_SECTIONS)

    def test_overview_redacts_victim_name(self, leer_report):
        """The OVERVIEW first sentence introduces the victim by name. The
        redactor must replace it with the role descriptor."""
        overview = leer_report.sections["OVERVIEW"]
        assert "Colton" not in overview
        assert "Walls" not in overview
        # Replacement uses the role from the same sentence.
        assert "the electrician" in overview

    def test_conclusion_redacts_victim_name(self, leer_report):
        """CONCLUSION repeats the victim name; same redaction must apply."""
        conclusion = leer_report.sections["CONCLUSION"]
        assert "Walls" not in conclusion
        assert "the electrician" in conclusion

    def test_root_cause_analysis_kept_intact(self, leer_report):
        """ROOT CAUSE ANALYSIS uses role descriptors throughout — nothing to
        redact, but the section text must still be present."""
        rca = leer_report.sections["ROOT CAUSE ANALYSIS"]
        assert "the mine operator" in rca.lower()
        assert "root cause" in rca.lower()

    def test_enforcement_actions_contains_citations(self, leer_report):
        """ENFORCEMENT ACTIONS lists 103(k), 104(a), and 104(d) orders."""
        actions = leer_report.sections["ENFORCEMENT ACTIONS"]
        assert "103(k)" in actions

    def test_no_unicode_nbsp_leaks_into_section_text(self, leer_report):
        """The Drupal page renders many spaces as ``&nbsp;`` (``\\xa0``).
        ``_normalize_whitespace`` and the section walker must collapse them
        into ASCII spaces."""
        for section_text in leer_report.sections.values():
            assert "\xa0" not in section_text


class TestRedactVictim:
    def test_replaces_full_name_throughout(self):
        sections = {
            "OVERVIEW": "John Smith, a 42-year-old foreman, was struck by a falling rock. "
            "Mr. Smith died at the scene.",
            "CONCLUSION": "Smith was checking the longwall when the accident occurred.",
        }
        out, warning = parser._redact_victim(sections)
        assert "John Smith" not in out["OVERVIEW"]
        assert "Mr. Smith" not in out["OVERVIEW"]
        assert "Smith was checking" not in out["CONCLUSION"]
        assert "the foreman" in out["OVERVIEW"]

    def test_returns_warning_when_no_intro_match(self):
        """Sections missing the canonical intro pattern get a PII warning so
        downstream consumers know redaction may be incomplete."""
        sections = {
            "OVERVIEW": "An accident occurred at the mine. Several injuries reported.",
        }
        _, warning = parser._redact_victim(sections)
        assert warning is True

    def test_warning_when_capitalized_word_pair_remains(self):
        """A leftover ``Capitalized Word`` pair in CONCLUSION trips the warning
        even after a successful intro redaction — names of foremen, witnesses
        often slip past the simple last-name replacement."""
        sections = {
            "OVERVIEW": "Jane Doe, a 50-year-old miner, was injured.",
            "CONCLUSION": "The accident was investigated by Bob Roberts and concluded.",
        }
        _, warning = parser._redact_victim(sections)
        # "Bob Roberts" is two consecutive capitalized words — heuristic flag.
        assert warning is True


class TestExtractMetadataIsolated:
    @pytest.mark.parametrize(
        "preamble,expected",
        [
            (
                "Adger, Jefferson County, Alabama ID No. 01-00851",
                {"city": "Adger", "county": "Jefferson", "state": "AL"},
            ),
            (
                "Sharples, Logan County, West Virginia ID No. 46-09029",
                {"city": "Sharples", "county": "Logan", "state": "WV"},
            ),
            (
                "Somerset, Gunnison County, Colorado ID No. 05-03672",
                {"city": "Somerset", "county": "Gunnison", "state": "CO"},
            ),
            (
                "Thornton, Taylor County, West Virginia ID No. 46-09192",
                {"city": "Thornton", "county": "Taylor", "state": "WV"},
            ),
        ],
    )
    def test_extracts_location_across_real_preambles(self, preamble, expected):
        out = parser._extract_metadata(preamble)
        for key, value in expected.items():
            assert out[key] == value


class TestProcessManifest:
    """End-to-end CSV → JSON pipeline against the fixture."""

    def test_skips_rows_without_final_report(self, tmp_path):
        manifest = tmp_path / "manifest.csv"
        with manifest.open("w", newline="") as fp:
            writer = csv.DictWriter(
                fp,
                fieldnames=[
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
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "incident_date": "2026-04-30",
                    "fatality_url": "https://www.msha.gov/x",
                    "mine_name": "X",
                    "location_raw": "X",
                    "mine_state": "WV",
                    "accident_classification": "X",
                    "mine_controller": "X",
                    "mine_type": "Surface",
                    "primary_sic": "Coal (Bituminous)",
                    "has_preliminary_report": "False",
                    "has_fatality_alert": "False",
                    "has_final_report": "False",
                    "final_report_interstitial_url": "",
                }
            )
        out = tmp_path / "interstitials.json"
        # Fetcher should never be called because no final-report rows exist.
        called = []
        count = parser.process_manifest(
            manifest, out, fetcher=lambda url: called.append(url) or b""
        )
        assert count == 0
        assert called == []
        assert json.loads(out.read_text()) == []

    def test_processes_final_report_rows(self, tmp_path):
        manifest = tmp_path / "manifest.csv"
        with manifest.open("w", newline="") as fp:
            writer = csv.DictWriter(
                fp,
                fieldnames=[
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
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "incident_date": "2024-09-28",
                    "fatality_url": "https://www.msha.gov/.../september-28-2024-fatality",
                    "mine_name": "Leer Mine",
                    "location_raw": "Leer Mine - Taylor, West Virginia",
                    "mine_state": "WV",
                    "accident_classification": "Machinery",
                    "mine_controller": "Arch Resources Inc",
                    "mine_type": "Underground",
                    "primary_sic": "Coal (Bituminous)",
                    "has_preliminary_report": "True",
                    "has_fatality_alert": "True",
                    "has_final_report": "True",
                    "final_report_interstitial_url": "https://www.msha.gov/.../final-report",
                }
            )
        out = tmp_path / "interstitials.json"
        count = parser.process_manifest(
            manifest, out, fetcher=lambda url: LEER_FIXTURE.read_bytes()
        )
        assert count == 1
        data = json.loads(out.read_text())
        assert data[0]["mine_id"] == "46-09192"
        assert data[0]["state"] == "WV"
        assert "OVERVIEW" in data[0]["sections"]


class TestFetchInterstitial:
    def test_uses_polite_user_agent(self, monkeypatch):
        captured = {}

        class FakeResp:
            content = b"<html></html>"

            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url, headers=None):
                captured["url"] = url
                captured["headers"] = headers
                return FakeResp()

        monkeypatch.setattr(parser.httpx, "Client", FakeClient)
        parser.fetch_interstitial("https://www.msha.gov/x/final-report", throttle=0)
        assert captured["url"] == "https://www.msha.gov/x/final-report"
        assert "unearthed-coal-data" in captured["headers"]["User-Agent"]


class TestMissingBodyField:
    def test_returns_minimal_record(self):
        """Page that exists but lacks ``.field--name-body`` yields a record
        with empty section dict — not a crash."""
        html_bytes = b"<html><body><h1>404</h1></body></html>"
        result = parser.parse_interstitial_page(
            html_bytes, fatality_url="/x", final_report_url="/x/final-report"
        )
        assert result.sections == {}
        assert result.mine_id == ""
