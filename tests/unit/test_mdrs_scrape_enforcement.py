"""Unit tests for ``scripts.mdrs_scrape_enforcement`` pure helpers.

The browser-driving paths (``drill_mine``, ``scrape_mines``) are covered
by manual end-to-end runs against MDRS — they require a live MSHA
session and are not safe to assert against in CI. The pure helpers
below are deterministic and fully unit-tested here.
"""

from __future__ import annotations

import pytest

from scripts import mdrs_scrape_enforcement as scraper


class TestValidateMineId:
    """The 7-digit numeric contract MSHA mines IDs must satisfy."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("4609192", "4609192"),  # canonical 7-digit
            ("46-09192", "4609192"),  # human-friendly hyphenated form
            ("  4609192  ", "4609192"),  # whitespace tolerated
            ("0103354", "0103354"),  # leading zero preserved
        ],
    )
    def test_accepts_valid_forms(self, raw, expected):
        assert scraper.validate_mine_id(raw) == expected

    @pytest.mark.parametrize(
        "bad",
        [
            "",  # empty
            "1234",  # too short
            "12345678",  # too long
            "abcdefg",  # non-numeric
            "46-9192",  # hyphenated form with wrong digit count
            "12.34567",  # decimal points are not digits
        ],
    )
    def test_rejects_invalid_forms(self, bad):
        with pytest.raises(ValueError, match="7 digits"):
            scraper.validate_mine_id(bad)


class TestCountMarkers:
    """The drill-in heuristic that signals whether the per-mine page loaded."""

    def test_zero_markers_in_empty_html(self):
        assert scraper.count_markers("") == {
            "violation": 0,
            "order_107a": 0,
            "assessed": 0,
            "contested": 0,
        }

    def test_counts_each_marker_independently(self):
        html = (
            "<div>Violations</div>"
            "<div>Violation</div>"
            "<div>107(a)</div>"
            "<div>Assessed Violations</div>"  # double-counts: Violation + Assessed
            "<div>Contested Violations</div>"  # double-counts: Violation + Contested
        )
        counts = scraper.count_markers(html)
        assert counts["violation"] == 4
        assert counts["order_107a"] == 1
        assert counts["assessed"] == 1
        assert counts["contested"] == 1

    def test_does_not_match_substrings_in_unrelated_words(self):
        # "violations" lowercase still matches because the regex is
        # case-insensitive on word boundary, but "violator" should NOT
        # match — that's an MSHA-domain word that the assertion guards
        # against accidentally inflating the count.
        html = "violator violators violational"
        counts = scraper.count_markers(html)
        assert counts["violation"] == 0


class TestParseMineIds:
    """The CLI's mine-ID resolution path."""

    def test_dedupes_and_normalizes(self, tmp_path):
        path = tmp_path / "ids.txt"
        path.write_text(
            "# leading comment, ignored\n"
            "4609192\n"
            "46-09192\n"  # same as above after normalize
            "\n"  # blank line, ignored
            "0103354\n"
            "abcdefg\n",  # invalid, skipped with warning
            encoding="utf-8",
        )

        class Args:
            mine_ids: list[str] = []
            mine_ids_file = path

        ids = scraper._parse_mine_ids(Args())
        assert ids == ["4609192", "0103354"]

    def test_rejects_when_no_ids(self, tmp_path):
        class Args:
            mine_ids: list[str] = []
            mine_ids_file = None

        with pytest.raises(SystemExit, match="No mine IDs"):
            scraper._parse_mine_ids(Args())
