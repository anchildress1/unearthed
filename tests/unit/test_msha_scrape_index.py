"""Unit tests for ``scripts.msha_scrape_index``.

Tests run against captured HTML fixtures rather than live MSHA pages so
schema regressions on the MSHA side are caught here, not at refresh time
in CI. The fixtures sit under ``tests/fixtures/msha/`` and were captured
from the live search page in May 2026 — when MSHA next changes the
template the asserts will trip and tell us exactly which selector moved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import msha_scrape_index as scraper

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "msha"


def _load(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


class TestParseSearchPage:
    """Parsing the search results page into structured rows."""

    @pytest.fixture(scope="class")
    def rows(self) -> list[scraper.FatalityRow]:
        return scraper.parse_search_page(_load("search_coal_2025_sample.html"))

    def test_returns_one_row_per_views_row(self, rows):
        """The curated fixture has exactly three .views-row blocks."""
        assert len(rows) == 3

    def test_row_with_final_report_has_all_three_flags(self, rows):
        """The Sept 28, 2024 Leer Mine row has prelim + alert + final."""
        row = rows[0]
        assert row.fatality_url.endswith("/2024/september-28-2024-fatality")
        assert row.has_preliminary_report is True
        assert row.has_fatality_alert is True
        assert row.has_final_report is True
        assert row.final_report_interstitial_url.endswith(
            "/2024/september-28-2024-fatality/final-report"
        )

    def test_row_with_only_preliminary_has_one_flag(self, rows):
        """The April 3, 2026 row is recent — only preliminary published."""
        row = rows[1]
        assert row.has_preliminary_report is True
        assert row.has_fatality_alert is False
        assert row.has_final_report is False
        assert row.final_report_interstitial_url == ""

    def test_row_with_no_buttons_has_no_flags(self, rows):
        """The April 30, 2026 row is brand new — no reports yet."""
        row = rows[2]
        assert row.has_preliminary_report is False
        assert row.has_fatality_alert is False
        assert row.has_final_report is False

    def test_extracts_metadata_fields(self, rows):
        row = rows[0]
        assert row.mine_name == "Leer Mine"
        assert row.mine_state == "WV"
        assert row.accident_classification == "Machinery"
        assert row.mine_controller == "Arch Resources Inc"
        assert row.mine_type == "Underground"
        assert row.primary_sic == "Coal (Bituminous)"

    def test_extracts_iso_date_from_button_datetime(self, rows):
        """The first row's prelim button carries datetime=2024-09-28T11:55:00Z."""
        assert rows[0].incident_date == "2024-09-28"

    def test_falls_back_to_url_slug_when_no_buttons(self, rows):
        """Brand-new fatalities have no buttons; the URL slug carries the date."""
        assert rows[2].incident_date == "2026-04-30"

    def test_makes_urls_absolute(self, rows):
        for row in rows:
            assert row.fatality_url.startswith("https://www.msha.gov/")

    def test_is_coal_classifies_correctly(self, rows):
        # Rows 0 + 1 are Coal (Bituminous); row 2 is Crushed Broken Stone NEC.
        assert rows[0].is_coal is True
        assert rows[1].is_coal is True
        assert rows[2].is_coal is False

    def test_state_extraction_handles_comma_format(self, rows):
        """`Taylor, West Virginia` should extract as WV."""
        assert rows[0].mine_state == "WV"

    def test_state_extraction_handles_no_comma(self, rows):
        """`Dallas West Virginia` (no comma) should still extract as WV."""
        assert rows[1].mine_state == "WV"


class TestParseSearchPageEmpty:
    def test_empty_view_returns_empty_list(self):
        rows = scraper.parse_search_page(_load("search_empty.html"))
        assert rows == []

    def test_completely_empty_html_returns_empty_list(self):
        rows = scraper.parse_search_page(b"<html><body></body></html>")
        assert rows == []


