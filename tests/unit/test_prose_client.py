"""Unit tests for prose_client: stats from mine_data, Cortex Complete fallbacks, H3 summaries."""

from unittest.mock import MagicMock, patch

import pytest

from app.prose_client import (
    _COMPLETE_PROMPT,
    _FALLBACK_NO_DATA,
    _H3_SUMMARY_PROMPT,
    _build_fallback,
    generate_h3_summary,
    generate_prose,
)


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


@pytest.fixture(autouse=True)
def _clear_h3_cache():
    """Keep H3 summary cache isolated across tests — otherwise the first
    successful test pins the value for every later one."""
    from app import prose_client

    prose_client._h3_summary_cache.clear()
    yield
    prose_client._h3_summary_cache.clear()


class TestBuildFallback:
    def test_includes_plant_and_mine(self):
        args = {
            "plant_name": "Cross",
            "mine_name": "Bailey Mine",
            "mine_county": "Greene",
            "mine_state": "PA",
            "mine_type": "Underground",
            "tons": "500,000",
            "tons_year": 2024,
            "fatalities": 3,
            "injuries": 10,
            "days_lost": "500",
        }
        out = _build_fallback(args)
        assert "Cross" in out
        assert "Bailey Mine" in out
        assert "3 workers have died" in out

    def test_skips_zero_fatalities(self):
        args = {
            "plant_name": "P",
            "mine_name": "M",
            "mine_county": "C",
            "mine_state": "WV",
            "mine_type": "Surface",
            "tons": "1,000",
            "tons_year": 2024,
            "fatalities": 0,
            "injuries": 5,
            "days_lost": "50",
        }
        out = _build_fallback(args)
        assert "died" not in out
        assert "injured" in out

    def test_skips_zero_injuries(self):
        args = {
            "plant_name": "P",
            "mine_name": "M",
            "mine_county": "C",
            "mine_state": "WV",
            "mine_type": "Surface",
            "tons": "1,000",
            "tons_year": 2024,
            "fatalities": 2,
            "injuries": 0,
            "days_lost": "0",
        }
        out = _build_fallback(args)
        assert "injured" not in out
        assert "2 workers have died" in out


