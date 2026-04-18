"""Performance tests for API response times.

These tests verify that mocked endpoints respond within acceptable
latency budgets. Live Snowflake/Gemini performance is validated
separately during integration testing against real services.
"""

import time
from unittest.mock import patch

import pytest

from tests.conftest import SAMPLE_MINE_DATA


class TestMineForMePerformance:
    @pytest.mark.timeout(2)
    @patch("app.main.generate_prose", return_value=("Prose.", False))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_mine_for_me_under_200ms_mocked(self, mock_sf, mock_gemini, client):
        start = time.perf_counter()
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert elapsed < 0.2, f"Response took {elapsed:.3f}s, expected < 0.2s"

    @pytest.mark.timeout(2)
    @patch("app.main.load_fallback_data", return_value=None)
    @patch("app.main.query_mine_for_subregion", side_effect=Exception("Down"))
    def test_no_data_404_under_200ms(self, mock_sf, mock_fb, client):
        start = time.perf_counter()
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        elapsed = time.perf_counter() - start

        assert resp.status_code == 404
        assert elapsed < 0.2, f"404 response took {elapsed:.3f}s, expected < 0.2s"


class TestAskPerformance:
    @pytest.mark.timeout(2)
    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
    )
    def test_ask_under_200ms_mocked(self, mock_cortex, client):
        start = time.perf_counter()
        resp = client.post("/ask", json={"question": "How much coal?"})
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert elapsed < 0.2, f"Response took {elapsed:.3f}s, expected < 0.2s"

    @pytest.mark.timeout(2)
    @patch("app.main.query_cortex_analyst", side_effect=Exception("Down"))
    def test_ask_error_under_200ms(self, mock_cortex, client):
        start = time.perf_counter()
        resp = client.post("/ask", json={"question": "test"})
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert elapsed < 0.2, f"Error response took {elapsed:.3f}s, expected < 0.2s"
