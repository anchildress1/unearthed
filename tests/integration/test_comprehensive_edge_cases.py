"""Comprehensive edge-case tests closing coverage gaps across all endpoints.

Covers: /ask, /mine-for-me, /h3-density, /emissions — positive, negative,
error, and edge scenarios identified in the full test audit.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import SAMPLE_MINE_DATA

_STATS = {"fatalities": 0, "injuries_lost_time": 0, "days_lost": 0}


# ── /ask edge cases ──────────────────────────────────────────────────────────


class TestAskZeroRowResults:
    """SQL executes successfully but returns an empty result set."""

    @patch("app.main.execute_analyst_sql", return_value=[])
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "Restating: how many?",
            "sql": "SELECT COUNT(*) FROM ...",
            "error": None,
        },
    )
    def test_zero_rows_skips_summary(self, mock_analyst, mock_exec, client):
        """Empty result set: no summary attempted, results=[] in response."""
        resp = client.post("/ask", json={"question": "How many mines in Guam?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        # Empty list is falsy → summary path skipped → answer stays ""
        assert data["summary_degraded"] is False

    @patch("app.main.summarize_analyst_results", return_value="One row found.")
    @patch("app.main.execute_analyst_sql", return_value=[{"MINE": "Bailey", "TONS": 42}])
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "Single row query.",
            "sql": "SELECT 1",
            "error": None,
        },
    )
    def test_single_row_result_summarized(self, mock_analyst, mock_exec, mock_sum, client):
        resp = client.post("/ask", json={"question": "Top mine?"})
        data = resp.json()
        assert data["answer"] == "One row found."
        assert len(data["results"]) == 1

    @patch("app.main.summarize_analyst_results", return_value="Multi-row summary.")
    @patch(
        "app.main.execute_analyst_sql",
        return_value=[{"MINE": f"Mine_{i}", "TONS": i * 100} for i in range(10)],
    )
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "Multi row query.",
            "sql": "SELECT TOP 10 ...",
            "error": None,
        },
    )
    def test_multi_row_results_all_returned(self, mock_analyst, mock_exec, mock_sum, client):
        resp = client.post("/ask", json={"question": "Top 10 mines?"})
        data = resp.json()
        assert len(data["results"]) == 10
        assert data["answer"] == "Multi-row summary."


class TestAskWhitespaceSummary:
    """Cortex returns whitespace-only summary — functionally empty."""

    @patch("app.main.summarize_analyst_results", return_value="   ")
    @patch("app.main.execute_analyst_sql", return_value=[{"X": 1}])
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "Restatement.",
            "sql": "SELECT 1",
            "error": None,
        },
    )
    def test_whitespace_summary_treated_as_truthy(self, mock_analyst, mock_exec, mock_sum, client):
        """Whitespace-only string is truthy in Python, so it passes the
        ``if summary:`` check and becomes the answer. This is acceptable —
        the strip is a Cortex responsibility, not the endpoint's."""
        resp = client.post("/ask", json={"question": "test"})
        data = resp.json()
        # The summary "   " is truthy so it replaces the empty answer
        assert data["answer"] == "   "
        assert data["summary_degraded"] is False


class TestAskResultsWithNullValues:
    """SQL results contain NULL values in some columns."""

    @patch("app.main.summarize_analyst_results", return_value="Summary with nulls.")
    @patch(
        "app.main.execute_analyst_sql",
        return_value=[{"MINE": "Bailey", "TONS": None, "STATUS": None}],
    )
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "Query with nulls.",
            "sql": "SELECT 1",
            "error": None,
        },
    )
    def test_null_values_in_results_serialized(self, mock_analyst, mock_exec, mock_sum, client):
        resp = client.post("/ask", json={"question": "test"})
        data = resp.json()
        assert data["results"][0]["TONS"] is None
        assert data["results"][0]["STATUS"] is None


class TestAskConversationalWithAnswer:
    """Cortex returns both answer and SQL — summary only runs if answer is empty."""

    @patch("app.main.execute_analyst_sql", return_value=[{"X": 1}])
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "Already have an answer.",
            "interpretation": "Restatement.",
            "sql": "SELECT 1",
            "error": None,
        },
    )
    def test_nonempty_answer_skips_summary(self, mock_analyst, mock_exec, client):
        """When Cortex already set answer, summary generation must not run."""
        resp = client.post("/ask", json={"question": "test"})
        data = resp.json()
        assert data["answer"] == "Already have an answer."
        assert data["summary_degraded"] is False


