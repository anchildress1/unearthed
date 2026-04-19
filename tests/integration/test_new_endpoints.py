"""Integration tests for /h3-density and /emissions endpoints."""

from unittest.mock import MagicMock, patch

import pytest


class TestH3Density:
    @patch("app.main._get_connection")
    def test_h3_returns_cells(self, mock_conn, client):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "H3": "842a981ffffffff",
                "LAT": 37.5,
                "LNG": -82.6,
                "TOTAL": 100,
                "ACTIVE": 5,
                "ABANDONED": 95,
            },
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/h3-density?resolution=4")
        assert resp.status_code == 200
        data = resp.json()
        assert "cells" in data
        assert data["resolution"] == 4

    def test_h3_invalid_resolution_returns_400(self, client):
        resp = client.get("/h3-density?resolution=1")
        assert resp.status_code == 400

    def test_h3_high_resolution_returns_400(self, client):
        resp = client.get("/h3-density?resolution=8")
        assert resp.status_code == 400

    def test_h3_default_resolution(self, client):
        """Default resolution should be accepted (no query param)."""
        with patch("app.main._get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.cursor.return_value = mock_cursor
            resp = client.get("/h3-density")
        assert resp.status_code == 200
        assert resp.json()["resolution"] == 4

    @patch("app.main._get_connection")
    def test_h3_state_filter_scopes_query(self, mock_conn, client):
        """State param should filter SQL and echo the state in the response."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "H3": "852a981ffffffff",
                "LAT": 37.5,
                "LNG": -82.6,
                "TOTAL": 1,
                "ACTIVE": 1,
                "ABANDONED": 0,
            },
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/h3-density?resolution=5&state=wv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "wv"
        assert len(data["cells"]) == 1

        sql_arg, bind_arg = mock_cursor.execute.call_args[0]
        # Require the exact filter, not just "STATE appears somewhere" —
        # otherwise a stray column named STATE_TXT_OPERATOR would pass.
        assert "state_txt = %(state)s" in sql_arg
        assert "HAVING total >= 1" in sql_arg
        assert bind_arg == {"state": "WV"}

    def test_h3_invalid_state_returns_400(self, client):
        resp = client.get("/h3-density?state=Kentucky")
        assert resp.status_code == 400

    def test_h3_state_case_insensitive(self, client):
        """Mixed-case 2-letter codes should be accepted."""
        with patch("app.main._get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.cursor.return_value = mock_cursor
            resp = client.get("/h3-density?state=Wy")
        assert resp.status_code == 200
        assert resp.json()["state"] == "Wy"

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_returns_summary_on_success(self, mock_conn, mock_summary, client):
        """On success, the endpoint must surface summary + degraded=False."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "H3": "852a981ffffffff",
                "LAT": 37.5,
                "LNG": -82.6,
                "TOTAL": 500,
                "ACTIVE": 10,
                "ABANDONED": 490,
            },
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_summary.return_value = ("Mostly closed mines.", False)

        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Mostly closed mines."
        assert data["summary_degraded"] is False

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_surfaces_degraded_flag(self, mock_conn, mock_summary, client):
        """When the generator reports degraded=True, the endpoint must
        propagate it so the UI can hide the Cortex byline."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "H3": "852a981ffffffff",
                "LAT": 37.5,
                "LNG": -82.6,
                "TOTAL": 100,
                "ACTIVE": 5,
                "ABANDONED": 95,
            },
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
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
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "H3": "852a981ffffffff",
                "LAT": 37.5,
                "LNG": -82.6,
                "TOTAL": 10,
                "ACTIVE": 1,
                "ABANDONED": 9,
            },
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_summary.side_effect = RuntimeError("unexpected")

        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == ""
        assert data["summary_degraded"] is True

    @patch("app.main.generate_h3_summary")
    @patch("app.main._get_connection")
    def test_h3_summary_skipped_when_total_zero(self, mock_conn, mock_summary, client):
        """No mines in view → no summary request; the generator must not be
        called, the response surfaces empty summary + degraded=False."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == ""
        assert data["summary_degraded"] is False
        mock_summary.assert_not_called()

    @patch("app.main._get_connection")
    def test_h3_filters_non_us_coordinates(self, mock_conn, client):
        """The SQL should bound lat/lng to the US landmass.

        MSHA occasionally ships (0,0) null-island or stray ocean coordinates
        when a mine's address was never geocoded cleanly. Without the bounding
        box, a resolution-5 hex lands in the Atlantic and drags the viewport
        off the mainland — the whole point of filtering at the query layer.
        """
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor

        resp = client.get("/h3-density")
        assert resp.status_code == 200
        sql_arg, _ = mock_cursor.execute.call_args[0]
        assert "lat_num BETWEEN 24 AND 72" in sql_arg
        assert "lng_num BETWEEN -180 AND -65" in sql_arg


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
