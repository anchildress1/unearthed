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

H3 hexbin design decision (Phase 2): cell IDs are computed at query time
via the ``h3`` library rather than pre-baked into the parquet. The raw
mines parquet carries lat/lng and Python aggregates into hexagons.
Pre-computing into the parquet would save a few milliseconds of CPU per
request but requires re-exporting whenever resolution tuning is considered.
At hobby-scale traffic the Python aggregation path is indistinguishable
from instant; the flexibility advantage of keeping resolution as a live
parameter outweighs the marginal runtime cost.
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


_MINE_TYPE_LABELS: dict[str, str] = {"U": "Underground", "S": "Surface", "F": "Facility"}

_MINE_FOR_SUBREGION_SQL = """
SELECT
    MINE_ID, MINE_NAME, MINE_OPERATOR, MINE_COUNTY, MINE_STATE, MINE_TYPE,
    MINE_LATITUDE, MINE_LONGITUDE,
    PLANT_NAME, PLANT_OPERATOR, PLANT_LATITUDE, PLANT_LONGITUDE,
    TOTAL_TONS, DATA_YEAR,
    FATALITIES, INJURIES_LOST_TIME, TOTAL_DAYS_LOST
FROM read_parquet(?)
WHERE EGRID_SUBREGION = ?
LIMIT 1
"""


def query_mine_for_subregion(subregion_id: str) -> dict | None:
    """Return the top mine-plant pair for a given eGRID subregion.

    Reads from ``mrt/mine_plant_for_subregion.parquet``. Returns ``None`` when no
    row matches the subregion or any required coordinate field is NULL.
    """
    con = _connection()
    result = con.execute(
        _MINE_FOR_SUBREGION_SQL,
        [_data_url("mrt/mine_plant_for_subregion"), subregion_id.upper()],
    )
    columns = [desc[0] for desc in result.description]
    row = result.fetchone()
    if not row:
        return None
    r = dict(zip(columns, row))

    for field in (
        "MINE_LATITUDE",
        "MINE_LONGITUDE",
        "PLANT_LATITUDE",
        "PLANT_LONGITUDE",
        "TOTAL_TONS",
        "DATA_YEAR",
    ):
        if r.get(field) is None:
            logger.error("NULL %s for subregion %s", field, subregion_id)
            return None

    return {
        "mine_id": str(r["MINE_ID"]),
        "mine": r["MINE_NAME"],
        "mine_operator": r["MINE_OPERATOR"],
        "mine_county": r["MINE_COUNTY"],
        "mine_state": r["MINE_STATE"],
        "mine_type": _MINE_TYPE_LABELS.get(r.get("MINE_TYPE") or "", "Surface"),
        "mine_coords": [float(r["MINE_LATITUDE"]), float(r["MINE_LONGITUDE"])],
        "plant": r["PLANT_NAME"],
        "plant_operator": r["PLANT_OPERATOR"],
        "plant_coords": [float(r["PLANT_LATITUDE"]), float(r["PLANT_LONGITUDE"])],
        "tons": float(r["TOTAL_TONS"]),
        "tons_year": int(r["DATA_YEAR"]),
        "fatalities": int(r.get("FATALITIES") or 0),
        "injuries": int(r.get("INJURIES_LOST_TIME") or 0),
        "days_lost": int(r.get("TOTAL_DAYS_LOST") or 0),
    }


# Bounding box mirrors the Snowflake original: continental US + mainland Alaska.
# Rejects (0,0) null-island entries and stray ocean coordinates MSHA's registry
# ships when a mine's address was never geocoded — without this, hexes land in
# the Atlantic and drag the viewport off the mainland.
_H3_MINES_SQL = """
SELECT LATITUDE, LONGITUDE, TRIM(CURRENT_MINE_STATUS) AS STATUS
FROM read_parquet(?)
WHERE COAL_METAL_IND = 'C'
  AND LATITUDE IS NOT NULL
  AND LONGITUDE IS NOT NULL
  AND LATITUDE BETWEEN 24 AND 72
  AND LONGITUDE BETWEEN -180 AND -65
"""