class TestAskInputEdges:
    """Boundary and unusual input validation for /ask."""

    def test_whitespace_only_question_accepted(self, client):
        """Whitespace-only passes min_length (3 chars) — Pydantic does not
        strip before validation. Cortex handles meaningless input gracefully."""
        with patch(
            "app.main.query_cortex_analyst",
            return_value={"answer": "", "interpretation": None, "sql": None, "error": None},
        ):
            resp = client.post("/ask", json={"question": "   "})
        assert resp.status_code == 200

    def test_punctuation_only_question_accepted(self, client):
        with patch(
            "app.main.query_cortex_analyst",
            return_value={"answer": "ok", "interpretation": None, "sql": None, "error": None},
        ):
            resp = client.post("/ask", json={"question": "???!!!"})
        assert resp.status_code == 200

    def test_subregion_with_trailing_spaces_rejected(self, client):
        """Subregion must match ^[A-Za-z0-9]{2,10}$ — trailing space fails."""
        resp = client.post("/ask", json={"question": "test", "subregion_id": "SRVC "})
        assert resp.status_code == 422

    def test_subregion_exactly_10_chars_accepted(self, client):
        with patch(
            "app.main.query_cortex_analyst",
            return_value={"answer": "ok", "interpretation": None, "sql": None, "error": None},
        ):
            resp = client.post("/ask", json={"question": "test", "subregion_id": "ABCDEFGHIJ"})
        assert resp.status_code == 200

    def test_subregion_11_chars_rejected(self, client):
        resp = client.post("/ask", json={"question": "test", "subregion_id": "ABCDEFGHIJK"})
        assert resp.status_code == 422


# ── /mine-for-me edge cases ──────────────────────────────────────────────────


class TestMineForMeLowercaseSubregion:
    """Lowercase subregion input gets uppercased internally."""

    @patch("app.main.generate_prose", return_value=("Prose.", False, _STATS))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_lowercase_subregion_uppercased(self, mock_sf, mock_prose, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "srvc"})
        assert resp.status_code == 200
        assert resp.json()["subregion_id"] == "SRVC"
        mock_sf.assert_called_once_with("SRVC")


class TestMineForMeContextCaching:
    """Verify mine context is stored for contextual suggestions."""

    @patch("app.main.generate_prose", return_value=("Prose.", False, _STATS))
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_mine_context_stored_after_success(self, mock_sf, mock_prose, client):
        from app.main import _mine_context

        _mine_context.clear()
        client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        assert "SRVC" in _mine_context
        assert _mine_context["SRVC"]["mine"] == "Bailey Mine"
        _mine_context.clear()


class TestMineForMeStatsAlwaysPresent:
    """Stats fields must always be present even when zero."""

    @patch(
        "app.main.generate_prose",
        return_value=("Prose.", False, {"fatalities": 0, "injuries_lost_time": 0, "days_lost": 0}),
    )
    @patch("app.main.query_mine_for_subregion", return_value=SAMPLE_MINE_DATA)
    def test_zero_stats_still_in_response(self, mock_sf, mock_prose, client):
        resp = client.post("/mine-for-me", json={"subregion_id": "SRVC"})
        data = resp.json()
        assert data["fatalities"] == 0
        assert data["injuries_lost_time"] == 0
        assert data["days_lost"] == 0


# ── /h3-density edge cases ───────────────────────────────────────────────────


class TestH3DensityResolutionBoundaries:
    """Resolution parameter boundary testing."""

    @patch("app.main.query_h3_registry_totals", return_value={"total": 0, "active": 0, "abandoned": 0})
    @patch("app.main.query_h3_density", return_value=[])
    def test_resolution_2_accepted(self, mock_density, mock_totals, client):
        resp = client.get("/h3-density?resolution=2")
        assert resp.status_code == 200
        assert resp.json()["resolution"] == 2

    @patch("app.main.query_h3_registry_totals", return_value={"total": 0, "active": 0, "abandoned": 0})
    @patch("app.main.query_h3_density", return_value=[])
    def test_resolution_7_accepted(self, mock_density, mock_totals, client):
        resp = client.get("/h3-density?resolution=7")
        assert resp.status_code == 200
        assert resp.json()["resolution"] == 7

    def test_resolution_1_rejected(self, client):
        resp = client.get("/h3-density?resolution=1")
        assert resp.status_code == 400

    def test_resolution_8_rejected(self, client):
        resp = client.get("/h3-density?resolution=8")
        assert resp.status_code == 400

    def test_resolution_0_rejected(self, client):
        resp = client.get("/h3-density?resolution=0")
        assert resp.status_code == 400

    def test_resolution_negative_rejected(self, client):
        resp = client.get("/h3-density?resolution=-1")
        assert resp.status_code == 400


