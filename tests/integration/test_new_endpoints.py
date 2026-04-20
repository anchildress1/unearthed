"""Integration tests for /h3-density and /emissions endpoints."""

from unittest.mock import MagicMock, patch

import pytest


def _h3_cursor(cells=None, totals=None):
    """Build a mock cursor that returns hex cells on the first ``execute``
    (density query, ``fetchall``) and a totals row on the second (registry
    query, ``fetchone``). Totals default to non-zero so the summary
    generator is exercised unless a test explicitly zeros them out.
    """
    cursor = MagicMock()
    cursor.fetchall.return_value = cells if cells is not None else []
    cursor.fetchone.return_value = (
        totals if totals is not None else {"TOTAL": 100, "ACTIVE": 5, "ABANDONED": 95}
    )
    return cursor


class TestH3Density:
    @patch("app.main._get_connection")
    def test_h3_returns_cells(self, mock_conn, client):
        mock_cursor = _h3_cursor(
            cells=[
                {
                    "H3": "842a981ffffffff",
                    "LAT": 37.5,
                    "LNG": -82.6,
                    "TOTAL": 100,
                    "ACTIVE": 5,
                    "ABANDONED": 95,
                },
            ],
        )
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/h3-density?resolution=4")
        assert resp.status_code == 200
        data = resp.json()
        assert "cells" in data
        assert data["resolution"] == 4
        # Registry totals surface as a separate payload so the frontend can
        # label "X mines on record" honestly — independent of hex filtering.
        assert data["totals"] == {"total": 100, "active": 5, "abandoned": 95}

    def test_h3_invalid_resolution_returns_400(self, client):
        resp = client.get("/h3-density?resolution=1")
        assert resp.status_code == 400

    def test_h3_high_resolution_returns_400(self, client):
        resp = client.get("/h3-density?resolution=8")
        assert resp.status_code == 400

    def test_h3_default_resolution(self, client):
        """Default resolution should be accepted (no query param)."""
        with patch("app.main._get_connection") as mock_conn:
            mock_conn.return_value.cursor.return_value = _h3_cursor(
                totals={"TOTAL": 0, "ACTIVE": 0, "ABANDONED": 0}
            )
            resp = client.get("/h3-density")
        assert resp.status_code == 200
        assert resp.json()["resolution"] == 4

    @patch("app.main._get_connection")
    def test_h3_state_filter_scopes_query(self, mock_conn, client):
        """State param should filter SQL and echo the state in the response."""
        mock_cursor = _h3_cursor(
            cells=[
                {
                    "H3": "852a981ffffffff",
                    "LAT": 37.5,
                    "LNG": -82.6,
                    "TOTAL": 1,
                    "ACTIVE": 1,
                    "ABANDONED": 0,
                },
            ],
            totals={"TOTAL": 1, "ACTIVE": 1, "ABANDONED": 0},
        )
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/h3-density?resolution=5&state=wv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "wv"
        assert len(data["cells"]) == 1

        # First execute = density query; second = registry totals.
        density_sql, density_bind = mock_cursor.execute.call_args_list[0][0]
        totals_sql, totals_bind = mock_cursor.execute.call_args_list[1][0]
        # Require the exact filter, not just "STATE appears somewhere" —
        # otherwise a stray column named STATE_TXT_OPERATOR would pass.
        assert "STATE = %(state)s" in density_sql
        assert "HAVING total >= 1" in density_sql
        assert density_bind == {"resolution": 5, "state": "WV"}
        # The registry-totals query must scope to the same state but must
        # NOT re-apply the bounding box / HAVING filters — those drop rows
        # the headline count should still include.
        assert "STATE = %(state)s" in totals_sql
        assert "LATITUDE BETWEEN" not in totals_sql
        assert "HAVING" not in totals_sql
        assert totals_bind == {"resolution": 5, "state": "WV"}

    def test_h3_invalid_state_returns_400(self, client):
        resp = client.get("/h3-density?state=Kentucky")
        assert resp.status_code == 400

    def test_h3_state_case_insensitive(self, client):
        """Mixed-case 2-letter codes should be accepted."""
        with patch("app.main._get_connection") as mock_conn:
            mock_conn.return_value.cursor.return_value = _h3_cursor(
                totals={"TOTAL": 0, "ACTIVE": 0, "ABANDONED": 0}
            )
            resp = client.get("/h3-density?state=Wy")
        assert resp.status_code == 200
        assert resp.json()["state"] == "Wy"

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_returns_summary_on_success(self, mock_conn, mock_summary, client):
        """On success, the endpoint must surface summary + degraded=False."""
        mock_conn.return_value.cursor.return_value = _h3_cursor(
            cells=[
                {
                    "H3": "852a981ffffffff",
                    "LAT": 37.5,
                    "LNG": -82.6,
                    "TOTAL": 500,
                    "ACTIVE": 10,
                    "ABANDONED": 490,
                },
            ],
            totals={"TOTAL": 500, "ACTIVE": 10, "ABANDONED": 490},
        )
        mock_summary.return_value = ("Mostly closed mines.", False)

        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Mostly closed mines."
        assert data["summary_degraded"] is False
        # The generator must see the registry totals (not the filtered hex
        # sum) and a role scoped to the public readonly endpoint.
        kwargs = mock_summary.call_args.kwargs
        assert kwargs["total"] == 500
        assert kwargs["active"] == 10
        assert kwargs["abandoned"] == 490
        assert kwargs["role"]  # truthy — populated from settings.snowflake_readonly_role

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_surfaces_degraded_flag(self, mock_conn, mock_summary, client):
        """When the generator reports degraded=True, the endpoint must
        propagate it so the UI can hide the Cortex byline."""
        mock_conn.return_value.cursor.return_value = _h3_cursor(
            cells=[
                {
                    "H3": "852a981ffffffff",
                    "LAT": 37.5,
                    "LNG": -82.6,
                    "TOTAL": 100,
                    "ACTIVE": 5,
                    "ABANDONED": 95,
                },
            ],
            totals={"TOTAL": 100, "ACTIVE": 5, "ABANDONED": 95},
        )
        mock_summary.return_value = ("Template fallback.", True)

        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Template fallback."
        assert data["summary_degraded"] is True

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_empty_summary_when_generator_crashes(self, mock_conn, mock_summary, client):
        """An unexpected generator exception must not fail the endpoint —
        the map still renders, the byline just goes empty + degraded."""
        mock_conn.return_value.cursor.return_value = _h3_cursor(
            cells=[
                {
                    "H3": "852a981ffffffff",
                    "LAT": 37.5,
                    "LNG": -82.6,
                    "TOTAL": 10,
                    "ACTIVE": 1,
                    "ABANDONED": 9,
                },
            ],
            totals={"TOTAL": 10, "ACTIVE": 1, "ABANDONED": 9},
        )
        mock_summary.side_effect = RuntimeError("unexpected")

        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == ""
        assert data["summary_degraded"] is True

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_summary_skipped_when_total_zero(self, mock_conn, mock_summary, client):
        """No mines in the registry → no summary request; the generator must
        not be called, the response surfaces empty summary + degraded=False."""
        mock_conn.return_value.cursor.return_value = _h3_cursor(
            cells=[],
            totals={"TOTAL": 0, "ACTIVE": 0, "ABANDONED": 0},
        )

        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == ""
        assert data["summary_degraded"] is False
        assert data["totals"] == {"total": 0, "active": 0, "abandoned": 0}
        mock_summary.assert_not_called()

    @patch("app.main._get_connection")
    def test_h3_filters_non_us_coordinates(self, mock_conn, client):
        """The density SQL should bound lat/lng to the US landmass.

        MSHA occasionally ships (0,0) null-island or stray ocean coordinates
        when a mine's address was never geocoded cleanly. Without the bounding
        box, a resolution-5 hex lands in the Atlantic and drags the viewport
        off the mainland — the whole point of filtering at the query layer.

        The registry-totals query does NOT apply this filter because "N mines
        on record" has to include rows even when their coordinates are
        missing or wrong.
        """
        mock_cursor = _h3_cursor(totals={"TOTAL": 0, "ACTIVE": 0, "ABANDONED": 0})
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/h3-density")
        assert resp.status_code == 200
        density_sql, _ = mock_cursor.execute.call_args_list[0][0]
        totals_sql, _ = mock_cursor.execute.call_args_list[1][0]
        assert "LATITUDE BETWEEN 24 AND 72" in density_sql
        assert "LONGITUDE BETWEEN -180 AND -65" in density_sql
        assert "LATITUDE BETWEEN" not in totals_sql

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_totals_independent_of_hex_filter(self, mock_conn, mock_summary, client):
        """Registry totals must come from the unfiltered count query, not
        from summing the hex cells. If the density query drops small clusters
        (HAVING) but the state has 1,000 coal mines on record, the summary
        must read "1,000 on record," not "0 because no hex crossed 5 mines."
        """
        mock_conn.return_value.cursor.return_value = _h3_cursor(
            cells=[],  # no hexes survived clustering
            totals={"TOTAL": 1_000, "ACTIVE": 40, "ABANDONED": 960},
        )
        mock_summary.return_value = ("Summary.", False)

        resp = client.get("/h3-density?resolution=5&state=wv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cells"] == []
        assert data["totals"] == {"total": 1_000, "active": 40, "abandoned": 960}
        # Generator receives the real registry counts, not the empty hex sum.
        kwargs = mock_summary.call_args.kwargs
        assert kwargs["total"] == 1_000


