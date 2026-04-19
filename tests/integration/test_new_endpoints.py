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


class TestH3DensityCache:
    def test_cache_hit_skips_db(self, client):
        from app.main import _h3_cache

        _h3_cache[4] = [{"H3": "cached", "LAT": 0, "LNG": 0, "TOTAL": 1}]
        try:
            resp = client.get("/h3-density?resolution=4")
            assert resp.status_code == 200
            assert resp.json()["cells"][0]["H3"] == "cached"
        finally:
            _h3_cache.pop(4, None)

    @patch("app.main._get_connection")
    def test_cache_populated_on_miss(self, mock_conn, client):
        from app.main import _h3_cache

        _h3_cache.pop(5, None)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"H3": "fresh", "LAT": 1, "LNG": 1, "TOTAL": 10, "ACTIVE": 5, "ABANDONED": 5}
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        client.get("/h3-density?resolution=5")
        assert 5 in _h3_cache
        assert _h3_cache[5][0]["H3"] == "fresh"
        _h3_cache.pop(5, None)

    def test_resolutions_cached_independently(self, client):
        from app.main import _h3_cache

        _h3_cache[3] = [{"H3": "res3"}]
        _h3_cache[6] = [{"H3": "res6"}]
        try:
            resp3 = client.get("/h3-density?resolution=3")
            resp6 = client.get("/h3-density?resolution=6")
            assert resp3.json()["cells"][0]["H3"] == "res3"
            assert resp6.json()["cells"][0]["H3"] == "res6"
        finally:
            _h3_cache.pop(3, None)
            _h3_cache.pop(6, None)


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
