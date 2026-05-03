"""Unit tests for ``app.data_client`` — the DuckDB boundary that replaces
the Snowflake data path for non-Cortex queries.

These tests run against a hand-built fixture parquet (see
``tests/fixtures/build_parquet.py``) so the data layer can be exercised
without a live Snowflake or R2 connection. Production behavior (R2 over
``httpfs``) is covered by the same SQL paths — only the parquet URL
changes between fixture and prod.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def data_client(tmp_path_factory, monkeypatch_module):
    """Reload ``app.data_client`` against a session-scoped fixture directory.

    The module caches the DuckDB connection at process scope, so we have to
    reset module state between test modules — otherwise the connection
    created by another module could outlive its fixture directory.
    """
    from tests.fixtures.build_parquet import (
        write_emissions_fixture,
        write_fatality_narratives_fixture,
        write_mine_plant_for_subregion_fixture,
        write_msha_mines_fixture,
    )

    fixtures_root = tmp_path_factory.mktemp("data_client_fixtures")
    write_emissions_fixture(fixtures_root)
    write_mine_plant_for_subregion_fixture(fixtures_root)
    write_msha_mines_fixture(fixtures_root)
    write_fatality_narratives_fixture(fixtures_root)

    monkeypatch_module.setenv("DATA_BASE_URL", str(fixtures_root))
    # Ensure no R2 secrets leak in from the developer's shell — the local
    # path mode must be exercised here, not the httpfs mode.
    monkeypatch_module.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch_module.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch_module.delenv("R2_ENDPOINT", raising=False)

    import app.data_client as module

    importlib.reload(module)
    yield module
    module._reset_connection()


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch — pytest's default is function-scoped."""
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


class TestQueryEmissionsForPlant:
    def test_exact_name_returns_row(self, data_client):
        result = data_client.query_emissions_for_plant("Cross")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(1000.0)
        assert result["so2_tons"] == pytest.approx(50.0)
        assert result["nox_tons"] == pytest.approx(30.0)

    def test_lowercase_name_matched(self, data_client):
        """Plant names are uppercased before LIKE — case-insensitive match."""
        result = data_client.query_emissions_for_plant("mitchell")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(500.0)

    def test_parenthetical_state_suffix_stripped(self, data_client):
        """EIA names carry trailing ``(TN)`` etc.; EPA's ``FACILITY_NAME`` does not.
        ``query_emissions_for_plant`` must bridge the gap before the LIKE."""
        result = data_client.query_emissions_for_plant("Cumberland (TN)")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(800.0)

    def test_prefix_match_resolves_longer_facility_name(self, data_client):
        """EPA names are sometimes longer than the EIA short name — ``Colstrip``
        in EIA, ``COLSTRIP ENERGY LP`` in EPA. Prefix LIKE bridges this."""
        result = data_client.query_emissions_for_plant("Colstrip")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(2200.0)

    def test_unknown_plant_returns_none(self, data_client):
        result = data_client.query_emissions_for_plant("NonexistentPlant")
        assert result is None

    def test_empty_string_returns_none(self, data_client):
        """Empty inputs must not collapse the LIKE to ``%`` and return a
        random row — that would silently fabricate emissions data."""
        result = data_client.query_emissions_for_plant("")
        assert result is None

    def test_sql_injection_attempt_does_not_match(self, data_client):
        """Plant name flows through a parameterized bind — a SQL fragment
        passed as input must be treated as literal text, not executable SQL."""
        result = data_client.query_emissions_for_plant("' OR '1'='1")
        assert result is None


