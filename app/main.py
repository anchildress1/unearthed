import logging
import os
import re
from pathlib import Path

import snowflake.connector
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.models import AskRequest, AskResponse, MineForMeRequest, MineForMeResponse
from app.prose_client import generate_h3_summary, generate_prose
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
WITH clean AS (
    SELECT
        TRY_TO_DOUBLE(REPLACE(LATITUDE, '"', '')) AS lat_num,
        TRY_TO_DOUBLE(REPLACE(LONGITUDE, '"', '')) AS lng_num,
        TRIM(REPLACE(CURRENT_MINE_STATUS, '"', '')) AS status_txt,
        TRIM(REPLACE(STATE, '"', '')) AS state_txt,
        REPLACE(COAL_METAL_IND, '"', '') AS coal_txt
    FROM UNEARTHED_DB.RAW.MSHA_MINES
)
SELECT
    H3_LATLNG_TO_CELL_STRING(lat_num, lng_num, {resolution}) AS h3,
    AVG(lat_num) AS lat,
    AVG(lng_num) AS lng,
    COUNT(*) AS total,
    SUM(CASE WHEN status_txt = 'Active' THEN 1 ELSE 0 END) AS active,
    SUM(CASE WHEN status_txt != 'Active' THEN 1 ELSE 0 END) AS abandoned
FROM clean
-- Bounding box: continental US + mainland Alaska. Rejects (0,0) null-island
-- entries and stray ocean coordinates MSHA's registry occasionally ships when
-- a mine's address was never geocoded cleanly — without this, resolution-5
-- hexes land in the Atlantic and drag the viewport off the mainland.
-- Aleutian Islands west of the antimeridian (positive longitudes) are outside
-- this box on purpose: MSHA has no recorded coal mines there, and widening the
-- filter to wrap the dateline would re-admit the very ocean outliers we're
-- trying to drop.
WHERE coal_txt = 'C'
    AND lat_num IS NOT NULL
    AND lng_num IS NOT NULL
    AND lat_num BETWEEN 24 AND 72
    AND lng_num BETWEEN -180 AND -65
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
        state_clause = "AND state_txt = %(state)s"
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

    # Cortex-generated explanation of the density map. The whole point of this
    # site is that Cortex explains the data, so we always return a summary. The
    # generator returns a ``degraded`` flag when the template fallback fires
    # (Cortex unavailable or empty response); the endpoint surfaces that flag
    # so the frontend can hide the "Cortex, on this map" byline — showing
    # fallback prose under a model byline would misattribute the template to
    # Cortex. An unexpected ImportError/AttributeError here also counts as
    # degraded so the caller never sees the fallback masquerading as model output.
    total = sum(int(r.get("TOTAL") or 0) for r in rows)
    active = sum(int(r.get("ACTIVE") or 0) for r in rows)
    abandoned = sum(int(r.get("ABANDONED") or 0) for r in rows)
    summary = ""
    summary_degraded = False
    if total > 0:
        try:
            summary, summary_degraded = generate_h3_summary(
                state=(state.upper() if state else None),
                total=total,
                active=active,
                abandoned=abandoned,
            )
        except Exception:
            logger.exception("H3 summary generation crashed outside its own guard")
            summary = ""
            summary_degraded = True

    return {
        "resolution": resolution,
        "state": state,
        "cells": rows,
        "summary": summary,
        "summary_degraded": summary_degraded,
    }


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
    answer = result["answer"]

    if sql:
        try:
            results = execute_analyst_sql(sql)
        except Exception:
            logger.exception("Failed to execute Analyst SQL")
            error = (
                "We generated a query but could not execute it. "
                "Please try rephrasing your question."
            )
            answer = "I could not answer that confidently."
            interpretation = None
    else:
        # Cortex answered conversationally without producing SQL — log the question
        # so we can tighten the semantic model for patterns it's missing.
        logger.info("Cortex Analyst returned no SQL for question: %s", question)

    suggestions = result.get("suggestions") or DEFAULT_SUGGESTIONS

    return AskResponse(
        answer=answer,
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
