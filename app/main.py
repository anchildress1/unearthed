import logging
import os
import re
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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
            logger.warning(
                "Pre-warm failed on %s — aborting remaining subregions",
                subregion_id,
                exc_info=True,
            )
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
    H3_LATLNG_TO_CELL_STRING(LATITUDE, LONGITUDE, %(resolution)s) AS h3,
    AVG(LATITUDE) AS lat,
    AVG(LONGITUDE) AS lng,
    COUNT(*) AS total,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) = 'Active'
        THEN 1 ELSE 0 END) AS active,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) != 'Active'
        THEN 1 ELSE 0 END) AS abandoned
FROM UNEARTHED_DB.RAW.MSHA_MINES
-- Bounding box: continental US + mainland Alaska. Rejects (0,0) null-island
-- entries and stray ocean coordinates MSHA's registry occasionally ships when
-- a mine's address was never geocoded cleanly — without this, resolution-5
-- hexes land in the Atlantic and drag the viewport off the mainland.
-- Aleutian Islands west of the antimeridian (positive longitudes) are outside
-- this box on purpose: MSHA has no recorded coal mines there, and widening the
-- filter to wrap the dateline would re-admit the very ocean outliers we're
-- trying to drop.
WHERE COAL_METAL_IND = 'C'
    AND LATITUDE IS NOT NULL
    AND LONGITUDE IS NOT NULL
    AND LATITUDE BETWEEN 24 AND 72
    AND LONGITUDE BETWEEN -180 AND -65
    {state_clause}
GROUP BY h3
HAVING total >= {min_mines}
ORDER BY total DESC
"""

# Registry totals are computed independently of the hex-density query so the
# Cortex summary reads from "MSHA's full registry" rather than "the hexes the
# map happens to render at this resolution." The density query drops
# null-coord rows, ocean outliers, and small clusters (HAVING total >= 5 on
# the national view) — all sensible for rendering hexes, all wrong for a
# sentence that claims "MSHA has X coal mines on record." Sharing a state
# filter with the density query is fine because that IS a scoping choice the
# reader asked for; the bounding-box and clustering filters are not.
_H3_REGISTRY_TOTALS_SQL = """
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) = 'Active' THEN 1 ELSE 0 END) AS active,
    SUM(CASE WHEN TRIM(CURRENT_MINE_STATUS) != 'Active' THEN 1 ELSE 0 END) AS abandoned
FROM UNEARTHED_DB.RAW.MSHA_MINES
WHERE COAL_METAL_IND = 'C'
    {state_clause}
