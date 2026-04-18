"""Integration tests for POST /mine-for-me endpoint."""

from unittest.mock import patch

from tests.conftest import SAMPLE_MINE_DATA


class TestMineForMeEndpoint:
    """Tests with mocked Snowflake and Gemini."""

    @patch("app.main.generate_prose", return_value=("Grief prose.", False))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_success_returns_full_payload(self, mock_sf, mock_gemini, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mine"] == "Bailey Mine"
        assert data["plant"] == "Cross"
        assert data["tons"] == 1247001.0
        assert data["prose"] == "Grief prose."
        assert data["subregion_id"] == "SRVC"
        assert data["degraded"] is False

    @patch("app.main.generate_prose", return_value=("Grief prose.", False))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_response_contains_all_required_fields(self, mock_sf, mock_gemini, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        data = resp.json()
        required = [
            "mine",
            "mine_operator",
            "mine_county",
            "mine_state",
            "mine_type",
            "mine_coords",
            "plant",
            "plant_operator",
            "plant_coords",
            "tons",
            "tons_year",
            "prose",
            "subregion_id",
            "degraded",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    @patch("app.main.generate_prose", return_value=("Grief prose.", False))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_coords_are_lat_lon_pairs(self, mock_sf, mock_gemini, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        data = resp.json()
        assert len(data["mine_coords"]) == 2
        assert len(data["plant_coords"]) == 2
        assert -90 <= data["mine_coords"][0] <= 90
        assert -180 <= data["mine_coords"][1] <= 180


class TestMineForMeSnowflakeFailure:
    """Degraded mode when Snowflake is down."""

    @patch("app.main.load_fallback_data", return_value=SAMPLE_MINE_DATA)
    @patch("app.main.generate_prose", return_value=("Fallback prose.", True))
    @patch("app.main.query_mine_for_subregion", side_effect=Exception("Connection refused"))
    def test_snowflake_down_uses_fallback(self, mock_sf, mock_gemini, mock_fb, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["degraded"] is True
        assert data["mine"] == "Bailey Mine"

    @patch("app.main.load_fallback_data", return_value=None)
    @patch("app.main.query_mine_for_subregion", side_effect=Exception("Connection refused"))
    def test_snowflake_down_no_fallback_returns_404(self, mock_sf, mock_fb, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "ZZZZ"})
        assert resp.status_code == 404

    @patch("app.main.load_fallback_data", return_value=None)
    @patch("app.main.query_mine_for_subregion", return_value=None)
    def test_no_data_for_subregion_returns_404(self, mock_sf, mock_fb, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "NOPE"})
        assert resp.status_code == 404


class TestMineForMeGeminiFailure:
    """Degraded mode when Gemini is down but Snowflake works."""

    @patch("app.main.generate_prose", return_value=("Template fallback.", True))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_gemini_down_sets_degraded(self, mock_sf, mock_gemini, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        data = resp.json()
        assert data["degraded"] is True
        assert data["mine"] == "Bailey Mine"
        assert len(data["prose"]) > 0


class TestMineForMeSnowflakeNoneFallbackSuccess:
    """Snowflake returns None (no data) but fallback succeeds."""

    @patch("app.main.load_fallback_data", return_value=SAMPLE_MINE_DATA)
    @patch("app.main.generate_prose", return_value=("Fallback prose.", True))
    @patch("app.main.query_mine_for_subregion", return_value=None)
    def test_snowflake_none_fallback_succeeds(self, mock_sf, mock_gemini, mock_fb, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["degraded"] is True
        assert data["mine"] == "Bailey Mine"

    @patch("app.main.generate_prose", return_value=("Prose.", False))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_subregion_id_in_response(self, mock_sf, mock_gemini, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        data = resp.json()
        assert data["subregion_id"] == "SRVC"

    @patch("app.main.generate_prose", return_value=("Prose.", False))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_subregion_id_injected_into_generate_prose(self, mock_sf, mock_gemini, client):
        """mine_data dict passed to generate_prose must include subregion_id."""
        client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        call_args = mock_gemini.call_args[0][0]
        assert call_args["subregion_id"] == "SRVC"

    @patch("app.main.generate_prose", return_value=("Prose.", False))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_response_content_type_is_json(self, mock_sf, mock_gemini, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert "application/json" in resp.headers["content-type"]


class TestMineForMeValidation:
    """Request validation edge cases."""

    def test_missing_body_returns_422(self, client):
        resp = client.post("/mine-for-me")
        assert resp.status_code == 422

    def test_empty_json_returns_422(self, client):
        resp = client.post("/mine-for-me", json={})
        assert resp.status_code == 422

    def test_wrong_field_name_returns_422(self, client):
        resp = client.post("/mine-for-me", json={"region": "SRVC"})
        assert resp.status_code == 422

    def test_numeric_subregion_returns_422(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": 123})
        assert resp.status_code == 422

    def test_get_method_not_allowed(self, client):
        resp = client.get("/mine-for-me")
        assert resp.status_code == 405

    def test_list_subregion_returns_422(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": ["SRVC"]})
        assert resp.status_code == 422

    def test_bool_subregion_returns_422(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": True})
        assert resp.status_code == 422
