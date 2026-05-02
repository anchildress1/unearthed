"""DuckDB read-only boundary against parquet files in Cloudflare R2.

Replaces the Snowflake data path for non-Cortex queries. All SQL lives in
this module — callers receive plain dicts. Three reasons to keep query
construction here:

1. Parameterized binds for every user-supplied value, mirroring the
   SELECT-only discipline of the old ``snowflake_client``.
2. The parquet URL is interpolated from env-controlled config; allowing
   callers to pass paths would widen the attack surface to no benefit.
3. Connection lifecycle (lazy ``httpfs`` install, R2 secret creation) is
   process-scoped state that should not leak to import sites.

Resolution: in production ``DATA_BASE_URL=s3://unearthed-data`` and the
R2 secrets must be set; locally and in tests ``DATA_BASE_URL`` points at a
filesystem directory containing the same parquet layout, and the R2
secrets are absent so ``httpfs`` is never loaded.
"""

from __future__ import annotations

import logging
import os
import threading

import duckdb

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None


def _data_base_url() -> str:
    """Where parquet files live. Trailing slash trimmed for clean joins."""
    return os.environ.get("DATA_BASE_URL", "").rstrip("/")


def _data_url(relative_path: str) -> str:
    """Build a fully-qualified parquet URL or filesystem path.

    ``relative_path`` is a layout-locked string (e.g. ``mrt/emissions_by_plant``)
    that callers do not control — never accept user input here.
    """
    base = _data_base_url()
    if not base:
        raise RuntimeError(
            "DATA_BASE_URL is not set — point it at the R2 prefix in production "
            "or at the test fixtures directory locally."
        )
    return f"{base}/{relative_path}.parquet"


def _connection() -> duckdb.DuckDBPyConnection:
    """Lazy, process-scoped DuckDB connection.

    First call installs ``httpfs`` and registers an R2 secret if R2
    credentials are present in the environment. Subsequent calls reuse the
    same connection — DuckDB is fast to open, but extension install + secret
    creation are not free, and they only need to happen once per process.
    """
    global _con
    with _lock:
        if _con is not None:
            return _con
        con = duckdb.connect(":memory:")
        if os.environ.get("R2_ACCESS_KEY_ID"):
            con.execute("INSTALL httpfs")
            con.execute("LOAD httpfs")
            con.execute(
                """
                CREATE OR REPLACE SECRET r2_data (
                    TYPE S3,
                    KEY_ID $key_id,
                    SECRET $secret,
                    ENDPOINT $endpoint,
                    URL_STYLE 'path',
                    REGION 'auto'
                )
                """,
                {
                    "key_id": os.environ["R2_ACCESS_KEY_ID"],
                    "secret": os.environ["R2_SECRET_ACCESS_KEY"],
                    # R2's S3 endpoint is the bucket-less host
                    # (``<account>.r2.cloudflarestorage.com``).
                    "endpoint": os.environ["R2_ENDPOINT"],
                },
            )
        _con = con
        return con


def _reset_connection() -> None:
    """Drop the cached connection. Tests use this to switch between fixture
    directories; production code never calls it."""
    global _con
    with _lock:
        if _con is not None:
            _con.close()
            _con = None


def normalize_plant_name(plant_name: str) -> str:
    """Bridge EIA → EPA plant-name conventions before the LIKE prefix match.

    EIA's 2024 receipts ship plant names with trailing parenthetical state
    suffixes — ``Cumberland (TN)``. EPA's ``FACILITY_NAME`` never does.
    Strip the suffix when present, then uppercase to match the EPA casing.
    Cache keys are derived from this same function so a hit on the cache
    and a hit on the parquet land at the same row.
    """
    if not plant_name:
        return ""
    idx = plant_name.rfind("(")
    if idx > 0 and plant_name.rstrip().endswith(")"):
        plant_name = plant_name[:idx].rstrip()
    return plant_name.upper()


_EMISSIONS_SQL = """
SELECT CO2_TONS, SO2_TONS, NOX_TONS
FROM read_parquet(?)
WHERE FACILITY_NAME LIKE ?
LIMIT 1
"""


def query_emissions_for_plant(plant_name: str) -> dict | None:
    """Return CO2/SO2/NOx tons for a plant, or ``None`` if not found.

    Plant name is normalized (parenthetical suffix stripped, uppercased)
    and used as a LIKE prefix to bridge EIA→EPA naming differences. Both
    the parquet URL and the LIKE pattern are bound as parameters — no
    string interpolation into the SQL. Empty inputs short-circuit to
    ``None`` so a stray ``LIKE '%'`` cannot return a random row that the
    caller would then surface as fact.
    """
    prefix = normalize_plant_name(plant_name)
    if not prefix:
        return None
    con = _connection()
    row = con.execute(
        _EMISSIONS_SQL,
        [_data_url("mrt/emissions_by_plant"), prefix + "%"],
    ).fetchone()
    if not row or row[0] is None:
        return None
    return {
        "co2_tons": float(row[0] or 0),
        "so2_tons": float(row[1] or 0),
        "nox_tons": float(row[2] or 0),
    }