class TestH3DensityStateValidation:
    """State parameter edge cases."""

    def test_three_char_state_rejected(self, client):
        resp = client.get("/h3-density?state=ABC")
        assert resp.status_code == 400

    def test_numeric_state_rejected(self, client):
        resp = client.get("/h3-density?state=12")
        assert resp.status_code == 400

    def test_single_char_state_rejected(self, client):
        resp = client.get("/h3-density?state=W")
        assert resp.status_code == 400

    @patch("app.main.query_h3_registry_totals", return_value={"total": 0, "active": 0, "abandoned": 0})
    @patch("app.main.query_h3_density", return_value=[])
    def test_empty_state_treated_as_national(self, mock_density, mock_totals, client):
        """Empty string state param is falsy — endpoint treats it as no-state filter."""
        resp = client.get("/h3-density?state=")
        assert resp.status_code == 200
        assert resp.json()["state"] == ""


class TestH3DensitySingleMine:
    """Single-mine scenario: total=1, active=1, abandoned=0."""

    @patch("app.main.generate_h3_summary", return_value=("One mine remains.", False))
    @patch("app.main.query_h3_registry_totals", return_value={"total": 1, "active": 1, "abandoned": 0})
    @patch("app.main.query_h3_density", return_value=[
        {"H3": "852a981ffffffff", "LAT": 37.5, "LNG": -82.6, "TOTAL": 1, "ACTIVE": 1, "ABANDONED": 0}
    ])
    def test_single_active_mine(self, mock_density, mock_totals, mock_summary, client):
        resp = client.get("/h3-density?resolution=5&state=AK")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["total"] == 1
        assert data["totals"]["active"] == 1
        assert data["totals"]["abandoned"] == 0


class TestH3DensityTotalsZero:
    """Zero-mine scenario: registry returns empty counts."""

    @patch("app.main.query_h3_registry_totals", return_value={"total": 0, "active": 0, "abandoned": 0})
    @patch("app.main.query_h3_density", return_value=[])
    def test_zero_totals_returns_zero_dict(self, mock_density, mock_totals, client):
        """When the registry is empty, response totals must be all-zero and
        summary must be skipped."""
        resp = client.get("/h3-density")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"] == {"total": 0, "active": 0, "abandoned": 0}
        assert data["summary"] == ""
        assert data["summary_degraded"] is False


# ── /emissions edge cases ────────────────────────────────────────────────────


class TestEmissionsParentheticalOnly:
    """Plant name normalization edge cases at the endpoint boundary.

    The data layer enforces "empty input returns None" — a stripped-to-empty
    name must not collapse into a wildcard ``LIKE '%'`` that fabricates data.
    """

    @patch("app.main.query_emissions_for_plant")
    def test_paren_only_name_returns_null_payload(self, mock_query, client):
        """``(TN)`` normalizes to empty — data client returns ``None`` —
        endpoint surfaces a null-emissions payload (not a 503, not a
        randomly-matched row)."""
        mock_query.return_value = None

        resp = client.get("/emissions/(TN)")
        assert resp.status_code == 200
        data = resp.json()
        assert data["co2_tons"] is None

    @patch("app.main.query_emissions_for_plant")
    def test_name_with_no_parens_passed_through_unchanged(self, mock_query, client):
        """Name without parens reaches the data client verbatim — the data
        client does the upper/strip itself."""
        mock_query.return_value = None

        client.get("/emissions/CrossStation")
        assert mock_query.call_args[0][0] == "CrossStation"


