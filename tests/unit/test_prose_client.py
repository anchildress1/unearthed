"""Unit tests for prose_client: stats query, mine_id type, Cortex Complete fallbacks."""

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
    }
    base.update(overrides)
    return base


class TestGenerateProse:
    def _mock_connection(self, stats_row=None, complete_result=None):
        mock_conn = MagicMock()
        stats_cursor = MagicMock()
        stats_cursor.fetchone.return_value = stats_row
        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = complete_result
        mock_conn.cursor.side_effect = [stats_cursor, complete_cursor]
        return mock_conn, stats_cursor, complete_cursor

    @patch("app.prose_client._get_connection")
    def test_mine_id_passed_as_int(self, mock_get_conn):
        mock_conn, stats_cur, _ = self._mock_connection(
            stats_row=(10, 2, 5, 100),
            complete_result=("Workers have died.",),
        )
        mock_get_conn.return_value = mock_conn

        generate_prose(
            _make_mine_data(
                mine_id=3607958, mine="Bailey Mine", mine_county="Greene", mine_state="PA"
            )
        )

        call_args = stats_cur.execute.call_args
        assert call_args[0][1]["mine_id"] == 3607958

    @patch("app.prose_client._get_connection")
    def test_mine_id_from_string_converted_to_int(self, mock_get_conn):
        mock_conn, stats_cur, _ = self._mock_connection(
            stats_row=(5, 0, 3, 50),
        )
        mock_get_conn.return_value = mock_conn

        generate_prose(
            _make_mine_data(
                mine_id="3607958", mine="Bailey Mine", mine_county="Greene", mine_state="PA"
            )
        )

        call_args = stats_cur.execute.call_args
        assert call_args[0][1]["mine_id"] == 3607958

    @patch("app.prose_client._get_connection")
    def test_no_stats_returns_fallback_no_data(self, mock_get_conn):
        mock_conn, _, _ = self._mock_connection(stats_row=None)
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(
            _make_mine_data(
                mine_id="999", mine="Ghost Mine", mine_county="Nowhere", mine_state="XX"
            )
        )

        assert prose == _FALLBACK_NO_DATA
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_zero_fatalities_zero_injuries_returns_no_data(self, mock_get_conn):
        mock_conn, _, _ = self._mock_connection(stats_row=(5, 0, 0, 0))
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data(mine_id="123"))

        assert prose == _FALLBACK_NO_DATA
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_complete_success_returns_prose(self, mock_get_conn):
        mock_conn, _, _ = self._mock_connection(
            stats_row=(20, 3, 10, 500),
            complete_result=("Three workers have died at this mine.",),
        )
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data())

        assert prose == "Three workers have died at this mine."
        assert degraded is False

    @patch("app.prose_client._get_connection")
    def test_complete_empty_falls_back_to_template(self, mock_get_conn):
        mock_conn, _, _ = self._mock_connection(
            stats_row=(20, 3, 10, 500),
            complete_result=("",),
        )
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data())

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "3 workers have died" in prose
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_complete_none_result_falls_back_to_template(self, mock_get_conn):
        mock_conn, _, _ = self._mock_connection(
            stats_row=(20, 3, 10, 500),
            complete_result=None,
        )
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data())

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "3 workers have died" in prose
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_null_stats_values_default_to_zero(self, mock_get_conn):
        mock_conn, _, _ = self._mock_connection(stats_row=(None, None, None, None))
        mock_get_conn.return_value = mock_conn

        prose, degraded = generate_prose(_make_mine_data())

        assert prose == _FALLBACK_NO_DATA
        assert degraded is True

    @patch("app.prose_client._get_connection", side_effect=Exception("Connection refused"))
    def test_connection_failure_returns_fallback(self, mock_get_conn):
        prose, degraded = generate_prose(_make_mine_data())

        assert prose == _FALLBACK_NO_DATA
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_stats_cursor_closed_on_success(self, mock_get_conn):
        mock_conn, stats_cur, complete_cur = self._mock_connection(
            stats_row=(20, 3, 10, 500),
            complete_result=("Prose.",),
        )
        mock_get_conn.return_value = mock_conn

        generate_prose(_make_mine_data())

        stats_cur.close.assert_called_once()
        complete_cur.close.assert_called_once()

    @patch("app.prose_client._get_connection")
    def test_prompt_includes_plant_and_mine_context(self, mock_get_conn):
        """The Cortex Complete prompt must include plant, mine, tonnage, and operator."""
        mock_conn, _, complete_cur = self._mock_connection(
            stats_row=(20, 3, 10, 500),
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
        stats_cursor = MagicMock()
        stats_cursor.fetchone.return_value = (20, 3, 10, 500)
        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = ("Generated prose.",)
        mock_conn.cursor.side_effect = [stats_cursor, complete_cursor]
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
        stats_cursor = MagicMock()
        stats_cursor.fetchone.return_value = None
        mock_conn.cursor.side_effect = [stats_cursor]
        mock_get_conn.return_value = mock_conn

        generate_prose(_make_mine_data(subregion_id="TNVA"))

        assert "TNVA" not in _prose_cache
        _prose_cache.clear()
