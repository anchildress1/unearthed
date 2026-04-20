"""Unit-level edge-case tests closing coverage gaps in snowflake_client + prose_client.

Covers: query_mine_for_subregion field handling, summarize_analyst_results
edge cases, generate_prose with missing keys, generate_h3_summary with
edge-case inputs, _build_fallback with partial data.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.prose_client import _build_fallback, _stats_from, generate_h3_summary, generate_prose
from app.snowflake_client import (
    execute_analyst_sql,
    query_mine_for_subregion,
    summarize_analyst_results,
)

# ── _stats_from edge cases ───────────────────────────────────────────────────


class TestStatsFrom:
    """Stats extraction from mine_data dict."""

    def test_missing_keys_default_to_zero(self):
        stats = _stats_from({})
        assert stats == {"fatalities": 0, "injuries_lost_time": 0, "days_lost": 0}

    def test_none_values_default_to_zero(self):
        stats = _stats_from({"fatalities": None, "injuries": None, "days_lost": None})
        assert stats == {"fatalities": 0, "injuries_lost_time": 0, "days_lost": 0}

    def test_injuries_key_translated_to_lost_time(self):
        """Internal key 'injuries' → response key 'injuries_lost_time'."""
        stats = _stats_from({"injuries": 42})
        assert stats["injuries_lost_time"] == 42

    def test_string_zero_coerced(self):
        """'0' or '' should not crash — int('0') is fine, int('' or 0) is 0."""
        stats = _stats_from({"fatalities": "0", "injuries": "", "days_lost": 0})
        assert stats["fatalities"] == 0
        assert stats["injuries_lost_time"] == 0


# ── _build_fallback edge cases ───────────────────────────────────────────────


class TestBuildFallbackEdges:
    def test_zero_fatalities_and_zero_injuries_omit_both(self):
        args = {
            "plant_name": "P",
            "mine_name": "M",
            "mine_county": "C",
            "mine_state": "WV",
            "mine_type": "Surface",
            "tons": "500",
            "tons_year": 2024,
            "fatalities": 0,
            "injuries": 0,
            "days_lost": "0",
        }
        out = _build_fallback(args)
        assert "died" not in out
        assert "injured" not in out
        assert "coal kept moving" in out

    def test_injuries_with_zero_days_lost(self):
        """Injuries present but days_lost=0 → injury sentence has no dash clause."""
        args = {
            "plant_name": "P",
            "mine_name": "M",
            "mine_county": "C",
            "mine_state": "WV",
            "mine_type": "Surface",
            "tons": "500",
            "tons_year": 2024,
            "fatalities": 0,
            "injuries": 5,
            "days_lost": "0",
        }
        out = _build_fallback(args)
        assert "injured" in out
        assert "days lost" not in out

    def test_injuries_with_days_lost(self):
        """Injuries + days_lost → dash clause appended."""
        args = {
            "plant_name": "P",
            "mine_name": "M",
            "mine_county": "C",
            "mine_state": "WV",
            "mine_type": "Surface",
            "tons": "500",
            "tons_year": 2024,
            "fatalities": 0,
            "injuries": 5,
            "days_lost": "100",
        }
        out = _build_fallback(args)
        assert "100 days lost" in out


# ── generate_prose edge cases ────────────────────────────────────────────────


class TestGenerateProseEdges:
    @patch("app.prose_client._get_connection")
    def test_whitespace_only_cortex_uses_fallback(self, mock_conn):
        """Cortex returning '   ' should trigger fallback (strips to empty)."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("   ",)
        mock_conn.return_value.cursor.return_value = cursor

        prose, degraded, _ = generate_prose(
            {
                "mine": "Test",
                "mine_operator": "Op",
                "mine_county": "C",
                "mine_state": "WV",
                "mine_type": "Surface",
                "plant": "P",
                "plant_operator": "PO",
                "tons": 100,
                "tons_year": 2024,
                "fatalities": 0,
                "injuries": 0,
                "days_lost": 0,
            }
        )
        # After strip().strip('"').strip(), "   " → "" → falsy → template fallback
        assert degraded is True
        assert "P" in prose  # Plant name in fallback

    @patch("app.prose_client._get_connection")
    def test_quoted_cortex_response_stripped(self, mock_conn):
        """Cortex sometimes wraps response in double quotes."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ('"This mine has a dark history."',)
        mock_conn.return_value.cursor.return_value = cursor

        prose, degraded, _ = generate_prose(
            {
                "mine": "Test",
                "mine_operator": "Op",
                "mine_county": "C",
                "mine_state": "WV",
                "mine_type": "Surface",
                "plant": "P",
                "plant_operator": "PO",
                "tons": 100,
                "tons_year": 2024,
                "fatalities": 1,
                "injuries": 0,
                "days_lost": 0,
            }
        )
        assert not prose.startswith('"')
        assert not prose.endswith('"')
        assert degraded is False

    def test_no_subregion_id_no_cache_attempt(self):
        """Missing subregion_id skips cache lookup without error."""
        from app.prose_client import _prose_cache

        _prose_cache.clear()
        with patch("app.prose_client._get_connection") as mock_conn:
            cursor = MagicMock()
            cursor.fetchone.return_value = ("Prose.",)
            mock_conn.return_value.cursor.return_value = cursor

            prose, _, _ = generate_prose(
                {
                    "mine": "M",
                    "mine_operator": "O",
                    "mine_county": "C",
                    "mine_state": "WV",
                    "mine_type": "Surface",
                    "plant": "P",
                    "plant_operator": "PO",
                    "tons": 100,
                    "tons_year": 2024,
                    "fatalities": 0,
                    "injuries": 0,
                    "days_lost": 0,
                }
            )
        assert prose == "Prose."
        assert len(_prose_cache) == 0  # Nothing cached — no subregion_id
        _prose_cache.clear()


# ── generate_h3_summary edge cases ──────────────────────────────────────────


class TestH3SummaryEdges:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        from app import prose_client

        prose_client._h3_summary_cache.clear()
        yield
        prose_client._h3_summary_cache.clear()

    @patch("app.prose_client._get_connection")
    def test_empty_top_counties_handled(self, mock_conn):
        """Empty list for top_counties should not crash prompt format."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Summary.",)
        mock_conn.return_value.cursor.return_value = cursor

        text, degraded = generate_h3_summary(
            state="WV", total=100, active=10, abandoned=90, top_counties=[]
        )
        assert degraded is False
        assert text == "Summary."

    @patch("app.prose_client._get_connection")
    def test_cortex_returns_empty_string_uses_fallback(self, mock_conn):
        """Cortex returning '' should trigger the template fallback."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("",)
        mock_conn.return_value.cursor.return_value = cursor

        text, degraded = generate_h3_summary(state="PA", total=500, active=50, abandoned=450)
        assert degraded is True
        assert "PA" in text  # State fallback template

    @patch("app.prose_client._get_connection")
    def test_cortex_returns_whitespace_uses_fallback(self, mock_conn):
        """Cortex returning whitespace-only should trigger fallback."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("  \n  ",)
        mock_conn.return_value.cursor.return_value = cursor

        text, degraded = generate_h3_summary(state="KY", total=800, active=30, abandoned=770)
        assert degraded is True
        assert "KY" in text

    @patch("app.prose_client._get_connection")
    def test_active_greater_than_total_no_crash(self, mock_conn):
        """Defensive: active > total shouldn't crash (bad data)."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Unusual data.",)
        mock_conn.return_value.cursor.return_value = cursor

        _, degraded = generate_h3_summary(state="WV", total=5, active=10, abandoned=0)
        # Shouldn't crash — active_pct calculates to 200% but that's fine
        assert degraded is False

    @patch("app.prose_client._get_connection")
    def test_cache_key_is_case_insensitive(self, mock_conn):
        """Cache key is uppercased — 'wv' and 'WV' share cache."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Cached.",)
        mock_conn.return_value.cursor.return_value = cursor

        first, _ = generate_h3_summary(state="wv", total=100, active=10, abandoned=90)
        second, _ = generate_h3_summary(state="WV", total=100, active=10, abandoned=90)
        assert first == second
        # Only one Cortex call — second hit cache
        assert mock_conn.return_value.cursor.call_count == 1