class TestExtractState:
    @pytest.mark.parametrize(
        "location,expected",
        [
            ("Mine Name - City, West Virginia", "WV"),
            ("Mine Name - City West Virginia", "WV"),
            ("Mine Name - City, Pennsylvania", "PA"),
            ("Mine Name - City, Virginia", "VA"),  # Must not greedy-match West Virginia
            ("Mine Name - City, New Mexico", "NM"),  # Multi-word state
            ("Mine Name - City, North Dakota", "ND"),
            ("Mine Name - City, District of Columbia", "DC"),
            ("Unknown Place", ""),
            ("", ""),
        ],
    )
    def test_state_extraction(self, location, expected):
        assert scraper._extract_state(location) == expected

    def test_west_virginia_does_not_collide_with_virginia(self):
        """Sorting by length-desc in the regex matters — `Virginia` would
        match inside `West Virginia` if alternation order were arbitrary."""
        assert scraper._extract_state("Charleston, West Virginia") == "WV"
        assert scraper._extract_state("Richmond, Virginia") == "VA"

    def test_state_in_mine_name_does_not_shadow_trailing_state(self):
        """`Ohio County Mine - Dallas West Virginia` must read as WV, not
        OH — the state always trails the location text, never leads it."""
        assert scraper._extract_state("Ohio County Mine - Dallas West Virginia") == "WV"
        assert scraper._extract_state("Indiana Operations - Cedar Bluff, Kentucky") == "KY"


class TestParseIsoDate:
    def test_prefers_iso_datetime_attr(self):
        result = scraper._parse_iso_date(
            "2024-09-28T11:55:00Z", "/data-reports/fatality-reports/2024/whatever"
        )
        assert result == "2024-09-28"

    def test_falls_back_to_slug_when_attr_missing(self):
        result = scraper._parse_iso_date(
            None,
            "/data-reports/fatality-reports/2026/april-30-2026-fatality",
        )
        assert result == "2026-04-30"

    def test_slug_with_dedup_suffix(self):
        """MSHA appends -0 to slugs when two fatalities share a date."""
        result = scraper._parse_iso_date(
            None,
            "/data-reports/fatality-reports/2025/december-10-2025-fatality-0",
        )
        assert result == "2025-12-10"

    def test_unparseable_attr_falls_back_to_slug(self):
        result = scraper._parse_iso_date(
            "not-a-datetime",
            "/data-reports/fatality-reports/2026/april-30-2026-fatality",
        )
        assert result == "2026-04-30"

    def test_unparseable_inputs_return_empty(self):
        assert scraper._parse_iso_date(None, "/no/match/here") == ""


class TestIterYearPages:
    """Pagination + dedupe behavior, with a mock fetcher."""

    def test_paginates_until_empty(self):
        page0 = _load("search_coal_2025_sample.html")
        page1 = _load("search_empty.html")

        calls: list[tuple[int, int]] = []

        def fetcher(year: int, page: int) -> bytes:
            calls.append((year, page))
            return page0 if page == 0 else page1

        rows = list(scraper.iter_year_pages(2025, fetcher=fetcher))
        assert len(rows) == 3
        # First page yielded results, second was empty and stopped iteration.
        assert calls == [(2025, 0), (2025, 1)]

    def test_dedupes_repeated_rows_across_pages(self):
        """If a stuck cursor returns the same rows on consecutive pages,
        the iterator emits each row once and stops on the duplicate page."""
        page = _load("search_coal_2025_sample.html")

        def fetcher(year: int, page_num: int) -> bytes:
            return page  # always the same content

        rows = list(scraper.iter_year_pages(2025, fetcher=fetcher, max_pages=5))
        assert len(rows) == 3  # only the 3 unique URLs

    def test_respects_max_pages_ceiling(self):
        """If the fetcher never returns empty, the ceiling kicks in."""
        # Each call returns one new row by varying the URL via a counter.
        counter = [0]

        def fetcher(year: int, page_num: int) -> bytes:
            counter[0] += 1
            html = (
                '<html><body><div class="view-content">'
                '<div class="views-row"><div class="views-field views-field-title">'
                f'<h2><a href="/data-reports/fatality-reports/2025/x-{counter[0]}-fatality">'
                "x</a></h2></div></div></div></body></html>"
            )
            return html.encode()

        rows = list(scraper.iter_year_pages(2025, fetcher=fetcher, max_pages=3))
        assert len(rows) == 3  # one new row per page, capped at 3 pages


