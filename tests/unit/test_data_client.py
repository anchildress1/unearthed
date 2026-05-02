"""Unit tests for ``app.data_client`` — the DuckDB boundary that replaces
the Snowflake data path for non-Cortex queries.

These tests run against a hand-built fixture parquet (see
``tests/fixtures/build_parquet.py``) so the data layer can be exercised
without a live Snowflake or R2 connection. Production behavior (R2 over
``httpfs``) is covered by the same SQL paths — only the parquet URL
changes between fixture and prod.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def data_client(tmp_path_factory, monkeypatch_module):
    """Reload ``app.data_client`` against a session-scoped fixture directory.

    The module caches the DuckDB connection at process scope, so we have to
    reset module state between test modules — otherwise the connection
    created by another module could outlive its fixture directory.
    """
    from tests.fixtures.build_parquet import write_emissions_fixture

    fixtures_root = tmp_path_factory.mktemp("data_client_fixtures")
    write_emissions_fixture(fixtures_root)

    monkeypatch_module.setenv("DATA_BASE_URL", str(fixtures_root))
    # Ensure no R2 secrets leak in from the developer's shell — the local
    # path mode must be exercised here, not the httpfs mode.
    monkeypatch_module.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch_module.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch_module.delenv("R2_ENDPOINT", raising=False)

    import app.data_client as module

    importlib.reload(module)
    yield module
    module._reset_connection()


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch — pytest's default is function-scoped."""
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


class TestQueryEmissionsForPlant:
    def test_exact_name_returns_row(self, data_client):
        result = data_client.query_emissions_for_plant("Cross")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(1000.0)
        assert result["so2_tons"] == pytest.approx(50.0)
        assert result["nox_tons"] == pytest.approx(30.0)

    def test_lowercase_name_matched(self, data_client):
        """Plant names are uppercased before LIKE — case-insensitive match."""
        result = data_client.query_emissions_for_plant("mitchell")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(500.0)

    def test_parenthetical_state_suffix_stripped(self, data_client):
        """EIA names carry trailing ``(TN)`` etc.; EPA's ``FACILITY_NAME`` does not.
        ``query_emissions_for_plant`` must bridge the gap before the LIKE."""
        result = data_client.query_emissions_for_plant("Cumberland (TN)")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(800.0)

    def test_prefix_match_resolves_longer_facility_name(self, data_client):
        """EPA names are sometimes longer than the EIA short name — ``Colstrip``
        in EIA, ``COLSTRIP ENERGY LP`` in EPA. Prefix LIKE bridges this."""
        result = data_client.query_emissions_for_plant("Colstrip")
        assert result is not None
        assert result["co2_tons"] == pytest.approx(2200.0)

    def test_unknown_plant_returns_none(self, data_client):
        result = data_client.query_emissions_for_plant("NonexistentPlant")
        assert result is None

    def test_empty_string_returns_none(self, data_client):
        """Empty inputs must not collapse the LIKE to ``%`` and return a
        random row — that would silently fabricate emissions data."""
        result = data_client.query_emissions_for_plant("")
        assert result is None

    def test_sql_injection_attempt_does_not_match(self, data_client):
        """Plant name flows through a parameterized bind — a SQL fragment
        passed as input must be treated as literal text, not executable SQL."""
        result = data_client.query_emissions_for_plant("' OR '1'='1")
        assert result is None


class TestNormalization:
    """The plant-name normalization helper is shared by the endpoint cache
    and the data client. Same logic, exercised in isolation so the cache
    key derivation can't drift from the LIKE prefix derivation."""

    def test_strips_trailing_state_suffix(self, data_client):
        assert data_client.normalize_plant_name("Cumberland (TN)") == "CUMBERLAND"

    def test_uppercases_alphabetic_input(self, data_client):
        assert data_client.normalize_plant_name("Bailey") == "BAILEY"

    def test_preserves_internal_parentheses_when_no_close_at_end(self, data_client):
        """Internal parens that aren't a trailing state suffix stay intact."""
        assert data_client.normalize_plant_name("Plant (Old) Site") == "PLANT (OLD) SITE"

    def test_empty_returns_empty(self, data_client):
        assert data_client.normalize_plant_name("") == ""
