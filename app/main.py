import logging
import os
import re
from pathlib import Path

import snowflake.connector
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.models import AskRequest, AskResponse, MineForMeRequest, MineForMeResponse
from app.prose_client import generate_prose
from app.snowflake_client import (
    _get_connection,
    execute_analyst_sql,
    load_fallback_data,
    query_cortex_analyst,
    query_mine_for_subregion,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_enable_docs = os.getenv("ENABLE_DOCS", "").lower() in ("1", "true")

app = FastAPI(
    title="unearthed",
    version="0.1.0",
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    openapi_url="/openapi.json" if _enable_docs else None,
)

_cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Static assets (images, data files)
_STATIC_DIR = _PROJECT_ROOT / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

_H3_DENSITY_SQL = """
SELECT
    H3_LATLNG_TO_CELL_STRING(
        TRY_TO_DOUBLE(REPLACE(LATITUDE, '"', '')),
        TRY_TO_DOUBLE(REPLACE(LONGITUDE, '"', '')),
        {resolution}
    ) AS h3,
    AVG(TRY_TO_DOUBLE(REPLACE(LATITUDE, '"', ''))) AS lat,
    AVG(TRY_TO_DOUBLE(REPLACE(LONGITUDE, '"', ''))) AS lng,
    COUNT(*) AS total,
    SUM(CASE WHEN TRIM(REPLACE(CURRENT_MINE_STATUS, '"', '')) = 'Active'
        THEN 1 ELSE 0 END) AS active,
    SUM(CASE WHEN TRIM(REPLACE(CURRENT_MINE_STATUS, '"', '')) != 'Active'
        THEN 1 ELSE 0 END) AS abandoned
FROM UNEARTHED_DB.RAW.MSHA_MINES
WHERE REPLACE(COAL_METAL_IND, '"', '') = 'C'
    AND TRY_TO_DOUBLE(REPLACE(LATITUDE, '"', '')) IS NOT NULL
    {state_clause}
GROUP BY h3
HAVING total >= {min_mines}
ORDER BY total DESC
"""

_STATE_CODE_PATTERN = re.compile(r"^[A-Za-z]{2}$")


@app.get("/h3-density", responses={400: {"description": "Invalid resolution (must be 2-7)"}})
def h3_density(resolution: int = 4, state: str | None = None):
    """H3 hexbin mine density — active vs abandoned extraction footprint.

    When ``state`` is a 2-letter US state code, only mines in that state are
    returned and the small-cluster HAVING threshold is dropped to 1 so a
    single-mine hex still shows up on the focused view.
    """
    if resolution < 2 or resolution > 7:
        raise HTTPException(status_code=400, detail="Resolution must be 2-7")
    from app.config import settings

    state_clause = ""
    bind: dict[str, object] = {}
    min_mines = 5
    if state:
        if not _STATE_CODE_PATTERN.match(state):
            raise HTTPException(status_code=400, detail="State must be a 2-letter code")
        state_clause = "AND TRIM(REPLACE(STATE, '\"', '')) = %(state)s"
        bind["state"] = state.upper()
        min_mines = 1

    sql = _H3_DENSITY_SQL.format(
        resolution=int(resolution),
        state_clause=state_clause,
        min_mines=min_mines,
    )

    conn = _get_connection(role=settings.snowflake_readonly_role)
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        cur.execute(sql, bind)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
    return {"resolution": resolution, "state": state, "cells": rows}


_EMISSIONS_SQL = """
SELECT
    SUM(CASE WHEN t.VARIABLE_NAME = 'Carbon Dioxide Mass, Short Tons (Quarterly)'
        THEN t.VALUE ELSE 0 END) AS co2_tons,
    SUM(CASE WHEN t.VARIABLE_NAME = 'Sulfur Dioxide Mass, Short Tons (Quarterly)'
        THEN t.VALUE ELSE 0 END) AS so2_tons,
    SUM(CASE WHEN t.VARIABLE_NAME = 'Nitrogen Oxide Mass, Short Tons (Quarterly)'
        THEN t.VALUE ELSE 0 END) AS nox_tons
FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.EPA_CAM_PLANT_UNIT_INDEX p
JOIN SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.EPA_CAM_TIMESERIES t
    ON p.PLANT_UNIT_ID = t.PLANT_UNIT_ID
WHERE p.FACILITY_NAME ILIKE %(plant_name)s
    AND p.PRIMARY_FUEL_INFO = 'Coal'
    AND t.VARIABLE_NAME IN (
        'Carbon Dioxide Mass, Short Tons (Quarterly)',
        'Sulfur Dioxide Mass, Short Tons (Quarterly)',
        'Nitrogen Oxide Mass, Short Tons (Quarterly)'
    )
    AND t.DATE >= '2020-01-01'
"""


@app.get("/emissions/{plant_name}")
def plant_emissions(plant_name: str):
    """EPA emissions data for a plant — from Snowflake Marketplace (free)."""
    from app.config import settings

    conn = _get_connection(role=settings.snowflake_readonly_role)
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        cur.execute(_EMISSIONS_SQL, {"plant_name": plant_name + "%"})
        row = cur.fetchone()
    finally:
        cur.close()
    if not row or row.get("CO2_TONS") is None:
        return {"plant": plant_name, "co2_tons": None, "so2_tons": None, "nox_tons": None}
    return {
        "plant": plant_name,
        "co2_tons": float(row["CO2_TONS"] or 0),
        "so2_tons": float(row["SO2_TONS"] or 0),
        "nox_tons": float(row["NOX_TONS"] or 0),
        "source": "EPA Clean Air Markets via Snowflake Marketplace",
    }


DEFAULT_SUGGESTIONS = [
    "How much has Bailey Mine produced since 2020?",
    "What other plants buy from Consol Pennsylvania Coal Company?",
    "Is Bailey Mine still active?",
    "What is the total coal tonnage for SRVC?",
    "Who is the largest coal supplier in Wyoming?",
]


@app.post("/mine-for-me", response_model=MineForMeResponse)
def mine_for_me(req: MineForMeRequest):
    degraded = False
    mine_data = None

    try:
        mine_data = query_mine_for_subregion(req.subregion_id)
    except Exception:
        logger.exception("Snowflake query failed, trying fallback")
        degraded = True

    if not mine_data:
        mine_data = load_fallback_data(req.subregion_id)
        degraded = True

    if not mine_data:
        raise HTTPException(
            status_code=404,
            detail=f"No coal data available for subregion '{req.subregion_id}'.",
        )

    mine_data = {**mine_data, "subregion_id": req.subregion_id}
    prose, gemini_degraded = generate_prose(mine_data)
    degraded = degraded or gemini_degraded

    return MineForMeResponse(
        mine=mine_data["mine"],
        mine_operator=mine_data["mine_operator"],
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        mine_type=mine_data["mine_type"],
        mine_coords=mine_data["mine_coords"],
        plant=mine_data["plant"],
        plant_operator=mine_data["plant_operator"],
        plant_coords=mine_data["plant_coords"],
        tons=mine_data["tons"],
        tons_year=mine_data["tons_year"],
        prose=prose,
        subregion_id=req.subregion_id,
        degraded=degraded,
    )


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    question = req.question
    if req.subregion_id:
        question = f"{req.question} (for eGRID subregion {req.subregion_id})"

    try:
        result = query_cortex_analyst(question)
    except Exception:
        logger.exception("Cortex Analyst query failed")
        return AskResponse(
            answer="",
            error="The data assistant is temporarily unavailable. "
            "Try one of the suggested questions.",
            suggestions=DEFAULT_SUGGESTIONS,
        )

    results = None
    error = result.get("error")
    sql = result.get("sql")
    interpretation = result["interpretation"]
    if sql:
        try:
            results = execute_analyst_sql(sql)
        except Exception:
            logger.exception("Failed to execute Analyst SQL")
            error = (
                "We generated a query but could not execute it. "
                "Please try rephrasing your question."
            )
            result["answer"] = "I could not answer that confidently."
            interpretation = None

    suggestions = result.get("suggestions") or DEFAULT_SUGGESTIONS

    return AskResponse(
        answer=result["answer"],
        interpretation=interpretation,
        sql=sql,
        error=error,
        suggestions=suggestions,
        results=results,
    )


# Serve SvelteKit build output in production (must be AFTER API routes).
_FRONTEND_DIR = _PROJECT_ROOT / "frontend" / "build"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
