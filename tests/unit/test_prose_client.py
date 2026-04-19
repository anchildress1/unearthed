"""Unit tests for prose_client: stats from mine_data, Cortex Complete fallbacks."""

from unittest.mock import MagicMock, patch

from app.prose_client import _FALLBACK_NO_DATA, generate_prose


def _make_mine_data(**overrides):
    """Build a complete mine_data dict with sensible defaults."""
    base = {
        "mine_id": "100",
        "mine": "Test Mine",
        "mine_operator": "Test Operator LLC",
        "mine_county": "Test County",
        "mine_state": "TN",
        "mine_type": "Underground",
        "plant": "Test Plant",
        "plant_operator": "Test Utility Co",
        "tons": 500000,
        "tons_year": 2024,
        "fatalities": 3,
        "injuries": 10,
        "days_lost": 500,
    }
    base.update(overrides)
    return base


class TestGenerateProse:
    def _mock_connection(self, complete_result=None):
        mock_conn = MagicMock()
        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = complete_result
        mock_conn.cursor.return_value = complete_cursor
        return mock_conn, complete_cursor

    @patch("app.prose_client._get_connection")
    def test_stats_from_mine_data_in_prompt(self, mock_get_conn):
        """Safety stats are read from mine_data, not a separate SQL query."""
        mock_conn, complete_cur = self._mock_connection(
            complete_result=("Generated prose.",),
        )
        mock_get_conn.return_value = mock_conn

        generate_prose(_make_mine_data(fatalities=7, injuries=15, days_lost=2000))

        prompt_arg = complete_cur.execute.call_args[0][1][0]
        assert "7 deaths" in prompt_arg
        assert "15 lost-time injuries" in prompt_arg
        assert "2,000 days lost" in prompt_arg

    @patch("app.prose_client._get_connection")
    def test_missing_stats_default_to_zero(self, mock_get_conn):
        """mine_data without stats keys → zeros in prompt, Complete still runs."""
        mock_conn, complete_cur = self._mock_connection(
            complete_result=("Prose without safety data.",),
        )
        mock_get_conn.return_value = mock_conn

        data = _make_mine_data()
        del data["fatalities"]
        del data["injuries"]
        del data["days_lost"]
        prose, degraded = generate_prose(data)

        assert prose == "Prose without safety data."
        assert degraded is False
        complete_cur.execute.assert_called_once()

    @patch("app.prose_client._get_connection")
    def test_none_stats_default_to_zero(self, mock_get_conn):
        """None stat values → zeros in prompt, Complete still runs."""
        mock_conn, complete_cur = self._mock_connection(
            complete_result=("Prose with nulls handled.",),
        )
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(
            _make_mine_data(fatalities=None, injuries=None, days_lost=None)
        )

        assert prose == "Prose with nulls handled."
        assert degraded is False
        prompt_arg = complete_cur.execute.call_args[0][1][0]
        assert "0 deaths" in prompt_arg

    @patch("app.prose_client._get_connection")
    def test_zero_stats_still_calls_complete(self, mock_get_conn):
        """Zero fatalities/injuries — Complete still runs, prompt says omit zeros."""
        mock_conn, complete_cur = self._mock_connection(
            complete_result=("Prose about the mine and plant.",),
        )
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data(fatalities=0, injuries=0, days_lost=0))

        assert prose == "Prose about the mine and plant."
        assert degraded is False
        complete_cur.execute.assert_called_once()

    @patch("app.prose_client._get_connection")
    def test_complete_success_returns_prose(self, mock_get_conn):
        mock_conn, _ = self._mock_connection(
            complete_result=("Three workers have died at this mine.",),
        )
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data())

        assert prose == "Three workers have died at this mine."
        assert degraded is False

    @patch("app.prose_client._get_connection")
    def test_complete_empty_falls_back_to_template(self, mock_get_conn):
        mock_conn, _ = self._mock_connection(complete_result=("",))
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data())

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "3 workers have died" in prose
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_complete_none_result_falls_back_to_template(self, mock_get_conn):
        mock_conn, _ = self._mock_connection(complete_result=None)
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data())

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "3 workers have died" in prose
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_zero_stats_omitted_from_fallback(self, mock_get_conn):
        """Fallback template must not render 'o workers have died' for zero stats."""
        mock_conn, _ = self._mock_connection(complete_result=("",))
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data(fatalities=0, injuries=0, days_lost=0))

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "workers have died" not in prose
        assert "injured" not in prose
        assert degraded is True

    @patch("app.prose_client._get_connection", side_effect=Exception("Connection refused"))
    def test_connection_failure_returns_fallback(self, mock_get_conn):
        prose, degraded = generate_prose(_make_mine_data())

        assert prose == _FALLBACK_NO_DATA
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_complete_cursor_closed(self, mock_get_conn):
        mock_conn, complete_cur = self._mock_connection(
            complete_result=("Prose.",),
        )
        mock_get_conn.return_value = mock_conn

        generate_prose(_make_mine_data())

        complete_cur.close.assert_called_once()

    @patch("app.prose_client._get_connection")
    def test_only_one_cursor_opened(self, mock_get_conn):
        """Stats come from mine_data — only one cursor (Complete) should open."""
        mock_conn, _ = self._mock_connection(complete_result=("Prose.",))
        mock_get_conn.return_value = mock_conn

        generate_prose(_make_mine_data())

        mock_conn.cursor.assert_called_once()

    @patch("app.prose_client._get_connection")
    def test_prompt_includes_plant_and_mine_context(self, mock_get_conn):
        """The Cortex Complete prompt must include plant, mine, tonnage, and operator."""
        mock_conn, complete_cur = self._mock_connection(
            complete_result=("Generated prose.",),
        )
        mock_get_conn.return_value = mock_conn

        generate_prose(
            _make_mine_data(
                mine="Bailey Mine",
                plant="Miller Plant",
                mine_operator="Consol Energy",
                tons=5000000,
            )
        )

        prompt_arg = complete_cur.execute.call_args[0][1][0]
        assert "Bailey Mine" in prompt_arg
        assert "Miller Plant" in prompt_arg
        assert "Consol Energy" in prompt_arg
        assert "5,000,000" in prompt_arg


class TestProseCache:
    def test_cache_hit_skips_snowflake(self):
        from app.prose_client import _prose_cache

        _prose_cache["SRVC"] = ("Cached prose.", False)
        try:
            prose, degraded = generate_prose({"subregion_id": "SRVC", "mine_id": "1"})
            assert prose == "Cached prose."
            assert degraded is False
        finally:
            _prose_cache.pop("SRVC", None)

    @patch("app.prose_client._get_connection")
    def test_successful_prose_cached(self, mock_get_conn):
        from app.prose_client import _prose_cache

        _prose_cache.clear()
        mock_conn = MagicMock()
        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = ("Generated prose.",)
        mock_conn.cursor.return_value = complete_cursor
        mock_get_conn.return_value = mock_conn

        generate_prose(_make_mine_data(subregion_id="TNVA"))

        assert "TNVA" in _prose_cache
        assert _prose_cache["TNVA"][0] == "Generated prose."
        _prose_cache.clear()

    @patch("app.prose_client._get_connection")
    def test_degraded_prose_not_cached(self, mock_get_conn):
        from app.prose_client import _prose_cache

        _prose_cache.clear()
        mock_conn = MagicMock()
        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = complete_cursor
        mock_get_conn.return_value = mock_conn

        generate_prose(_make_mine_data(subregion_id="TNVA"))

        assert "TNVA" not in _prose_cache
        _prose_cache.clear()
