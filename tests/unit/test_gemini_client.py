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

    # --- Structural tests: verb, article, and tons_year by mine_type ---

    def test_fallback_underground_uses_hollowed_out(self, sample_mine_data):
        """Underground mines must not say 'stripped' — that's surface-only language."""
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "hollowed out" in prose
        assert "stripped" not in prose

    def test_fallback_underground_article_is_an(self, sample_mine_data):
        """'Underground' starts with a vowel → article must be 'an'."""
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "an underground" in prose

    def test_fallback_surface_uses_stripped(self, sample_mine_data_surface):
        """Surface mines must use 'stripped'."""
        prose = gemini_client._fallback_prose(sample_mine_data_surface)
        assert "stripped" in prose
        assert "hollowed out" not in prose

    def test_fallback_surface_article_is_a(self, sample_mine_data_surface):
        """'Surface' starts with a consonant → article must be 'a'."""
        prose = gemini_client._fallback_prose(sample_mine_data_surface)
        assert "a surface" in prose

    def test_fallback_contains_tons_year(self, sample_mine_data):
        """tons_year must appear in the fallback — the template had it dropped."""
        sample_mine_data["tons_year"] = 2024
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "2024" in prose

    def test_fallback_underground_contains_all_required_fields(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "SRVC"
        sample_mine_data["tons_year"] = 2024
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "Bailey Mine" in prose
        assert "Consol Pennsylvania Coal Company LLC" in prose
        assert "1,247,001" in prose
        assert "2024" in prose
        assert "Cross" in prose
        assert "South Carolina Public Service Authority" in prose
        assert "SRVC" in prose

    def test_fallback_surface_contains_all_required_fields(self, sample_mine_data_surface):
        sample_mine_data_surface["subregion_id"] = "SERC"
        sample_mine_data_surface["tons_year"] = 2023
        prose = gemini_client._fallback_prose(sample_mine_data_surface)
        assert "Hobet Mine" in prose
        assert "1,247,001" in prose
        assert "2023" in prose
        assert "Cross" in prose
        assert "SERC" in prose

    def test_fallback_facility_uses_excavated(self, sample_mine_data):
        """Facility mine type must use 'excavated' verb."""
        sample_mine_data["mine_type"] = "Facility"
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "excavated" in prose
        assert "stripped" not in prose
        assert "hollowed out" not in prose

    def test_fallback_facility_article_is_a(self, sample_mine_data):
        """'Facility' starts with a consonant → article must be 'a'."""
        sample_mine_data["mine_type"] = "Facility"
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "a facility" in prose

    def test_fallback_unknown_type_uses_excavated(self, sample_mine_data):
        """Unknown mine_type should default to 'excavated' verb."""
        sample_mine_data["mine_type"] = "Quarry"
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "excavated" in prose

    def test_fallback_returns_string(self, sample_mine_data):
        result = gemini_client._fallback_prose(sample_mine_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_large_tonnage_formatted(self, sample_mine_data):
        """Large tonnage values should be formatted with commas."""
        sample_mine_data["tons"] = 12_345_678.0
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "12,345,678" in prose

    def test_fallback_zero_tonnage_formatted(self, sample_mine_data):
        """Zero tonnage must not crash the formatter."""
        sample_mine_data["tons"] = 0.0
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert "0" in prose

    def test_fallback_empty_subregion_handled(self, sample_mine_data):
        """Empty subregion_id should not crash fallback template."""
        sample_mine_data["subregion_id"] = ""
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert isinstance(prose, str)
        assert "Bailey Mine" in prose

    def test_fallback_missing_subregion_key_handled(self, sample_mine_data):
        """mine_data without subregion_id key must use .get() default."""
        if "subregion_id" in sample_mine_data:
            del sample_mine_data["subregion_id"]
        prose = gemini_client._fallback_prose(sample_mine_data)
        assert isinstance(prose, str)


class TestGenerateProse:
    def test_no_api_key_returns_degraded(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "TEST_NO_KEY"
        with patch.object(gemini_client.settings, "gemini_api_key", ""):
            prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert degraded is True
        assert "Bailey Mine" in prose

    def test_cache_hit_returns_cached_prose(self, sample_mine_data):
        gemini_client._prose_cache["CACHED"] = ("Previously generated prose.", False)
        sample_mine_data["subregion_id"] = "CACHED"
        prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert prose == "Previously generated prose."
        assert degraded is False

    def test_cache_hit_preserves_degraded_state(self, sample_mine_data):
        gemini_client._prose_cache["DEG"] = ("Fallback prose.", True)
        sample_mine_data["subregion_id"] = "DEG"
        prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert prose == "Fallback prose."
        assert degraded is True

    def test_cache_hit_does_not_call_gemini(self, sample_mine_data):
        gemini_client._prose_cache["CACHED2"] = ("Cached.", False)
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
        assert gemini_client._prose_cache["NEW_REGION"] == (prose, False)

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
        assert gemini_client._prose_cache["CACHE_DEGRADE"] == (prose, True)

    def test_gemini_exception_caches_fallback(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "FAIL_CACHE"
        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", side_effect=Exception("boom")):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert degraded is True
        assert "FAIL_CACHE" in gemini_client._prose_cache
        assert gemini_client._prose_cache["FAIL_CACHE"] == (prose, True)

    def test_empty_subregion_not_cached(self, sample_mine_data):
        sample_mine_data["subregion_id"] = ""
        with patch.object(gemini_client.settings, "gemini_api_key", ""):
            gemini_client.generate_prose(sample_mine_data)
        assert "" not in gemini_client._prose_cache

    def test_different_subregions_get_separate_cache_entries(self, sample_mine_data):
        gemini_client._prose_cache["REGION_A"] = ("Prose A", False)
        gemini_client._prose_cache["REGION_B"] = ("Prose B", False)

        sample_mine_data["subregion_id"] = "REGION_A"
        prose_a, _ = gemini_client.generate_prose(sample_mine_data)

        sample_mine_data["subregion_id"] = "REGION_B"
        prose_b, _ = gemini_client.generate_prose(sample_mine_data)

        assert prose_a != prose_b

    def test_gemini_returns_none_text_uses_fallback(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "NULL_TEXT"
        mock_response = MagicMock()
        mock_response.text = None
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)

        assert degraded is True
        assert "Bailey Mine" in prose

    def test_gemini_returns_empty_string_uses_fallback(self, sample_mine_data):
        sample_mine_data["subregion_id"] = "EMPTY_TEXT"
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)

        assert degraded is True
        assert "Bailey Mine" in prose

    def test_gemini_returns_whitespace_only_uses_fallback(self, sample_mine_data):
        """Whitespace-only response from Gemini is falsy → must degrade."""
        sample_mine_data["subregion_id"] = "WHITESPACE_TEXT"
        mock_response = MagicMock()
        mock_response.text = "   "
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)

        # "   ".strip() == "" which is falsy, so fallback should be used
        assert degraded is True
        assert "Bailey Mine" in prose

    def test_no_subregion_key_does_not_crash(self, sample_mine_data):
        """mine_data without 'subregion_id' key must not raise KeyError."""
        if "subregion_id" in sample_mine_data:
            del sample_mine_data["subregion_id"]
        # sample_mine_data from conftest doesn't have subregion_id by default
        with patch.object(gemini_client.settings, "gemini_api_key", ""):
            prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert isinstance(prose, str)
        assert degraded is True

    def test_successful_call_returns_stripped_prose(self, sample_mine_data):
        """Gemini response text must be stripped of leading/trailing whitespace."""
        sample_mine_data["subregion_id"] = "STRIP_TEST"
        mock_response = MagicMock()
        mock_response.text = "\n\n  Clean prose here.  \n\n"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client):
                prose, degraded = gemini_client.generate_prose(sample_mine_data)

        assert prose == "Clean prose here."
        assert degraded is False

    def test_second_call_same_subregion_uses_cache_not_gemini(self, sample_mine_data):
        """Second call for same subregion must hit cache without calling Gemini again."""
        sample_mine_data["subregion_id"] = "DOUBLE_CALL"
        mock_response = MagicMock()
        mock_response.text = "First call prose."
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client) as mock_cls:
                gemini_client.generate_prose(sample_mine_data)
                gemini_client.generate_prose(sample_mine_data)
                # Client constructor called once, not twice
                assert mock_cls.call_count == 1

    def test_none_api_key_returns_degraded(self, sample_mine_data):
        """None api_key (not just empty string) must also trigger fallback."""
        sample_mine_data["subregion_id"] = "NONE_KEY"
        with patch.object(gemini_client.settings, "gemini_api_key", None):
            prose, degraded = gemini_client.generate_prose(sample_mine_data)
        assert degraded is True
        assert "Bailey Mine" in prose

    def test_prompt_template_uses_mine_data_fields(self, sample_mine_data):
        """Prompt must be formatted with mine data before sending to Gemini."""
        sample_mine_data["subregion_id"] = "PROMPT_CHECK"
        mock_response = MagicMock()
        mock_response.text = "Generated."
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client):
                gemini_client.generate_prose(sample_mine_data)

        # Verify prompt was passed as contents arg
        call_kwargs = mock_client.models.generate_content.call_args
        prompt = call_kwargs[1]["contents"]
        assert "Bailey Mine" in prompt
        assert "Greene" in prompt

    def test_gemini_model_from_settings(self, sample_mine_data):
        """generate_content must use the model from settings."""
        sample_mine_data["subregion_id"] = "MODEL_CHECK"
        mock_response = MagicMock()
        mock_response.text = "Generated."
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch.object(gemini_client.settings, "gemini_model", "test-model"):
                with patch("app.gemini_client.genai.Client", return_value=mock_client):
                    gemini_client.generate_prose(sample_mine_data)

        call_kwargs = mock_client.models.generate_content.call_args
        assert call_kwargs[1]["model"] == "test-model"

    def test_whitespace_only_response_cached_as_degraded(self, sample_mine_data):
        """Whitespace-only Gemini response must cache as degraded."""
        sample_mine_data["subregion_id"] = "WS_CACHE"
        mock_response = MagicMock()
        mock_response.text = "   \t\n  "
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(gemini_client.settings, "gemini_api_key", "fake-key"):
            with patch("app.gemini_client.genai.Client", return_value=mock_client):
                gemini_client.generate_prose(sample_mine_data)

        assert "WS_CACHE" in gemini_client._prose_cache
        _, degraded = gemini_client._prose_cache["WS_CACHE"]
        assert degraded is True
