import logging
import os
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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
    summarize_analyst_results,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_enable_docs = os.getenv("ENABLE_DOCS", "").lower() in ("1", "true")


def _prewarm_prose_cache() -> None:
    """Pre-warm the prose cache for all fallback subregions in a background thread.

    Each subregion fires a Snowflake query + Cortex Complete call, so the first
    visitor to any subregion gets a cached response instead of a 4-27s wait.
    Bails out entirely after the first failure — if Snowflake is unreachable
    there is no point hammering it 19 times.
    """
    from app.snowflake_client import _VALID_FALLBACK_IDS

    for subregion_id in _VALID_FALLBACK_IDS:
        try:
            mine_data = query_mine_for_subregion(subregion_id)
            if mine_data:
                mine_data = {**mine_data, "subregion_id": subregion_id}
                generate_prose(mine_data)
                logger.info("Pre-warmed prose cache for %s", subregion_id)
        except Exception:
            logger.warning("Pre-warm failed on %s — aborting remaining subregions", subregion_id)
            return


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    threading.Thread(target=_prewarm_prose_cache, daemon=True).start()
    yield


app = FastAPI(
    title="unearthed",
    version="0.1.0",
    lifespan=_lifespan,
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
    H3_LATLNG_TO_CELL_STRING(LATITUDE, LONGITUDE, {resolution}) AS h3,
    AVG(LATITUDE) AS lat,
    AVG(LONGITUDE) AS lng,
    COUNT(*) AS total,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) = 'Active'
        THEN 1 ELSE 0 END) AS active,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) != 'Active'
        THEN 1 ELSE 0 END) AS abandoned
FROM UNEARTHED_DB.RAW.MSHA_MINES
WHERE COAL_METAL_IND = 'C'
    AND LATITUDE IS NOT NULL
GROUP BY h3
HAVING total >= 5
ORDER BY total DESC
"""

_h3_cache: dict[int, list[dict]] = {}


@app.get("/h3-density", responses={400: {"description": "Invalid resolution (must be 2-7)"}})
def h3_density(resolution: int = 4):
    """H3 hexbin mine density — active vs abandoned extraction footprint."""
    if resolution < 2 or resolution > 7:
        raise HTTPException(status_code=400, detail="Resolution must be 2-7")

    cached = _h3_cache.get(resolution)
    if cached is not None:
        return {"resolution": resolution, "cells": cached}

    from app.config import settings

    conn = _get_connection(role=settings.snowflake_readonly_role)
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        cur.execute(_H3_DENSITY_SQL.format(resolution=int(resolution)))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
    _h3_cache[resolution] = rows
    return {"resolution": resolution, "cells": rows}


_EMISSIONS_SQL = """
SELECT CO2_TONS, SO2_TONS, NOX_TONS
FROM UNEARTHED_DB.MRT.EMISSIONS_BY_PLANT
WHERE FACILITY_NAME ILIKE %(plant_name)s
"""

_emissions_cache: dict[str, dict] = {}


@app.get("/emissions/{plant_name}")
def plant_emissions(plant_name: str):
    """EPA emissions data for a plant — pre-aggregated from Snowflake Marketplace."""
    cache_key = plant_name.upper()
    if cache_key in _emissions_cache:
        return _emissions_cache[cache_key]

    from app.config import settings

    conn = _get_connection(role=settings.snowflake_readonly_role)
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        cur.execute(_EMISSIONS_SQL, {"plant_name": plant_name + "%"})
        row = cur.fetchone()
    finally:
        cur.close()
    if not row or row.get("CO2_TONS") is None:
        result = {"plant": plant_name, "co2_tons": None, "so2_tons": None, "nox_tons": None}
    else:
        result = {
            "plant": plant_name,
            "co2_tons": float(row["CO2_TONS"] or 0),
            "so2_tons": float(row["SO2_TONS"] or 0),
            "nox_tons": float(row["NOX_TONS"] or 0),
            "source": "EPA Clean Air Markets via Snowflake Marketplace",
        }
    _emissions_cache[cache_key] = result
    return result


_GENERIC_SUGGESTIONS = [
    "How much has Bailey Mine produced since 2020?",
    "What other plants buy from Consol Pennsylvania Coal Company?",
    "Is Bailey Mine still active?",
    "What is the total coal tonnage for SRVC?",
    "Who is the largest coal supplier in Wyoming?",
]

_mine_context: dict[str, dict] = {}


def _suggestions_for(subregion_id: str | None) -> list[str]:
    """Build contextual suggestions from cached mine data for this subregion."""
    if not subregion_id:
        return _GENERIC_SUGGESTIONS
    ctx = _mine_context.get(subregion_id.upper())
    if not ctx:
        return _GENERIC_SUGGESTIONS
    mine = ctx["mine"]
    plant = ctx["plant"]
    state = ctx["mine_state"]
    return [
        f"How much has {mine} produced since 2020?",
        f"Which mines supplied {plant} in 2024?",
        f"Is {mine} still active?",
        f"What is the total coal tonnage for {subregion_id.upper()}?",
        f"Who is the largest coal supplier in {state}?",
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
    _mine_context[req.subregion_id.upper()] = mine_data
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
            suggestions=_suggestions_for(req.subregion_id),
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

    if results and not result.get("answer"):
        try:
            result["answer"] = summarize_analyst_results(req.question, results)
        except Exception:
            logger.debug("Analyst summary generation failed", exc_info=True)

    suggestions = result.get("suggestions") or _suggestions_for(req.subregion_id)

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
