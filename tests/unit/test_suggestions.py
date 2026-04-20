"""Unit tests for contextual suggestion generation and mine context caching."""

from unittest.mock import patch

from tests.conftest import SAMPLE_MINE_DATA

# Matches the stats dict shape returned by generate_prose — three MSHA fields
# keyed by the frontend's public names. Zeros so these tests don't accidentally
# depend on specific incident counts while checking caching.
_STATS = {"fatalities": 0, "injuries_lost_time": 0, "days_lost": 0}


class TestSuggestionsFor:
    """Tests for _suggestions_for() contextual question templating."""

    def test_no_subregion_returns_generic(self):
        from app.main import _GENERIC_SUGGESTIONS, _suggestions_for

        result = _suggestions_for(None)
        assert result == _GENERIC_SUGGESTIONS

    def test_empty_subregion_returns_generic(self):
        from app.main import _GENERIC_SUGGESTIONS, _suggestions_for

        result = _suggestions_for("")
        assert result == _GENERIC_SUGGESTIONS

    def test_unknown_subregion_returns_generic(self):
        from app.main import _GENERIC_SUGGESTIONS, _suggestions_for

        result = _suggestions_for("ZZZZ")
        assert result == _GENERIC_SUGGESTIONS

    def test_cached_subregion_returns_contextual(self):
        from app.main import _mine_context, _suggestions_for

        _mine_context["SRVC"] = {
            "mine": "Bailey Mine",
            "plant": "Cross",
            "mine_state": "PA",
        }
        try:
            result = _suggestions_for("SRVC")
            assert "Bailey Mine" in result[0]
            assert "Cross" in result[1]
            assert "PA" in result[4]
            assert len(result) == 5
        finally:
            _mine_context.pop("SRVC", None)

    def test_subregion_lookup_case_insensitive(self):
        from app.main import _mine_context, _suggestions_for

        _mine_context["RFCW"] = {
            "mine": "Hobet Mine",
            "plant": "Mitchell",
            "mine_state": "WV",
        }
        try:
            result = _suggestions_for("rfcw")
            assert "Hobet Mine" in result[0]
        finally:
            _mine_context.pop("RFCW", None)

    def test_suggestions_include_subregion_id(self):
        from app.main import _mine_context, _suggestions_for

        _mine_context["MROW"] = {
            "mine": "Eagle Butte",
            "plant": "Sherburne",
            "mine_state": "WY",
        }
        try:
            result = _suggestions_for("mrow")
            assert "MROW" in result[3]
        finally:
            _mine_context.pop("MROW", None)

    def test_generic_suggestions_are_five(self):
        from app.main import _GENERIC_SUGGESTIONS

        assert len(_GENERIC_SUGGESTIONS) == 5


class TestMineContextPopulation:
    """Tests that /mine-for-me populates _mine_context for downstream use."""

    @patch("app.main.generate_prose", return_value=("Prose.", False, _STATS))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_mine_for_me_populates_context(self, mock_sf, mock_prose, client):
        from app.main import _mine_context

        _mine_context.clear()
        client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert "SRVC" in _mine_context
        assert _mine_context["SRVC"]["mine"] == "Bailey Mine"
        _mine_context.clear()

    @patch("app.main.generate_prose", return_value=("Prose.", False, _STATS))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_context_key_uppercased(self, mock_sf, mock_prose, client):
        from app.main import _mine_context

        _mine_context.clear()
        client.post("/mine-for-me", json={"subregion_id": "srvc"})
        assert "SRVC" in _mine_context
        _mine_context.clear()

    @patch("app.main.generate_prose", return_value=("Prose.", False, _STATS))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_context_cache_bounded(self, mock_sf, mock_prose, client):
        """Cache evicts the oldest entry when it exceeds _CACHE_MAXSIZE."""
        from app.main import _CACHE_MAXSIZE, _mine_context

        _mine_context.clear()
        try:
            for i in range(_CACHE_MAXSIZE + 1):
                client.post("/mine-for-me", json={"subregion_id": f"Z{i:04d}"})
            assert len(_mine_context) == _CACHE_MAXSIZE
            assert "Z0000" not in _mine_context
            assert f"Z{_CACHE_MAXSIZE:04d}" in _mine_context
        finally:
            _mine_context.clear()


class TestAskUsesContextualSuggestions:
    """Tests that /ask returns contextual suggestions when mine context exists."""

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
    )
    def test_ask_with_populated_context_returns_contextual(self, mock_cortex, client):
        from app.main import _mine_context

        _mine_context["SRVC"] = {
            "mine": "Bailey Mine",
            "plant": "Cross",
            "mine_state": "PA",
        }
        try:
            resp = client.post("/ask", json={"question": "How much coal?", "subregion_id": "SRVC"})
            data = resp.json()
            assert any("Bailey Mine" in s for s in data["suggestions"])
        finally:
            _mine_context.clear()

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
    )
    def test_ask_without_context_returns_generic(self, mock_cortex, client):
        from app.main import _GENERIC_SUGGESTIONS, _mine_context

        _mine_context.clear()
        resp = client.post("/ask", json={"question": "How much coal?", "subregion_id": "SRVC"})
        data = resp.json()
        assert data["suggestions"] == _GENERIC_SUGGESTIONS

    @patch("app.main.query_cortex_analyst", side_effect=Exception("Service unavailable"))
    def test_cortex_failure_with_context_returns_contextual(self, mock_cortex, client):
        from app.main import _mine_context

        _mine_context["RFCW"] = {
            "mine": "Hobet Mine",
            "plant": "Mitchell",
            "mine_state": "WV",
        }
        try:
            resp = client.post("/ask", json={"question": "How much coal?", "subregion_id": "RFCW"})
            data = resp.json()
            assert any("Hobet Mine" in s for s in data["suggestions"])
        finally:
            _mine_context.clear()
