"""Unit tests for Gemini client: caching, fallback, template formatting."""

from unittest.mock import MagicMock, patch

import pytest

from app import gemini_client


@pytest.fixture(autouse=True)
def clear_prose_cache():
    """Reset the in-memory prose cache before each test."""
    gemini_client._prose_cache.clear()
    yield
    gemini_client._prose_cache.clear()


class TestFallbackProse:
    def test_fallback_contains_mine_name(self, sample_mine_data):
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "Bailey Mine" in prose

    def test_fallback_contains_plant_name(self, sample_mine_data):
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "Cross" in prose

    def test_fallback_contains_operator(self, sample_mine_data):
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "Consol Pennsylvania Coal Company LLC" in prose

    def test_fallback_contains_tonnage(self, sample_mine_data):
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "1,247,001" in prose

    def test_fallback_contains_county_and_state(self, sample_mine_data):
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "Greene" in prose
        assert "PA" in prose

    def test_fallback_surface_mine_type_lowercase(self, sample_mine_data_surface):
        prose = gemini_client._fallback_prose(sample_mine_data_surface)
        assert "surface" in prose

    def test_fallback_contains_plant_operator(self, sample_mine_data):
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "South Carolina Public Service Authority" in prose

    def test_fallback_contains_subregion(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "SRVC"
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "SRVC" in prose


class TestGenerateProse:
    def test_no_api_key_returns_degraded(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "TEST_NO_KEY"
        with patch.object(gemini_client.settings, "gemini_api_key", ""):
            prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert degraded is True
        assert "Bailey Mine" in prose

    def test_cache_hit_returns_cached_prose(self, sample_mine_data):
        gemini_client._prose_cache["CACHED"] = "Previously generated prose."
        sample_mine_data["subregion_id"] = "CACHED"
        prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert prose == "Previously generated prose."
        assert degraded is False

    def test_cache_hit_does_not_call_gemini(self, sample_mine_data):
        gemini_client._prose_cache["CACHED2"] = "Cached."
        sample_mine_data["subregion_id"] = "CACHED2"
        with patch("app.gemini_client.genai") as mock_genai:
            gemini_client.generate_prose(sample_mine_data)
        mock_genai.Client.assert_not_called()

    def test_successful_gemini_call_caches_result(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "NEW_REGION"
        mock_response = MagicMock()
        mock_response.text = "  Generated prose about Bailey Mine.  "
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)

        assert prose == "Generated prose about Bailey Mine."
        assert degraded is False
        assert gemini_client._prose_cache["NEW_REGION"] == prose

    def test_gemini_exception_falls_back(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "FAIL_REGION"
        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", side_effect=Exception("API down")):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)

        assert degraded is True
        assert "Bailey Mine" in prose

    def test_no_api_key_caches_fallback(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "CACHE_DEGRADE"
        with patch.object(gemini_client.settings, "gemini_api_key", ""):
            prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert degraded is True
        assert "CACHE_DEGRADE" in gemini_client._prose_cache
        assert gemini_client._prose_cache["CACHE_DEGRADE"] == prose

    def test_gemini_exception_caches_fallback(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "FAIL_CACHE"
        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", side_effect=Exception("boom")):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert degraded is True
        assert "FAIL_CACHE" in gemini_client._prose_cache
        assert gemini_client._prose_cache["FAIL_CACHE"] == prose

    def test_empty_subregion_not_cached(self, sample_mine_data):
        sample_mine_data["subregion_id"] = ""
        with patch.object(gemini_client.settings, "gemini_api_key", ""):
            gemini_client.generate_prose(sample_mine_data)
        assert "" not in gemini_client._prose_cache

    def test_different_subregions_get_separate_cache_entries(self, sample_mine_data):
        gemini_client._prose_cache["REGION_A"] = "Prose A"
        gemini_client._prose_cache["REGION_B"] = "Prose B"

        sample_mine_data["subregion_id"] = "REGION_A"
        prose_a, _ = gemini_client.generate_prose(sample_mine_data)

        sample_mine_data["subregion_id"] = "REGION_B"
        prose_b, _ = gemini_client.generate_prose(sample_mine_data)

        assert prose_a != prose_b