class TestEmissions:
    @patch("app.main._get_connection")
    def test_emissions_returns_data(self, mock_conn, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"CO2_TONS": 1000.0, "SO2_TONS": 50.0, "NOX_TONS": 30.0}
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/emissions/Cross")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plant"] == "Cross"
        assert data["co2_tons"] == pytest.approx(1000.0)

    @patch("app.main._get_connection")
    def test_emissions_no_data_returns_nulls(self, mock_conn, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/emissions/NonexistentPlant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["co2_tons"] is None

    def test_emissions_get_method(self, client):
        """Emissions endpoint accepts GET."""
        with patch("app.main._get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.cursor.return_value = mock_cursor
            resp = client.get("/emissions/Test")
        assert resp.status_code == 200


class TestEmissionsCache:
    def test_cache_hit_skips_db(self, client):
        from app.main import _emissions_cache

        _emissions_cache["CROSS"] = {
            "plant": "Cross",
            "co2_tons": 999.0,
            "so2_tons": 1.0,
            "nox_tons": 2.0,
        }
        try:
            resp = client.get("/emissions/Cross")
            assert resp.status_code == 200
            assert resp.json()["co2_tons"] == pytest.approx(999.0)
        finally:
            _emissions_cache.pop("CROSS", None)

    def test_cache_key_case_insensitive(self, client):
        from app.main import _emissions_cache

        _emissions_cache["MITCHELL"] = {
            "plant": "Mitchell",
            "co2_tons": 500.0,
            "so2_tons": 10.0,
            "nox_tons": 5.0,
        }
        try:
            resp = client.get("/emissions/mitchell")
            assert resp.status_code == 200
            assert resp.json()["co2_tons"] == pytest.approx(500.0)
        finally:
            _emissions_cache.pop("MITCHELL", None)

    @patch("app.main._get_connection")
    def test_cache_populated_on_miss(self, mock_conn, client):
        from app.main import _emissions_cache

        _emissions_cache.pop("NEWPLANT", None)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"CO2_TONS": 42.0, "SO2_TONS": 1.0, "NOX_TONS": 1.0}
        mock_conn.return_value.cursor.return_value = mock_cursor

        client.get("/emissions/NewPlant")
        assert "NEWPLANT" in _emissions_cache
        assert _emissions_cache["NEWPLANT"]["co2_tons"] == pytest.approx(42.0)
        _emissions_cache.pop("NEWPLANT", None)

    @patch("app.main._get_connection")
    def test_bind_param_uppercased(self, mock_conn, client):
        """Plant name is uppercased before binding so the SQL needs no UPPER() on the column."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cursor

        client.get("/emissions/Mitchell")
        bind = mock_cursor.execute.call_args[0][1]
        assert bind["plant_name"] == "MITCHELL"

    @patch("app.main._get_connection")
    def test_cache_bounded(self, mock_conn, client):
        """Cache evicts the oldest entry when it exceeds _CACHE_MAXSIZE."""
        from app.main import _CACHE_MAXSIZE, _emissions_cache

        _emissions_cache.clear()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"CO2_TONS": 1.0, "SO2_TONS": 0, "NOX_TONS": 0}
        mock_conn.return_value.cursor.return_value = mock_cursor

        try:
            for i in range(_CACHE_MAXSIZE + 1):
                client.get(f"/emissions/PLANT{i}")
            assert len(_emissions_cache) == _CACHE_MAXSIZE
            assert "PLANT0" not in _emissions_cache
            assert f"PLANT{_CACHE_MAXSIZE}" in _emissions_cache
        finally:
            _emissions_cache.clear()
