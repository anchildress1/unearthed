"""Integration tests for /health, /h3-density, /emissions, and security headers."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_emissions_cache():
    """The endpoint cache is module-scoped; clear it between tests so a
    cached row from one test never satisfies another test's request."""
    from app.main import _emissions_cache

    _emissions_cache.clear()
    yield
    _emissions_cache.clear()


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_post_method_not_allowed(self, client):
        resp = client.post("/health")
        assert resp.status_code == 405


class TestSecurityHeaders:
    """Every response must carry the hardened headers added by the
    ``security_headers`` middleware in ``app/main.py``.
    """

    def test_csp_frame_ancestors(self, client):
        resp = client.get("/health")
        csp = resp.headers.get("Content-Security-Policy")
        assert csp == "frame-ancestors 'self' https://dev.to"

    def test_x_content_type_options(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy(self, client):
        resp = client.get("/health")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_headers_present_on_non_health_route(self, client):
        """Headers apply globally, not just to /health."""
        resp = client.get("/h3-density?resolution=1")  # 400 — still gets headers
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert "frame-ancestors" in resp.headers.get("Content-Security-Policy", "")


def _cells(n=1, total=100, active=5, abandoned=95):
    return [
        {
            "H3": "842a981ffffffff",
            "LAT": 37.5,
            "LNG": -82.6,
            "TOTAL": total,
            "ACTIVE": active,
            "ABANDONED": abandoned,
        }
    ] * n


def _totals(total=100, active=5, abandoned=95):
    return {"total": total, "active": active, "abandoned": abandoned}


class TestH3Density:
    @patch("app.main.query_h3_registry_totals", return_value=_totals())
    @patch("app.main.query_h3_density", return_value=_cells())
    def test_h3_returns_cells(self, mock_density, mock_totals, client):
        resp = client.get("/h3-density?resolution=4")
        assert resp.status_code == 200
        data = resp.json()
        assert "cells" in data
        assert data["resolution"] == 4
        assert data["totals"] == {"total": 100, "active": 5, "abandoned": 95}

    def test_h3_invalid_resolution_returns_400(self, client):
        resp = client.get("/h3-density?resolution=1")
        assert resp.status_code == 400

    def test_h3_high_resolution_returns_400(self, client):
        resp = client.get("/h3-density?resolution=8")
        assert resp.status_code == 400

    @patch("app.main.query_h3_registry_totals", return_value=_totals(0, 0, 0))
    @patch("app.main.query_h3_density", return_value=[])
    def test_h3_default_resolution(self, mock_density, mock_totals, client):
        """Default resolution should be accepted (no query param)."""
        resp = client.get("/h3-density")
        assert resp.status_code == 200
        assert resp.json()["resolution"] == 4

    @patch("app.main.query_h3_registry_totals", return_value=_totals(1, 1, 0))
    @patch("app.main.query_h3_density", return_value=_cells(1, 1, 1, 0))
    def test_h3_state_filter_passes_uppercased_state_to_data_client(
        self, mock_density, mock_totals, client
    ):
        """State param echoes in the response; data client receives the uppercased value."""
        resp = client.get("/h3-density?resolution=5&state=wv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "wv"  # response echoes original casing
        assert len(data["cells"]) == 1
        # Data client must receive uppercased state so SQL comparisons work.
        mock_density.assert_called_once_with(5, "WV")
        mock_totals.assert_called_once_with("WV")

    def test_h3_invalid_state_returns_400(self, client):
        resp = client.get("/h3-density?state=Kentucky")
        assert resp.status_code == 400

    @patch("app.main.query_h3_registry_totals", return_value=_totals(0, 0, 0))
    @patch("app.main.query_h3_density", return_value=[])
    def test_h3_state_case_insensitive(self, mock_density, mock_totals, client):
        """Mixed-case 2-letter codes should be accepted."""
        resp = client.get("/h3-density?state=Wy")
        assert resp.status_code == 200
        assert resp.json()["state"] == "Wy"

    @patch("app.main.generate_h3_summary", return_value=("Mostly closed mines.", False))
    @patch("app.main.query_h3_registry_totals", return_value=_totals(500, 10, 490))
    @patch("app.main.query_h3_density", return_value=_cells(1, 500, 10, 490))
    def test_h3_returns_summary_on_success(self, mock_density, mock_totals, mock_summary, client):
        """On success, the endpoint must surface summary + degraded=False."""
        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Mostly closed mines."
        assert data["summary_degraded"] is False
        # Generator receives registry totals and a non-empty role.
        kwargs = mock_summary.call_args.kwargs
        assert kwargs["total"] == 500
        assert kwargs["active"] == 10
        assert kwargs["abandoned"] == 490
        assert kwargs["role"]

    @patch("app.main.generate_h3_summary", return_value=("Template fallback.", True))
    @patch("app.main.query_h3_registry_totals", return_value=_totals(100, 5, 95))
    @patch("app.main.query_h3_density", return_value=_cells())
    def test_h3_surfaces_degraded_flag(self, mock_density, mock_totals, mock_summary, client):
        """When the generator reports degraded=True, the endpoint must propagate it."""
        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Template fallback."
        assert data["summary_degraded"] is True

    @patch("app.main.generate_h3_summary", side_effect=RuntimeError("unexpected"))
    @patch("app.main.query_h3_registry_totals", return_value=_totals(10, 1, 9))
    @patch("app.main.query_h3_density", return_value=_cells(1, 10, 1, 9))
    def test_h3_empty_summary_when_generator_crashes(
        self, mock_density, mock_totals, mock_summary, client
    ):
        """An unexpected generator exception must not fail the endpoint."""
        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == ""
        assert data["summary_degraded"] is True

    @patch("app.main.generate_h3_summary")
    @patch("app.main.query_h3_registry_totals", return_value=_totals(0, 0, 0))
    @patch("app.main.query_h3_density", return_value=[])
    def test_h3_summary_skipped_when_total_zero(
        self, mock_density, mock_totals, mock_summary, client
    ):
        """No mines in the registry → generator must not be called."""
        resp = client.get("/h3-density?resolution=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == ""
        assert data["summary_degraded"] is False
        assert data["totals"] == {"total": 0, "active": 0, "abandoned": 0}
        mock_summary.assert_not_called()

    @patch("app.main.query_h3_density", side_effect=RuntimeError("R2 unreachable"))
    def test_h3_data_layer_exception_returns_503(self, mock_density, client):
        resp = client.get("/h3-density?resolution=4")
        assert resp.status_code == 503

    @patch("app.main.generate_h3_summary", return_value=("Summary.", False))
    @patch("app.main.query_h3_registry_totals", return_value=_totals(1_000, 40, 960))
    @patch("app.main.query_h3_density", return_value=[])
    def test_h3_totals_independent_of_hex_filter(
        self, mock_density, mock_totals, mock_summary, client
    ):
        """Registry totals from query_h3_registry_totals must flow to the
        response and to generate_h3_summary — not be derived by summing the
        (empty) cell list. If clustering drops all hexes, the summary still
        reads from the authoritative registry count."""
        resp = client.get("/h3-density?resolution=5&state=wv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cells"] == []
        assert data["totals"] == {"total": 1_000, "active": 40, "abandoned": 960}
        kwargs = mock_summary.call_args.kwargs
        assert kwargs["total"] == 1_000

    @patch("app.main.query_h3_registry_totals", return_value=_totals(0, 0, 0))
    @patch("app.main.query_h3_density", return_value=[])
    def test_h3_calls_data_client_with_resolution(self, mock_density, mock_totals, client):
        """Endpoint must forward the resolution parameter to the data client."""
        client.get("/h3-density?resolution=6")
        mock_density.assert_called_once_with(6, None)


class TestEmissions:
    """The endpoint now reads through ``app.data_client.query_emissions_for_plant``;
    Snowflake is no longer in the path. Patch the import the endpoint uses
    (``app.main.query_emissions_for_plant``) so the stub stands in for the
    DuckDB read against the parquet file."""

    @patch("app.main.query_emissions_for_plant")
    def test_emissions_returns_data(self, mock_query, client):
        mock_query.return_value = {"co2_tons": 1000.0, "so2_tons": 50.0, "nox_tons": 30.0}

        resp = client.get("/emissions/Cross")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plant"] == "Cross"
        assert data["co2_tons"] == pytest.approx(1000.0)

    @patch("app.main.query_emissions_for_plant")
    def test_emissions_no_data_returns_nulls(self, mock_query, client):
        mock_query.return_value = None

        resp = client.get("/emissions/NonexistentPlant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["co2_tons"] is None

    @patch("app.main.query_emissions_for_plant")
    def test_emissions_get_method(self, mock_query, client):
        """Emissions endpoint accepts GET."""
        mock_query.return_value = None
        resp = client.get("/emissions/Test")
        assert resp.status_code == 200

    @patch("app.main.query_emissions_for_plant")
    def test_data_layer_exception_returns_503(self, mock_query, client):
        """A DuckDB / R2 failure surfaces as 503 — same contract as the old
        Snowflake-down branch, just a different upstream."""
        mock_query.side_effect = RuntimeError("R2 unreachable")
        resp = client.get("/emissions/Cross")
        assert resp.status_code == 503


class TestEmissionsCache:
    def test_cache_hit_skips_db(self, client):
        from app.main import _emissions_cache

        _emissions_cache["CROSS"] = {
            "plant": "Cross",
            "co2_tons": 999.0,
            "so2_tons": 1.0,
            "nox_tons": 2.0,
        }
        # The data layer must not be called on a hit. Patching with a
        # side_effect that fails the test if invoked is the strongest
        # assertion here — beats checking call_count after the fact.
        with patch("app.main.query_emissions_for_plant") as mock_query:
            mock_query.side_effect = AssertionError("data layer hit on cached request")
            resp = client.get("/emissions/Cross")
        assert resp.status_code == 200
        assert resp.json()["co2_tons"] == pytest.approx(999.0)

    def test_cache_key_case_insensitive(self, client):
        from app.main import _emissions_cache

        _emissions_cache["MITCHELL"] = {
            "plant": "Mitchell",
            "co2_tons": 500.0,
            "so2_tons": 10.0,
            "nox_tons": 5.0,
        }
        with patch("app.main.query_emissions_for_plant") as mock_query:
            mock_query.side_effect = AssertionError("data layer hit on cached request")
            resp = client.get("/emissions/mitchell")
        assert resp.status_code == 200
        assert resp.json()["co2_tons"] == pytest.approx(500.0)

    @patch("app.main.query_emissions_for_plant")
    def test_cache_populated_on_miss(self, mock_query, client):
        from app.main import _emissions_cache

        mock_query.return_value = {"co2_tons": 42.0, "so2_tons": 1.0, "nox_tons": 1.0}

        client.get("/emissions/NewPlant")
        assert "NEWPLANT" in _emissions_cache
        assert _emissions_cache["NEWPLANT"]["co2_tons"] == pytest.approx(42.0)

    @patch("app.main.query_emissions_for_plant")
    def test_data_client_receives_raw_plant_name(self, mock_query, client):
        """Normalization (parenthetical strip, upper) is the data client's job —
        the endpoint passes through the user-facing plant string. The endpoint
        cache key still derives from the normalized form so cache hits and
        DB hits land at the same row."""
        mock_query.return_value = None

        client.get("/emissions/Cumberland (TN)")
        assert mock_query.call_args[0][0] == "Cumberland (TN)"

        from app.main import _emissions_cache

        # Cache key collapses to the normalized form even on a miss-with-null
        # so subsequent lowercase variants still hit cache.
        # (Cache only populates on success, so we just verify the request landed
        # on the expected normalized cache lookup path by sending a cached entry.)
        _emissions_cache["CUMBERLAND"] = {
            "plant": "Cumberland",
            "co2_tons": 1.0,
            "so2_tons": 0.0,
            "nox_tons": 0.0,
        }
        with patch("app.main.query_emissions_for_plant") as inner:
            inner.side_effect = AssertionError("normalized cache key did not match")
            resp = client.get("/emissions/cumberland (tn)")
        assert resp.status_code == 200

    @patch("app.main.query_emissions_for_plant")
    def test_cache_bounded(self, mock_query, client):
        """Cache evicts the oldest entry when it exceeds _CACHE_MAXSIZE."""
        from app.main import _CACHE_MAXSIZE, _emissions_cache

        mock_query.return_value = {"co2_tons": 1.0, "so2_tons": 0.0, "nox_tons": 0.0}

        for i in range(_CACHE_MAXSIZE + 1):
            client.get(f"/emissions/PLANT{i}")
        assert len(_emissions_cache) == _CACHE_MAXSIZE
        assert "PLANT0" not in _emissions_cache
        assert f"PLANT{_CACHE_MAXSIZE}" in _emissions_cache