"""

_STATE_CODE_PATTERN = re.compile(r"^[A-Za-z]{2}$")


@app.get(
    "/h3-density",
    responses={
        400: {"description": "Invalid resolution (must be 2-7)"},
        503: {"description": "Snowflake unavailable"},
    },
)
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
    bind: dict[str, object] = {"resolution": int(resolution)}
    min_mines = 5
    if state:
        if not _STATE_CODE_PATTERN.match(state):
            raise HTTPException(status_code=400, detail="State must be a 2-letter code")
        state_clause = "AND STATE = %(state)s"
        bind["state"] = state.upper()
        min_mines = 1

    sql = _H3_DENSITY_SQL.format(
        state_clause=state_clause,
        min_mines=min_mines,
    )

    totals_sql = _H3_REGISTRY_TOTALS_SQL.format(state_clause=state_clause)

    try:
        conn = _get_connection(role=settings.snowflake_readonly_role)
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(sql, bind)
            rows = [dict(r) for r in cur.fetchall()]
            cur.execute(totals_sql, bind)
            totals_row = cur.fetchone() or {}
        finally:
            cur.close()
    except Exception:
        logger.warning("H3 density query failed for resolution %s", resolution, exc_info=True)
        raise HTTPException(status_code=503, detail="Snowflake unavailable")

    # Registry totals come from the unfiltered coal-mine registry (optionally
    # scoped to the requested state). Hex cells may drop rows — null coords,
    # ocean outliers, small-cluster HAVING threshold — but the Cortex summary
    # and the frontend legend must both report "MSHA has X mines on record"
    # honestly, not "X mines visible at this zoom."
    total = int(totals_row.get("TOTAL") or 0)
    active = int(totals_row.get("ACTIVE") or 0)
    abandoned = int(totals_row.get("ABANDONED") or 0)

    # Cortex-generated explanation of the density map. The whole point of this
    # site is that Cortex explains the data, so we always return a summary. The
    # generator returns a ``degraded`` flag when the template fallback fires
    # (Cortex unavailable or empty response); the endpoint surfaces that flag
    # so the frontend can hide the "Cortex, on this map" byline — showing
    # fallback prose under a model byline would misattribute the template to
    # Cortex. An unexpected ImportError/AttributeError here also counts as
    # degraded so the caller never sees the fallback masquerading as model output.
    summary = ""
    summary_degraded = False
    if total > 0:
        try:
            summary, summary_degraded = generate_h3_summary(
                state=(state.upper() if state else None),
                total=total,
                active=active,
                abandoned=abandoned,
                role=settings.snowflake_readonly_role,
            )
        except Exception:
            logger.exception("H3 summary generation crashed outside its own guard")
            summary = ""
            summary_degraded = True

    return {
        "resolution": resolution,
        "state": state,
        "cells": rows,
        "totals": {"total": total, "active": active, "abandoned": abandoned},
        "summary": summary,
        "summary_degraded": summary_degraded,
    }


_EMISSIONS_SQL = """
SELECT CO2_TONS, SO2_TONS, NOX_TONS
FROM UNEARTHED_DB.MRT.EMISSIONS_BY_PLANT
WHERE UPPER(FACILITY_NAME) = UPPER(%(plant_name)s)
"""

_emissions_cache: dict[str, dict] = {}


@app.get(
    "/emissions/{plant_name}",
    responses={503: {"description": "Snowflake unavailable"}},
)
def plant_emissions(plant_name: str):
    """EPA emissions data for a plant — pre-aggregated from Snowflake Marketplace."""
    cache_key = plant_name.upper()
    if cache_key in _emissions_cache:
        return _emissions_cache[cache_key]

    from app.config import settings

    try:
        conn = _get_connection(role=settings.snowflake_readonly_role)
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(_EMISSIONS_SQL, {"plant_name": plant_name})
            row = cur.fetchone()
        finally:
            cur.close()
    except Exception:
        logger.warning("Emissions query failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Snowflake unavailable")
    if not row or row.get("CO2_TONS") is None:
        return {"plant": plant_name, "co2_tons": None, "so2_tons": None, "nox_tons": None}
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


@app.post(
    "/mine-for-me",
    response_model=MineForMeResponse,
    responses={
        404: {
            "description": (
                "No mine-to-plant shipment is on record for the given subregion. "
                "Returned when both the Snowflake query and the bundled fallback "
                "JSON have no row for this eGRID subregion_id."
            ),
        },
    },
)
def mine_for_me(req: MineForMeRequest):
    subregion = req.subregion_id.upper()
    degraded = False
    mine_data = None

    try:
        mine_data = query_mine_for_subregion(subregion)
    except Exception:
        logger.warning("Snowflake query failed, trying fallback", exc_info=True)
        degraded = True

    if not mine_data:
        mine_data = load_fallback_data(subregion)
        degraded = True

    if not mine_data:
        raise HTTPException(
            status_code=404,
            detail=f"No coal data available for subregion '{subregion}'.",
        )

    mine_data = {**mine_data, "subregion_id": subregion}
    _mine_context[subregion] = mine_data
    prose, prose_degraded = generate_prose(mine_data)
    degraded = degraded or prose_degraded

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
        subregion_id=subregion,
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
    elif error:
        # Cortex Analyst itself failed upstream (timeout, 5xx, fallback
        # payload from `query_cortex_analyst`). Surface as a warning so it
        # doesn't get conflated with semantic-model coverage gaps below.
        logger.warning(
            "Cortex Analyst returned an error for question: %s; error: %s",
            question,
            error,
        )
    else:
        # Cortex answered conversationally without producing SQL — the
        # semantic model didn't match the question shape. Debug-level so
        # the signal is reviewable in logs without polluting info output.
        logger.debug("Cortex Analyst returned no SQL for question: %s", question)

    if results and not result.get("answer"):
        try:
            answer = summarize_analyst_results(req.question, results)
        except Exception:
            logger.warning("Analyst summary generation failed", exc_info=True)

    suggestions = result.get("suggestions") or _suggestions_for(req.subregion_id)

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