class TestCompletePrompt:
    def test_prompt_carries_plant_and_mine_context(self):
        """The full-narrative prompt must receive plant + mine + tonnage fields."""
        for placeholder in (
            "{plant_name}",
            "{plant_operator}",
            "{mine_name}",
            "{mine_operator}",
            "{mine_type}",
            "{tons}",
        ):
            assert placeholder in _COMPLETE_PROMPT, f"missing {placeholder}"

    def test_prompt_is_eulogy_style(self):
        assert "eulogy" in _COMPLETE_PROMPT.lower()


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
        prose, degraded, _stats = generate_prose(data)

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

        prose, degraded, _stats = generate_prose(
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

        prose, degraded, _stats = generate_prose(
            _make_mine_data(fatalities=0, injuries=0, days_lost=0),
        )

        assert prose == "Prose about the mine and plant."
        assert degraded is False
        complete_cur.execute.assert_called_once()

    @patch("app.prose_client._get_connection")
    def test_complete_success_returns_prose(self, mock_get_conn):
        mock_conn, _ = self._mock_connection(
            complete_result=("Three workers have died at this mine.",),
        )
        mock_get_conn.return_value = mock_conn

        prose, degraded, _stats = generate_prose(_make_mine_data())

        assert prose == "Three workers have died at this mine."
        assert degraded is False

    @patch("app.prose_client._get_connection")
    def test_complete_empty_falls_back_to_template(self, mock_get_conn):
        mock_conn, _ = self._mock_connection(complete_result=("",))
        mock_get_conn.return_value = mock_conn

        prose, degraded, _stats = generate_prose(_make_mine_data())

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "3 workers have died" in prose
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_complete_none_result_falls_back_to_template(self, mock_get_conn):
        mock_conn, _ = self._mock_connection(complete_result=None)
        mock_get_conn.return_value = mock_conn

        prose, degraded, _stats = generate_prose(_make_mine_data())

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "3 workers have died" in prose
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_zero_stats_omitted_from_fallback(self, mock_get_conn):
        """Fallback template must not render 'o workers have died' for zero stats."""
        mock_conn, _ = self._mock_connection(complete_result=("",))
        mock_get_conn.return_value = mock_conn

        prose, degraded, _stats = generate_prose(
            _make_mine_data(fatalities=0, injuries=0, days_lost=0),
        )

        assert "Test Plant" in prose
        assert "Test Mine" in prose
        assert "workers have died" not in prose
        assert "injured" not in prose
        assert degraded is True

    @patch("app.prose_client._get_connection", side_effect=Exception("Connection refused"))
    def test_connection_failure_returns_fallback(self, mock_get_conn):
        prose, degraded, _stats = generate_prose(_make_mine_data())

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

        _prose_cache["SRVC"] = (
            "Cached prose.",
            False,
            {"fatalities": 0, "injuries_lost_time": 0, "days_lost": 0, "incidents": 0},
        )
        try:
            prose, degraded, stats = generate_prose({"subregion_id": "SRVC", "mine_id": "1"})
            assert prose == "Cached prose."
            assert degraded is False
            assert stats == {
                "fatalities": 0,
                "injuries_lost_time": 0,
                "days_lost": 0,
                "incidents": 0,
            }
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


class TestH3SummaryPrompt:
    def test_prompt_has_active_pct_and_scope_placeholders(self):
        for placeholder in (
            "{scope_line}",
            "{total",
            "{active",
            "{abandoned",
            "{active_pct}",
            "{top_counties}",
        ):
            assert placeholder in _H3_SUMMARY_PROMPT, f"missing {placeholder}"


class TestGenerateH3Summary:
    @patch("app.prose_client._get_connection")
    def test_returns_cortex_output_when_populated(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Most of these mines are already closed.",)
        mock_conn.return_value.cursor.return_value = cursor

        text, degraded = generate_h3_summary(state="WV", total=500, active=20, abandoned=480)
        assert degraded is False
        assert text == "Most of these mines are already closed."

    @patch("app.prose_client._get_connection")
    def test_cache_hit_skips_cortex(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Cached H3 summary.",)
        mock_conn.return_value.cursor.return_value = cursor

        first, first_degraded = generate_h3_summary(state="WV", total=100, active=10, abandoned=90)
        second, second_degraded = generate_h3_summary(
            state="WV", total=100, active=10, abandoned=90
        )
        assert first == second == "Cached H3 summary."
        assert first_degraded is False
        assert second_degraded is False
        # Cursor only opened once — the second call must short-circuit on cache.
        assert mock_conn.return_value.cursor.call_count == 1

    @patch("app.prose_client._get_connection")
    def test_fallback_used_when_cortex_raises(self, mock_conn):
        mock_conn.side_effect = RuntimeError("cortex down")

        text, degraded = generate_h3_summary(state="KY", total=800, active=30, abandoned=770)
        assert degraded is True
        assert "KY" in text
        assert "800" in text

    @patch("app.prose_client._get_connection")
    def test_fallback_not_cached(self, mock_conn):
        """A fallback response must not get pinned under the Cortex byline —
        the next request needs to re-attempt Cortex in case it recovered."""
        mock_conn.side_effect = RuntimeError("cortex down")

        generate_h3_summary(state="WY", total=50, active=5, abandoned=45)

        # Next call: Cortex back online. Must call the cursor again.
        mock_conn.side_effect = None
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Cortex recovered.",)
        mock_conn.return_value.cursor.return_value = cursor

        text, degraded = generate_h3_summary(state="WY", total=50, active=5, abandoned=45)
        assert degraded is False
        assert text == "Cortex recovered."

    @patch("app.prose_client._get_connection")
    def test_national_scope_when_state_none(self, mock_conn):
        mock_conn.side_effect = RuntimeError("cortex down")

        text, degraded = generate_h3_summary(state=None, total=10_000, active=200, abandoned=9_800)
        assert degraded is True
        # National fallback doesn't template any state name.
        assert "10,000" in text
        assert "None" not in text

    @patch("app.prose_client._get_connection")
    def test_zero_total_does_not_divide_by_zero(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Empty map.",)
        mock_conn.return_value.cursor.return_value = cursor

        text, degraded = generate_h3_summary(state="AK", total=0, active=0, abandoned=0)
        # No ZeroDivisionError; Cortex is still asked (caller gates on total>0
        # at the endpoint layer, but the generator itself must be safe).
        assert degraded is False
        assert text == "Empty map."

    @patch("app.prose_client._get_connection")
    def test_role_passed_through_to_connection(self, mock_conn):
        """Readonly role from the /h3-density endpoint must scope the Cortex
        connection — passing ``role=None`` would silently fall back to the
        default APP_ROLE and break least-privilege on the public endpoint."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Scoped.",)
        mock_conn.return_value.cursor.return_value = cursor

        generate_h3_summary(
            state="WV",
            total=10,
            active=1,
            abandoned=9,
            role="READONLY_ROLE",
        )
        mock_conn.assert_called_once_with(role="READONLY_ROLE")

    @patch("app.prose_client._get_connection")
    def test_fallback_prose_avoids_banned_words(self, mock_conn):
        """ "still" and "moss" were removed from the fallback templates —
        "still" violates the voice rule the prompt itself enforces, and
        "moss" reads as "life grew back" which contradicts the ash legend
        on the map. Lock that out so a future edit can't quietly reintroduce
        them under a "Cortex, on this map" byline."""
        mock_conn.side_effect = RuntimeError("cortex down")

        state_text, _ = generate_h3_summary(state="WV", total=500, active=20, abandoned=480)
        national_text, _ = generate_h3_summary(
            state=None, total=10_000, active=200, abandoned=9_800
        )
        for text in (state_text, national_text):
            assert "still" not in text.lower()
            assert "moss" not in text.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