class TestEmissionsAllZero:
    """All emission values are 0.0 — row exists but zeroed."""

    @patch("app.main.query_emissions_for_plant")
    def test_all_zero_emissions_returned(self, mock_query, client):
        mock_query.return_value = {"co2_tons": 0.0, "so2_tons": 0.0, "nox_tons": 0.0}

        resp = client.get("/emissions/ZeroPlant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["co2_tons"] == pytest.approx(0.0)
        assert data["so2_tons"] == pytest.approx(0.0)
        assert data["nox_tons"] == pytest.approx(0.0)


class TestEmissionsPartialNull:
    """Row exists with CO2 but SO2/NOx coerced to zero by the data client."""

    @patch("app.main.query_emissions_for_plant")
    def test_partial_null_emissions_use_zero(self, mock_query, client):
        # Data client owns the None→0 coercion; the endpoint just relays.
        mock_query.return_value = {"co2_tons": 1000.0, "so2_tons": 0.0, "nox_tons": 0.0}

        resp = client.get("/emissions/PartialPlant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["co2_tons"] == pytest.approx(1000.0)
        assert data["so2_tons"] == pytest.approx(0.0)
        assert data["nox_tons"] == pytest.approx(0.0)


class TestEmissionsSource:
    """Emissions response includes a source attribution."""

    @patch("app.main.query_emissions_for_plant")
    def test_source_present_when_data_exists(self, mock_query, client):
        mock_query.return_value = {"co2_tons": 100.0, "so2_tons": 10.0, "nox_tons": 5.0}

        resp = client.get("/emissions/SourcePlant")
        data = resp.json()
        # EPA Clean Air Markets is the upstream regardless of how the bytes
        # reach us — Snowflake Marketplace was a transport detail that no
        # longer applies once we've baked the data into R2 parquet.
        assert "EPA" in data.get("source", "")

    @patch("app.main.query_emissions_for_plant")
    def test_no_source_when_no_data(self, mock_query, client):
        mock_query.return_value = None

        resp = client.get("/emissions/Missing")
        data = resp.json()
        assert "source" not in data


# ── HTTP method coverage ─────────────────────────────────────────────────────


class TestHttpMethodCoverage:
    """Methods not explicitly allowed should return 404 or 405."""

    def test_head_health_rejected(self, client):
        """HEAD not explicitly allowed — FastAPI rejects it."""
        resp = client.head("/health")
        assert resp.status_code in (404, 405)

    def test_patch_health_rejected(self, client):
        resp = client.patch("/health")
        assert resp.status_code in (404, 405)

    def test_put_ask_rejected(self, client):
        resp = client.put("/ask", json={"question": "test"})
        assert resp.status_code in (404, 405)

    def test_delete_health_rejected(self, client):
        resp = client.delete("/health")
        assert resp.status_code in (404, 405)

    def test_get_emissions_post_rejected(self, client):
        resp = client.post("/emissions/Test")
        assert resp.status_code in (404, 405)

    def test_post_h3_density_rejected(self, client):
        resp = client.post("/h3-density")
        assert resp.status_code in (404, 405)


# ── Security headers on non-200 responses ────────────────────────────────────


class TestSecurityHeadersOnErrors:
    """Security headers must be present even on 404/422/503."""

    def test_headers_on_422(self, client):
        resp = client.post("/ask", json={})
        assert resp.status_code == 422
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert "frame-ancestors" in resp.headers.get("Content-Security-Policy", "")

    def test_headers_on_404(self, client):
        resp = client.get("/nonexistent-route")
        assert resp.status_code == 404
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    @patch("app.main.query_h3_density", side_effect=Exception("R2 down"))
    def test_headers_on_503(self, mock_density, client):
        resp = client.get("/h3-density?resolution=4")
        assert resp.status_code == 503
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"


# ── Startup / lifespan edge cases ────────────────────────────────────────────


class TestPrewarmFlags:
    """PREWARM_PROSE accepts '1' and 'true', rejects others."""

    @patch("app.main.threading.Thread")
    def test_prewarm_enabled_with_1(self, mock_thread):
        import asyncio

        from app.main import _lifespan

        mock_instance = MagicMock()
        mock_thread.return_value = mock_instance

        async def _run():
            async with _lifespan(MagicMock()):
                ...

        with patch.dict("os.environ", {"PREWARM_PROSE": "1"}):
            asyncio.run(_run())

        mock_thread.assert_called_once()

    @patch("app.main.threading.Thread")
    def test_prewarm_disabled_with_false(self, mock_thread):
        import asyncio

        from app.main import _lifespan

        async def _run():
            async with _lifespan(MagicMock()):
                ...

        with patch.dict("os.environ", {"PREWARM_PROSE": "false"}):
            asyncio.run(_run())

        mock_thread.assert_not_called()

    @patch("app.main.threading.Thread")
    def test_prewarm_disabled_with_zero(self, mock_thread):
        import asyncio

        from app.main import _lifespan

        async def _run():
            async with _lifespan(MagicMock()):
                ...

        with patch.dict("os.environ", {"PREWARM_PROSE": "0"}):
            asyncio.run(_run())

        mock_thread.assert_not_called()

    @patch("app.main.threading.Thread")
    def test_prewarm_enabled_case_insensitive(self, mock_thread):
        import asyncio

        from app.main import _lifespan

        mock_instance = MagicMock()
        mock_thread.return_value = mock_instance

        async def _run():
            async with _lifespan(MagicMock()):
                ...

        with patch.dict("os.environ", {"PREWARM_PROSE": "TRUE"}):
            asyncio.run(_run())

        mock_thread.assert_called_once()
