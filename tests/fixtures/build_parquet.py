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