_H3_MINES_STATE_SQL = """
SELECT LATITUDE, LONGITUDE, TRIM(CURRENT_MINE_STATUS) AS STATUS
FROM read_parquet(?)
WHERE COAL_METAL_IND = 'C'
  AND LATITUDE IS NOT NULL
  AND LONGITUDE IS NOT NULL
  AND LATITUDE BETWEEN 24 AND 72
  AND LONGITUDE BETWEEN -180 AND -65
  AND STATE = ?
"""

# Registry totals intentionally omit the bounding-box filter so the count
# matches "MSHA has X coal mines on record" — not the subset with clean coords.
_H3_TOTALS_SQL = """
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) = 'Active' THEN 1 ELSE 0 END) AS active,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) != 'Active' THEN 1 ELSE 0 END) AS abandoned
FROM read_parquet(?)
WHERE COAL_METAL_IND = 'C'
"""

_H3_TOTALS_STATE_SQL = """
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) = 'Active' THEN 1 ELSE 0 END) AS active,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) != 'Active' THEN 1 ELSE 0 END) AS abandoned
FROM read_parquet(?)
WHERE COAL_METAL_IND = 'C'
  AND STATE = ?
"""


def query_h3_density(resolution: int, state: str | None = None) -> list[dict]:
    """Compute H3 hexbin density of coal mines aggregated at ``resolution``.

    Cell IDs are computed at query time using the ``h3`` library. The mines
    parquet carries lat/lng; Python aggregates into hexagons and applies the
    same min-cluster threshold the Snowflake query used (5 on the national
    view, 1 on state views so single-mine hexes appear on the focused map).
    The caller is responsible for validating ``resolution`` (2–7) and
    uppercasing ``state``.
    """
    import h3 as h3lib

    con = _connection()
    mines_url = _data_url("raw/msha_mines")
    if state:
        rows = con.execute(_H3_MINES_STATE_SQL, [mines_url, state]).fetchall()
    else:
        rows = con.execute(_H3_MINES_SQL, [mines_url]).fetchall()

    min_mines = 1 if state else 5
    cells: dict[str, dict] = {}
    for lat, lng, status in rows:
        cell_id = h3lib.latlng_to_cell(float(lat), float(lng), resolution)
        if cell_id not in cells:
            cells[cell_id] = {
                "H3": cell_id,
                "_lat_sum": 0.0,
                "_lng_sum": 0.0,
                "TOTAL": 0,
                "ACTIVE": 0,
                "ABANDONED": 0,
            }
        c = cells[cell_id]
        c["TOTAL"] += 1
        c["_lat_sum"] += float(lat)
        c["_lng_sum"] += float(lng)
        if status == "Active":
            c["ACTIVE"] += 1
        else:
            c["ABANDONED"] += 1

    result = []
    for c in cells.values():
        if c["TOTAL"] < min_mines:
            continue
        n = c["TOTAL"]
        result.append(
            {
                "H3": c["H3"],
                "LAT": c["_lat_sum"] / n,
                "LNG": c["_lng_sum"] / n,
                "TOTAL": n,
                "ACTIVE": c["ACTIVE"],
                "ABANDONED": c["ABANDONED"],
            }
        )
    result.sort(key=lambda x: x["TOTAL"], reverse=True)
    return result


def query_h3_registry_totals(state: str | None = None) -> dict:
    """Return unfiltered coal mine counts, optionally scoped to a state.

    Counts come from the full mines parquet without bounding-box or clustering
    filters so the number matches "MSHA has X coal mines on record" — not the
    subset that happens to render as hexes at the requested zoom level. The
    caller is responsible for uppercasing ``state``.
    """
    con = _connection()
    mines_url = _data_url("raw/msha_mines")
    if state:
        row = con.execute(_H3_TOTALS_STATE_SQL, [mines_url, state]).fetchone()
    else:
        row = con.execute(_H3_TOTALS_SQL, [mines_url]).fetchone()
    if not row:
        return {"total": 0, "active": 0, "abandoned": 0}
    return {
        "total": int(row[0] or 0),
        "active": int(row[1] or 0),
        "abandoned": int(row[2] or 0),
    }


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
