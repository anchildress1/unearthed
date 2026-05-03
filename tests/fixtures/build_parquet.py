"""Builders for fixture parquet files used by data_client tests.

The test corpus is generated at session start rather than committed as binary
so reviewers can see what rows the assertions are reading against. Each
builder mirrors the shape of one Snowflake table or MRT view: columns and
casing match the Snowflake DDL so the same SQL works against the fixture
and the production R2-hosted file.
"""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def write_emissions_fixture(target_dir: Path) -> Path:
    """Write the EMISSIONS_BY_PLANT fixture parquet under ``target_dir/mrt/``.

    Mirrors ``UNEARTHED_DB.MRT.EMISSIONS_BY_PLANT`` — uppercase facility names,
    pre-aggregated CO2/SO2/NOx tons. EIA→EPA name normalization (parenthetical
    stripping) is the caller's concern; this fixture only stores EPA names.
    """
    table = pa.table(
        {
            "FACILITY_NAME": [
                "CROSS",
                "MITCHELL",
                "CUMBERLAND",
                "BAILEY",
                "COLSTRIP ENERGY LP",
            ],
            "CO2_TONS": [1000.0, 500.0, 800.0, 1500.0, 2200.0],
            "SO2_TONS": [50.0, 10.0, 25.0, 40.0, 60.0],
            "NOX_TONS": [30.0, 5.0, 15.0, 22.0, 35.0],
        }
    )
    out = target_dir / "mrt" / "emissions_by_plant.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out)
    return out


def write_mine_plant_for_subregion_fixture(target_dir: Path) -> Path:
    """Write the MINE_PLANT_FOR_SUBREGION fixture under ``target_dir/mrt/``.

    Mirrors ``UNEARTHED_DB.MRT.MINE_PLANT_FOR_SUBREGION`` — one row per eGRID
    subregion, joining the top mine-to-plant coal shipment with MSHA safety stats.
    Includes a NULL-coordinate row so callers can test the guard that rejects
    records with missing lat/lng.
    """
    table = pa.table(
        {
            "MINE_ID": pa.array([36609947, 12345678, 99999999], type=pa.int64()),
            "MINE_NAME": ["Bailey Mine", "Other Mine", "Null Coord Mine"],
            "MINE_OPERATOR": ["CONSOL Energy", "Alpha Natural Resources", "Unknown Operator"],
            "MINE_COUNTY": ["Greene", "Mingo", "Wayne"],
            "MINE_STATE": ["PA", "WV", "WV"],
            "MINE_TYPE": ["U", "S", "U"],
            "MINE_LATITUDE": pa.array([39.857, 37.654, None], type=pa.float64()),
            "MINE_LONGITUDE": pa.array([-80.166, -82.123, -82.0], type=pa.float64()),
            "PLANT_NAME": ["Cross", "Mitchell", "Phantom Plant"],
            "PLANT_OPERATOR": ["AEP", "TVA", "NoOp Utility"],
            "PLANT_LATITUDE": pa.array([33.786, 35.432, 35.0], type=pa.float64()),
            "PLANT_LONGITUDE": pa.array([-85.123, -87.654, -82.5], type=pa.float64()),
            "TOTAL_TONS": pa.array([1247001.0, 500000.0, 100000.0], type=pa.float64()),
            "DATA_YEAR": pa.array([2023, 2023, 2023], type=pa.int32()),
            "FATALITIES": pa.array([2, 0, 0], type=pa.int32()),
            "INJURIES_LOST_TIME": pa.array([15, 3, 0], type=pa.int32()),
            "TOTAL_DAYS_LOST": pa.array([430, 45, 0], type=pa.int32()),
            "EGRID_SUBREGION": ["SRVC", "RFCW", "NULL_LAT"],
        }
    )
    out = target_dir / "mrt" / "mine_plant_for_subregion.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out)
    return out


def write_msha_mines_fixture(target_dir: Path) -> Path:
    """Write the MSHA_MINES fixture under ``target_dir/raw/``.

    Mirrors ``UNEARTHED_DB.RAW.MSHA_MINES`` — one row per mine.
    Layout enables testing of:
    - Coal-only filter (COAL_METAL_IND = 'C' vs 'M')
    - US bounding-box filter (lat 24-72 / lng -180 to -65)
    - Active vs. Abandoned status aggregation
    - National vs. state-scoped density queries
    - min-cluster threshold difference (5 national, 1 state)

    Rows 0-5: WV coal mines in bbox — 4 Active, 2 Abandoned; all same H3 cell
    Rows 6-8: PA coal mines in bbox — 3 Active; same H3 cell
    Row 9:    PA coal mine at (0,0) — outside bbox, still counts in registry totals
    Row 10:   XX coal mine in UK — outside bbox (lng > -65)
    Row 11:   WV metal mine in bbox — excluded by COAL_METAL_IND='M'
    """
    lats = [37.501, 37.502, 37.499, 37.500, 37.503, 37.498, 40.001, 40.002, 39.999, 0.0, 51.5, 37.501]
    lngs = [-81.001, -81.002, -80.999, -81.000, -81.003, -80.998, -79.001, -79.002, -78.999, 0.0, -0.1, -81.001]
    statuses = ["Active", "Active", "Active", "Active", "Abandoned", "Abandoned",
                "Active", "Active", "Active", "Active", "Active", "Active"]
    coal_ind = ["C", "C", "C", "C", "C", "C", "C", "C", "C", "C", "C", "M"]
    states = ["WV", "WV", "WV", "WV", "WV", "WV", "PA", "PA", "PA", "PA", "XX", "WV"]

    table = pa.table(
        {
            "LATITUDE": pa.array(lats, type=pa.float64()),
            "LONGITUDE": pa.array(lngs, type=pa.float64()),
            "CURRENT_MINE_STATUS": statuses,
            "COAL_METAL_IND": coal_ind,
            "STATE": states,
        }
    )
    out = target_dir / "raw" / "msha_mines.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out)
    return out