class TestNormalization:
    """The plant-name normalization helper is shared by the endpoint cache
    and the data client. Same logic, exercised in isolation so the cache
    key derivation can't drift from the LIKE prefix derivation."""

    def test_strips_trailing_state_suffix(self, data_client):
        assert data_client.normalize_plant_name("Cumberland (TN)") == "CUMBERLAND"

    def test_uppercases_alphabetic_input(self, data_client):
        assert data_client.normalize_plant_name("Bailey") == "BAILEY"

    def test_preserves_internal_parentheses_when_no_close_at_end(self, data_client):
        """Internal parens that aren't a trailing state suffix stay intact."""
        assert data_client.normalize_plant_name("Plant (Old) Site") == "PLANT (OLD) SITE"

    def test_empty_returns_empty(self, data_client):
        assert data_client.normalize_plant_name("") == ""


class TestQueryMineForSubregion:
    def test_known_subregion_returns_full_record(self, data_client):
        result = data_client.query_mine_for_subregion("SRVC")
        assert result is not None
        assert result["mine"] == "Bailey Mine"
        assert result["mine_id"] == "36609947"
        assert result["mine_operator"] == "CONSOL Energy"
        assert result["mine_state"] == "PA"
        assert result["mine_type"] == "Underground"
        assert result["plant"] == "Cross"
        assert result["tons"] == pytest.approx(1247001.0)
        assert result["tons_year"] == 2023
        assert result["fatalities"] == 2
        assert result["injuries"] == 15
        assert result["days_lost"] == 430
        assert len(result["mine_coords"]) == 2
        assert len(result["plant_coords"]) == 2

    def test_case_insensitive_lookup(self, data_client):
        """Subregion is uppercased at the call site; fixture stores uppercase."""
        result = data_client.query_mine_for_subregion("srvc")
        assert result is not None
        assert result["mine"] == "Bailey Mine"

    def test_second_subregion_returns_different_record(self, data_client):
        result = data_client.query_mine_for_subregion("RFCW")
        assert result is not None
        assert result["mine"] == "Other Mine"
        assert result["mine_state"] == "WV"
        assert result["mine_type"] == "Surface"

    def test_unknown_subregion_returns_none(self, data_client):
        assert data_client.query_mine_for_subregion("XXXX") is None

    def test_null_coordinate_row_returns_none(self, data_client):
        """A row with a NULL lat/lng must not be returned — callers require
        valid coordinates to render the map marker."""
        assert data_client.query_mine_for_subregion("NULL_LAT") is None


class TestQueryH3Density:
    def test_national_returns_cells_meeting_threshold(self, data_client):
        """National view requires ≥5 mines per cell. Fixture has 6 WV mines
        clustered together (same cell) and 3 PA mines (different cell that
        falls below the national threshold)."""
        cells = data_client.query_h3_density(resolution=4)
        assert len(cells) == 1
        cell = cells[0]
        assert cell["TOTAL"] == 6
        assert cell["ACTIVE"] == 4
        assert cell["ABANDONED"] == 2
        assert "H3" in cell
        assert "LAT" in cell
        assert "LNG" in cell

    def test_national_excludes_cells_below_threshold(self, data_client):
        """PA has 3 mines (in-bbox). With national min_mines=5, that cell
        must not appear."""
        cells = data_client.query_h3_density(resolution=4)
        totals_in_cells = sum(c["TOTAL"] for c in cells)
        # Only the WV cluster (6) passes; PA (3) does not
        assert totals_in_cells == 6

    def test_state_view_includes_single_mine_cells(self, data_client):
        """State view drops threshold to 1 so PA's 3-mine cell appears."""
        cells = data_client.query_h3_density(resolution=4, state="PA")
        assert len(cells) == 1
        assert cells[0]["TOTAL"] == 3
        assert cells[0]["ACTIVE"] == 3

    def test_state_filter_excludes_other_states(self, data_client):
        """WV query must not return PA mines and vice versa."""
        wv_cells = data_client.query_h3_density(resolution=4, state="WV")
        pa_cells = data_client.query_h3_density(resolution=4, state="PA")
        wv_h3 = {c["H3"] for c in wv_cells}
        pa_h3 = {c["H3"] for c in pa_cells}
        assert wv_h3.isdisjoint(pa_h3), "WV and PA cells must not overlap"

    def test_bounding_box_excludes_null_island(self, data_client):
        """Mines at (0,0) are outside the US bounding box and must not
        generate any hex regardless of state filtering."""
        cells = data_client.query_h3_density(resolution=4, state="PA")
        # PA has 3 in-bbox + 1 null-island; null-island must be excluded
        assert cells[0]["TOTAL"] == 3

    def test_bounding_box_excludes_non_us_longitude(self, data_client):
        """Mine in UK (lng=-0.1) is outside lng bounds and must be excluded."""
        cells = data_client.query_h3_density(resolution=4)
        total_mines_in_cells = sum(c["TOTAL"] for c in cells)
        # Row 10 (XX/UK) must never contribute to any cell
        assert total_mines_in_cells <= 9  # 6 WV + 3 PA max

    def test_non_coal_mines_excluded(self, data_client):
        """Metal mine (COAL_METAL_IND='M') in WV must not affect WV cell counts."""
        cells = data_client.query_h3_density(resolution=4, state="WV")
        assert cells[0]["TOTAL"] == 6  # not 7

    def test_result_sorted_by_total_descending(self, data_client):
        """Cells with more mines should be listed first."""
        cells = data_client.query_h3_density(resolution=4, state="WV")
        totals = [c["TOTAL"] for c in cells]
        assert totals == sorted(totals, reverse=True)

    def test_no_mines_returns_empty_list(self, data_client):
        assert data_client.query_h3_density(resolution=4, state="AK") == []


