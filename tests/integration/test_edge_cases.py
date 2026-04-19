"""Integration tests for edge cases: unicode, long inputs, CORS, injection."""

from unittest.mock import patch

from tests.conftest import SAMPLE_MINE_DATA

# Generic MSHA safety-stats payload for mocked generate_prose returns. Real
# values are exercised in the unit tests and in the dedicated happy-path
# integration test; these edge-case tests only need the third tuple slot
# populated so the endpoint still returns a schema-valid response.
_STATS = {
    "fatalities": 0,
    "injuries_lost_time": 0,
    "days_lost": 0,
    "incidents": 0,
}


class TestAskEdgeCases:
    """Edge cases for the /ask endpoint."""

    def test_unicode_question_accepted(self, client):
        with patch(
            "app.main.query_cortex_analyst",
            return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
        ):
            resp = client.post("/ask", json={"question": "How much coal in 日本語?"})
        assert resp.status_code == 200

    def test_emoji_question_accepted(self, client):
        with patch(
            "app.main.query_cortex_analyst",
            return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
        ):
            resp = client.post("/ask", json={"question": "How much coal? 🪨⛏️"})
        assert resp.status_code == 200

    def test_max_length_question_accepted(self, client):
        with patch(
            "app.main.query_cortex_analyst",
            return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
        ):
            question = "x" * 500
            resp = client.post("/ask", json={"question": question})
        assert resp.status_code == 200

    def test_over_max_length_question_rejected(self, client):
        question = "x" * 501
        resp = client.post("/ask", json={"question": question})
        assert resp.status_code == 422

    def test_sql_injection_in_question_safe(self, client):
        with patch(
            "app.main.query_cortex_analyst",
            return_value={"answer": "safe", "interpretation": None, "sql": None, "error": None},
        ):
            resp = client.post("/ask", json={"question": "'; DROP TABLE mines; --"})
        assert resp.status_code == 200

    def test_html_in_question_not_executed(self, client):
        with patch(
            "app.main.query_cortex_analyst",
            return_value={
                "answer": "<script>alert(1)</script>",
                "interpretation": None,
                "sql": None,
                "error": None,
            },
        ):
            resp = client.post("/ask", json={"question": "<script>alert(1)</script>"})
        assert resp.status_code == 200
        # Response is JSON, not rendered HTML — XSS is a frontend concern


class TestMineForMeEdgeCases:
    """Edge cases for the /mine-for-me endpoint."""

    def test_path_traversal_in_subregion_rejected(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "../etc/passwd"})
        assert resp.status_code == 422

    def test_null_byte_injection_rejected(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC\x00DROP"})
        assert resp.status_code == 422

    def test_very_long_subregion_rejected(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "A" * 100})
        assert resp.status_code == 422

    def test_empty_string_subregion_rejected(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": ""})
        assert resp.status_code == 422

    def test_single_char_subregion_rejected(self, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "X"})
        assert resp.status_code == 422


class TestCorsHeaders:
    """Verify CORS headers are present on API responses."""

    def test_cors_allows_origin(self, client):
        resp = client.options(
            "/mine-for-me",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" in resp.headers

    def test_cors_allows_post_method(self, client):
        resp = client.options(
            "/ask",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        assert "POST" in allow_methods


class TestHttpMethods:
    """Verify correct HTTP method handling."""

    def test_put_mine_for_me_returns_405(self, client):
        resp = client.put("/mine-for-me", json={"subregion_id": "SRVC"})
        assert resp.status_code in (404, 405)

    def test_delete_ask_returns_405(self, client):
        resp = client.delete("/ask")
        assert resp.status_code in (404, 405)

    def test_patch_mine_for_me_returns_405(self, client):
        resp = client.patch("/mine-for-me", json={"subregion_id": "SRVC"})
        assert resp.status_code in (404, 405)


class TestResponseHeaders:
    """Verify response headers on API endpoints."""

    @patch(
        "app.main.generate_prose",
        return_value=("Prose.", False, _STATS),
    )
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_mine_for_me_no_cache_header(self, mock_sf, mock_prose, client):
        """API JSON responses should not include cache-control by default."""
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert resp.status_code == 200
        assert "cache-control" not in resp.headers

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
    )
    def test_ask_response_is_valid_json(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "test"})
        # Should not raise
        data = resp.json()
        assert isinstance(data, dict)


class TestConcurrentFailures:
    """Both Snowflake and Gemini fail simultaneously."""

    @patch(
        "app.main.generate_prose",
        return_value=("Fallback.", True, _STATS),
    )
    @patch("app.main.load_fallback_data", return_value=SAMPLE_MINE_DATA)
    @patch("app.main.query_mine_for_subregion", side_effect=Exception("SF down"))
    def test_both_snowflake_and_prose_degraded(self, mock_sf, mock_fb, mock_prose, client):
        """Snowflake and prose both failing must result in degraded=True."""
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        data = resp.json()
        assert data["degraded"] is True

    @patch("app.main.load_fallback_data", return_value=None)
    @patch("app.main.query_mine_for_subregion", return_value=None)
    def test_no_data_no_fallback_returns_404_detail(self, mock_sf, mock_fb, client):
        """404 response must include descriptive detail message."""
        resp = client.post("/mine-for-me", json={"subregion_id": "ZZZZ"})
        assert resp.status_code == 404
        data = resp.json()
        assert "ZZZZ" in data["detail"]


class TestResponsePayloadBounds:
    """Verify response payloads stay within reasonable bounds."""

    @patch(
        "app.main.generate_prose",
        return_value=("Short prose.", False, _STATS),
    )
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_mine_for_me_response_under_10kb(self, mock_sf, mock_prose, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert resp.status_code == 200
        assert len(resp.content) < 10_000

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
    )
    def test_ask_response_under_10kb(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "How much coal?"})
        assert resp.status_code == 200
        assert len(resp.content) < 10_000