class TestWriteManifest:
    def test_writes_csv_with_expected_columns(self, tmp_path):
        rows = scraper.parse_search_page(_load("search_coal_2025_sample.html"))
        out = tmp_path / "manifest.csv"
        scraper.write_manifest(rows, out)
        text = out.read_text(encoding="utf-8")
        # Header present
        assert "incident_date,fatality_url,mine_name" in text
        # All three rows written
        assert text.count("\n") == 4  # header + 3 rows

    def test_creates_parent_directory(self, tmp_path):
        out = tmp_path / "nested" / "dir" / "manifest.csv"
        scraper.write_manifest([], out)
        assert out.exists()

    def test_atomic_write_no_tmp_left_behind(self, tmp_path):
        out = tmp_path / "manifest.csv"
        scraper.write_manifest([], out)
        assert out.exists()
        assert not out.with_suffix(".csv.tmp").exists()


class TestParseYearArg:
    def test_single_year(self):
        assert scraper._parse_year_arg("2025") == [2025]

    def test_year_range(self):
        assert scraper._parse_year_arg("2010-2012") == [2010, 2011, 2012]

    def test_inverted_range_rejected(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            scraper._parse_year_arg("2015-2010")


class TestFetchSearchPage:
    """Verify URL composition and headers without making a real request."""

    def test_builds_correct_url_with_filters(self, monkeypatch):
        captured = {}

        class FakeResponse:
            content = b"<html></html>"
            status_code = 200

            def raise_for_status(self):
                # Test double: every fake response is a 200 OK.
                return None

        class FakeClient:
            def __init__(self, *args, **kwargs):
                # Test double: ignores constructor args.
                return None

            def __enter__(self):
                return self

            def __exit__(self, *args):
                # Test double: nothing to clean up.
                return None

            def get(self, url, headers=None):
                captured["url"] = url
                captured["headers"] = headers
                return FakeResponse()

        monkeypatch.setattr(scraper.httpx, "Client", FakeClient)
        scraper.fetch_search_page(2024, 1, throttle=0)

        assert "field_mine_category_target_id=191" in captured["url"]
        assert "year=2024" in captured["url"]
        assert "page=1" in captured["url"]
        assert "User-Agent" in captured["headers"]
        assert "unearthed-coal-data" in captured["headers"]["User-Agent"]

    @pytest.mark.parametrize(
        ("status_code", "body"),
        [
            (202, b"<html></html>"),  # WAF "accepted-but-empty" pattern
            (200, b""),  # honest 200 with truncated body
            (200, b"   \n  "),  # whitespace-only
        ],
    )
    def test_rejects_non_200_or_empty_body(self, monkeypatch, status_code, body):
        """200-only and non-empty body required.

        MSHA's WAF was observed returning ``202 + empty body`` for GHA
        runner IPs. ``raise_for_status`` doesn't trip on 2xx, so without
        these explicit guards the parser saw ``b""`` and raised an
        opaque ``lxml.etree.ParserError``. Now the failure is a clean
        ``MshaFetchError`` naming the URL and status — diagnosable in
        CI logs.
        """

        class FakeResponse:
            def __init__(self, status_code: int, body: bytes) -> None:
                self.status_code = status_code
                self.content = body

            def raise_for_status(self):
                # Test double: 2xx never raises (mirrors httpx semantics).
                return None

        class FakeClient:
            def __init__(self, *args, **kwargs):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def get(self, url, headers=None):
                return FakeResponse(status_code, body)

        monkeypatch.setattr(scraper.httpx, "Client", FakeClient)
        with pytest.raises(scraper.MshaFetchError):
            scraper.fetch_search_page(2024, 0, throttle=0)


class TestParseSearchPageEmptyDefenses:
    """Parser must tolerate empty / whitespace bodies."""

    @pytest.mark.parametrize("content", [b"", b"   ", b"\n\n  \n"])
    def test_returns_empty_list_for_blank_content(self, content):
        # iter_year_pages treats [] as end-of-year, so blank bodies must
        # produce []  rather than raise — that's the contract that makes
        # legitimately-empty years (e.g. 2007 has zero coal fatalities
        # indexed in this view) terminate cleanly.
        assert scraper.parse_search_page(content) == []