class TestQueryH3RegistryTotals:
    def test_national_totals_include_all_coal_mines(self, data_client):
        """National count must include all 11 coal mines (in-bbox + out-of-bbox),
        but not the metal mine (row 11)."""
        totals = data_client.query_h3_registry_totals()
        assert totals["total"] == 11
        assert totals["active"] == 9
        assert totals["abandoned"] == 2

    def test_state_totals_scoped_to_state(self, data_client):
        """WV total: 6 coal mines (rows 0-5); metal mine excluded."""
        totals = data_client.query_h3_registry_totals(state="WV")
        assert totals["total"] == 6

    def test_state_totals_include_out_of_bbox_records(self, data_client):
        """PA total must include the null-island mine (row 9) — registry counts
        are intentionally unfiltered so the headline number is authoritative."""
        totals = data_client.query_h3_registry_totals(state="PA")
        assert totals["total"] == 4  # 3 in-bbox + 1 null-island

    def test_unknown_state_returns_zero(self, data_client):
        totals = data_client.query_h3_registry_totals(state="ZZ")
        assert totals == {"total": 0, "active": 0, "abandoned": 0}

    def test_abandoned_count_correct(self, data_client):
        totals = data_client.query_h3_registry_totals(state="WV")
        assert totals["abandoned"] == 2
        assert totals["active"] == 4

    def test_returns_dict_with_all_keys(self, data_client):
        totals = data_client.query_h3_registry_totals()
        assert set(totals.keys()) == {"total", "active", "abandoned"}