# ── summarize_analyst_results edge cases ─────────────────────────────────────


class TestSummarizeEdges:
    @patch("app.snowflake_client._get_connection")
    def test_whitespace_only_cortex_result_returns_empty(self, mock_conn):
        """Cortex returning whitespace should strip to empty."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("   ",)
        mock_conn.return_value.cursor.return_value = cursor

        result = summarize_analyst_results("test?", [{"X": 1}])
        # "   ".strip().strip('"') = "" → falsy → returns ""
        assert result == ""

    @patch("app.snowflake_client._get_connection")
    def test_results_capped_at_10_in_prompt(self, mock_conn):
        """Verify first 10 rows sent, 11th excluded."""
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Summary.",)
        mock_conn.return_value.cursor.return_value = cursor

        rows = [{"IDX": i} for i in range(15)]
        summarize_analyst_results("test?", rows)

        prompt = cursor.execute.call_args[0][1][0]
        assert '"IDX": 9' in prompt
        assert '"IDX": 10' not in prompt

    @patch("app.snowflake_client._get_connection")
    def test_cursor_closed_on_success(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("OK.",)
        mock_conn.return_value.cursor.return_value = cursor

        summarize_analyst_results("test?", [{"X": 1}])
        cursor.close.assert_called_once()

    @patch("app.snowflake_client._get_connection")
    def test_cursor_closed_on_exception(self, mock_conn):
        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("boom")
        mock_conn.return_value.cursor.return_value = cursor

        with pytest.raises(RuntimeError):
            summarize_analyst_results("test?", [{"X": 1}])
        cursor.close.assert_called_once()


# ── query_mine_for_subregion edge cases ──────────────────────────────────────


class TestQueryMineForSubregionEdges:
    def _mock_row(self, **overrides):
        base = {
            "MINE_ID": 100,
            "MINE_NAME": "Test Mine",
            "MINE_OPERATOR": "Op",
            "MINE_COUNTY": "County",
            "MINE_STATE": "WV",
            "MINE_TYPE": "UG",
            "MINE_LATITUDE": 38.0,
            "MINE_LONGITUDE": -80.0,
            "PLANT_NAME": "Plant",
            "PLANT_OPERATOR": "PO",
            "PLANT_LATITUDE": 33.0,
            "PLANT_LONGITUDE": -80.0,
            "TOTAL_TONS": 1000.0,
            "DATA_YEAR": 2024,
            "FATALITIES": 0,
            "INJURIES_LOST_TIME": 0,
            "TOTAL_DAYS_LOST": 0,
        }
        base.update(overrides)
        return base

    @patch("app.snowflake_client._get_connection")
    def test_null_latitude_returns_none(self, mock_conn):
        """Row with NULL MINE_LATITUDE → returns None, not partial data."""
        cursor = MagicMock()
        cursor.fetchone.return_value = self._mock_row(MINE_LATITUDE=None)
        mock_conn.return_value.cursor.return_value = cursor

        result = query_mine_for_subregion("SRVC")
        assert result is None

    @patch("app.snowflake_client._get_connection")
    def test_null_total_tons_returns_none(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = self._mock_row(TOTAL_TONS=None)
        mock_conn.return_value.cursor.return_value = cursor

        result = query_mine_for_subregion("SRVC")
        assert result is None

    @patch("app.snowflake_client._get_connection")
    def test_null_stats_default_to_zero(self, mock_conn):
        """FATALITIES/INJURIES_LOST_TIME/TOTAL_DAYS_LOST as NULL → 0."""
        cursor = MagicMock()
        cursor.fetchone.return_value = self._mock_row(
            FATALITIES=None, INJURIES_LOST_TIME=None, TOTAL_DAYS_LOST=None
        )
        mock_conn.return_value.cursor.return_value = cursor

        result = query_mine_for_subregion("SRVC")
        assert result is not None
        assert result["fatalities"] == 0
        assert result["injuries"] == 0
        assert result["days_lost"] == 0

    @patch("app.snowflake_client._get_connection")
    def test_unknown_mine_type_defaults_to_surface(self, mock_conn):
        """Unknown MINE_TYPE code → 'Surface' label."""
        cursor = MagicMock()
        cursor.fetchone.return_value = self._mock_row(MINE_TYPE="XX")
        mock_conn.return_value.cursor.return_value = cursor

        result = query_mine_for_subregion("SRVC")
        assert result["mine_type"] == "Surface"

    @patch("app.snowflake_client._get_connection")
    def test_no_row_returns_none(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = cursor

        result = query_mine_for_subregion("NOPE")
        assert result is None

    @patch("app.snowflake_client._get_connection")
    def test_subregion_uppercased_in_query(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = self._mock_row()
        mock_conn.return_value.cursor.return_value = cursor

        query_mine_for_subregion("srvc")
        bind = cursor.execute.call_args[0][1]
        assert bind["subregion_id"] == "SRVC"

    @patch("app.snowflake_client._get_connection")
    def test_reconnect_on_first_failure(self, mock_conn):
        """First execute fails → reconnect → retry succeeds."""
        # First cursor raises
        bad_cursor = MagicMock()
        bad_cursor.execute.side_effect = RuntimeError("stale")

        # Reconnect cursor succeeds
        good_cursor = MagicMock()
        good_cursor.fetchone.return_value = self._mock_row()

        mock_conn.return_value.cursor.side_effect = [bad_cursor, good_cursor]

        with patch("app.snowflake_client._reconnect") as mock_reconnect:
            good_conn = MagicMock()
            good_conn.cursor.return_value = good_cursor
            mock_reconnect.return_value = good_conn

            result = query_mine_for_subregion("SRVC")

        assert result is not None
        assert result["mine"] == "Test Mine"
        mock_reconnect.assert_called_once()


# ── execute_analyst_sql edge cases ───────────────────────────────────────────


class TestExecuteAnalystSqlEdges:
    def test_alter_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("ALTER TABLE t ADD COLUMN x INT")

    def test_merge_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("MERGE INTO t USING s ON t.id = s.id")

    def test_copy_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("COPY INTO t FROM @stage")

    def test_execute_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("EXECUTE TASK my_task")

    @patch("app.snowflake_client._get_connection")
    def test_select_with_subquery_allowed(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchmany.return_value = [{"X": 1}]
        mock_conn.return_value.cursor.return_value = cursor

        result = execute_analyst_sql("SELECT * FROM (SELECT 1 AS X) sub WHERE X > 0")
        assert result == [{"X": 1}]

    @patch("app.snowflake_client._get_connection")
    def test_cte_with_multiple_selects_allowed(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchmany.return_value = [{"TOTAL": 5}]
        mock_conn.return_value.cursor.return_value = cursor

        sql = "WITH a AS (SELECT 1 AS X), b AS (SELECT 2 AS Y) SELECT COUNT(*) AS TOTAL FROM a, b"
        result = execute_analyst_sql(sql)
        assert result == [{"TOTAL": 5}]
