"""Unit tests for app.prose_client.

The fallback sentence and prompt ordering are load-bearing editorial choices:
injuries land first (daily cost, bodily), fatalities land second (the weight
the injuries accumulate toward). These tests lock that order in.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.prose_client import (
    _COMPLETE_PROMPT,
    _FALLBACK_NO_DATA,
    _build_fallback,
    generate_prose,
)


class TestBuildFallback:
    def test_includes_all_nonzero_fields(self):
        out = _build_fallback(fatalities=3, injuries=42, days_lost=1200)
        assert "42" in out
        assert "1,200" in out
        assert "3" in out
        assert out.endswith("The coal kept moving to your grid.")

    def test_injuries_precede_fatalities(self):
        out = _build_fallback(fatalities=5, injuries=30, days_lost=800)
        assert out.index("30") < out.index("5 never came home")

    def test_skips_zero_fatalities(self):
        out = _build_fallback(fatalities=0, injuries=12, days_lost=50)
        assert "never came home" not in out
        assert "12" in out

    def test_skips_zero_injuries(self):
        out = _build_fallback(fatalities=2, injuries=0, days_lost=0)
        assert "hurt badly enough" not in out
        assert "2 never came home" in out

    def test_days_lost_formatted_with_commas(self):
        out = _build_fallback(fatalities=0, injuries=5, days_lost=12345)
        assert "12,345" in out


class TestCompletePrompt:
    def test_prompt_orders_injuries_before_fatalities(self):
        """Injuries must appear before fatalities in both the data bullets
        and the authoring instructions."""
        injuries_pos = _COMPLETE_PROMPT.index("{injuries}")
        fatalities_pos = _COMPLETE_PROMPT.index("{fatalities}")
        assert injuries_pos < fatalities_pos

    def test_prompt_carries_plant_and_mine_context(self):
        """The full-narrative prompt must receive plant + mine + tonnage fields so
        the agent can write all three paragraphs without frontend templating."""
        for placeholder in (
            "{plant_name}",
            "{plant_operator}",
            "{mine_name}",
            "{mine_operator}",
            "{mine_type}",
            "{tons",
        ):
            assert placeholder in _COMPLETE_PROMPT, f"missing {placeholder}"

    def test_prompt_requests_three_paragraphs(self):
        prompt_lower = _COMPLETE_PROMPT.lower()
        assert "3 short paragraphs" in _COMPLETE_PROMPT or "three paragraphs" in prompt_lower


class TestGenerateProse:
    @patch("app.prose_client._get_connection")
    def test_returns_fallback_when_no_data(self, mock_conn):
        """No accident rows (both counts zero) → _FALLBACK_NO_DATA, degraded=True."""
        cursor = MagicMock()
        cursor.fetchone.return_value = (0, 0, 0, 0)
        mock_conn.return_value.cursor.return_value = cursor

        prose, degraded = generate_prose(
            {
                "mine_id": "1234567",
                "mine": "Unnamed",
                "mine_county": "Nowhere",
                "mine_state": "XX",
                "subregion_id": "TEST1",
            }
        )
        assert prose == _FALLBACK_NO_DATA
        assert degraded is True

    @patch("app.prose_client._get_connection")
    def test_uses_template_when_complete_returns_empty(self, mock_conn):
        """Cortex Complete returns empty string → _build_fallback text, degraded=True."""
        # First cursor = stats, second = Cortex Complete.
        # Row shape: (incidents, fatalities, injuries, days_lost)
        stats_cursor = MagicMock()
        stats_cursor.fetchone.return_value = (100, 3, 40, 800)

        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = ("",)  # empty prose

        mock_conn.return_value.cursor.side_effect = [stats_cursor, complete_cursor]

        prose, degraded = generate_prose(
            {
                "mine_id": "9999999",
                "mine": "Test Mine",
                "mine_operator": "Test Op",
                "mine_county": "Test",
                "mine_state": "WV",
                "mine_type": "Surface",
                "plant": "Test Plant",
                "plant_operator": "Test Utility",
                "tons": 100000,
                "tons_year": 2024,
                "subregion_id": "TEST2",
            }
        )
        assert degraded is True
        # Must follow the injuries-first ordering
        assert prose.index("40") < prose.index("3 never came home")

    @patch("app.prose_client._get_connection")
    def test_uses_cortex_output_when_populated(self, mock_conn):
        stats_cursor = MagicMock()
        stats_cursor.fetchone.return_value = (50, 1, 20, 200)

        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = ('"Twenty workers here missed shifts this year."',)

        mock_conn.return_value.cursor.side_effect = [stats_cursor, complete_cursor]

        prose, degraded = generate_prose(
            {
                "mine_id": "7777777",
                "mine": "Another",
                "mine_operator": "Op",
                "mine_county": "Kanawha",
                "mine_state": "WV",
                "mine_type": "Underground",
                "plant": "Plant",
                "plant_operator": "Utility",
                "tons": 50000,
                "tons_year": 2024,
                "subregion_id": "TEST3",
            }
        )
        assert degraded is False
        # Outer quotes stripped
        assert prose == "Twenty workers here missed shifts this year."


class TestProseCache:
    @patch("app.prose_client._get_connection")
    def test_caches_successful_prose_by_subregion(self, mock_conn):
        """Second call for the same subregion must not re-query Snowflake."""
        from app import prose_client

        prose_client._prose_cache.clear()

        stats_cursor = MagicMock()
        stats_cursor.fetchone.return_value = (50, 1, 20, 200)
        complete_cursor = MagicMock()
        complete_cursor.fetchone.return_value = ("Cached prose.",)
        mock_conn.return_value.cursor.side_effect = [stats_cursor, complete_cursor]

        payload = {
            "mine_id": "1",
            "mine": "M",
            "mine_operator": "O",
            "mine_county": "C",
            "mine_state": "WV",
            "mine_type": "Surface",
            "plant": "P",
            "plant_operator": "U",
            "tons": 1000,
            "tons_year": 2024,
            "subregion_id": "CACHED",
        }
        first, _ = generate_prose(payload)
        second, _ = generate_prose(payload)
        assert first == second == "Cached prose."
        # Only the first call hit the cursor pipeline
        assert mock_conn.return_value.cursor.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