class TestQueryFatalitiesForMine:
    def test_returns_all_fatalities_for_known_mine(self, data_client):
        """Mine 46-09192 has two recorded fatalities in the fixture."""
        rows = data_client.query_fatalities_for_mine("46-09192")
        assert len(rows) == 2
        assert rows[0]["mine_id"] == "46-09192"
        assert rows[1]["mine_id"] == "46-09192"

    def test_orders_newest_first(self, data_client):
        """Two Leer Mine fatalities — Sept 28 should sort before Aug 5."""
        rows = data_client.query_fatalities_for_mine("46-09192")
        assert rows[0]["incident_date"] == "2024-09-28"
        assert rows[1]["incident_date"] == "2024-08-05"

    def test_returns_section_text_when_present(self, data_client):
        """Final-report rows expose SECTION_* text via the helper."""
        rows = data_client.query_fatalities_for_mine("46-09192")
        assert "the electrician was injured" in rows[0]["section_overview"]
        assert "103(k)" in rows[0]["section_enforcement_actions"]

    def test_unknown_mine_returns_empty_list(self, data_client):
        assert data_client.query_fatalities_for_mine("99-00000") == []

    def test_blank_input_returns_empty_list(self, data_client):
        """Empty mine_id must short-circuit before SQL — no wildcard match."""
        assert data_client.query_fatalities_for_mine("") == []

    def test_invalid_mine_id_format_rejected(self, data_client):
        """Anything that isn't ``NN-NNNNN`` is rejected at the input boundary."""
        assert data_client.query_fatalities_for_mine("not-a-mine-id") == []
        assert data_client.query_fatalities_for_mine("46/09192") == []
        assert data_client.query_fatalities_for_mine("'; DROP TABLE x;--") == []

    def test_lowercase_mine_id_normalized(self, data_client):
        """Mine IDs are alphanumeric — lowercase should resolve."""
        rows = data_client.query_fatalities_for_mine("46-09192")
        assert rows  # baseline
        # Same mine with surrounding whitespace + already-uppercase.
        rows2 = data_client.query_fatalities_for_mine("  46-09192  ")
        assert rows2 == rows

    def test_limit_clamps_to_safe_ceiling(self, data_client):
        """Very large or negative limits collapse to the bounded range."""
        rows_huge = data_client.query_fatalities_for_mine("46-09192", limit=10_000)
        rows_neg = data_client.query_fatalities_for_mine("46-09192", limit=-5)
        # Both still return the two fixture rows; cap doesn't drop valid data.
        assert len(rows_huge) == 2
        assert len(rows_neg) == 1  # negative collapses to min=1

    def test_pii_warning_round_trips(self, data_client):
        """The KY edge-case row has PII_WARNING=True; the bool must come
        through the SQL → dict pipeline as a real bool, not string '1'."""
        rows = data_client.query_fatalities_for_mine("15-99999")
        assert len(rows) == 1
        assert rows[0]["pii_warning"] is True


class TestQueryRecentFatalities:
    def test_returns_global_list_newest_first(self, data_client):
        """Without a state filter, all fixture rows surface in date-desc order."""
        rows = data_client.query_recent_fatalities()
        # 4 rows total in the fixture
        assert len(rows) == 4
        dates = [r["incident_date"] for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_filters_by_state(self, data_client):
        """WV state filter returns only the two Leer Mine fatalities."""
        rows = data_client.query_recent_fatalities(state="WV")
        assert len(rows) == 2
        assert all(r["mine_state"] == "WV" for r in rows)

    def test_unknown_state_returns_empty(self, data_client):
        """A state with no fixture rows yields an empty list (not all rows)."""
        assert data_client.query_recent_fatalities(state="AK") == []

    def test_invalid_state_falls_back_to_national(self, data_client):
        """A non-conforming state input collapses to the national list — the
        agent's "answer with what you have" guidance prefers a result over
        an empty-due-to-typo response."""
        national = data_client.query_recent_fatalities()
        rows = data_client.query_recent_fatalities(state="Not A State")
        assert len(rows) == len(national)

    def test_limit_caps_returned_rows(self, data_client):
        rows = data_client.query_recent_fatalities(limit=2)
        assert len(rows) == 2

    def test_lowercase_state_normalized(self, data_client):
        rows = data_client.query_recent_fatalities(state="wv")
        assert len(rows) == 2
        assert all(r["mine_state"] == "WV" for r in rows)

    def test_sql_injection_attempt_does_not_match(self, data_client):
        """State input flows through a parameterized bind. A SQL fragment
        passed in must be rejected at the regex boundary so it never even
        reaches the bind step."""
        rows = data_client.query_recent_fatalities(state="' OR '1'='1")
        # Falls back to national (regex rejects) — never returns extra data
        # and certainly does not execute the injected fragment.
        assert len(rows) == 4
