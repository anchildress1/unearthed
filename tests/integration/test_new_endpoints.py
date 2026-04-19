"""Integration tests for /h3-density and /emissions endpoints."""

from unittest.mock import MagicMock, patch


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
        assert data["co2_tons"] == 1000.0

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
