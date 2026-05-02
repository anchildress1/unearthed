import logging
import os
import re
import threading
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.routing import Match

from app.data_client import (
    normalize_plant_name,
    query_emissions_for_plant,
    query_h3_density,
    query_h3_registry_totals,
    query_mine_for_subregion,
)
from app.models import AskRequest, AskResponse, MineForMeRequest, MineForMeResponse
from app.prose_client import generate_h3_summary, generate_prose
from app.snowflake_client import (
    execute_analyst_sql,
    load_fallback_data,
    query_cortex_analyst,
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
    from app.config import get_settings

    s = get_settings()
    missing = [
        name
        for name, val in [
            ("SNOWFLAKE_ACCOUNT", s.snowflake_account),
            ("SNOWFLAKE_USER", s.snowflake_user),
            ("SNOWFLAKE_PRIVATE_KEY_PATH", s.snowflake_private_key_path),
        ]
        if not val
    ]
    if missing:
        logger.error(
            "Required environment variables not set: %s — Snowflake queries will fail.",
            ", ".join(missing),
        )
    if s.snowflake_private_key_path:
        key_path = Path(s.snowflake_private_key_path)
        if not key_path.exists():
            logger.error("Private key file not found: %s", key_path)
        elif key_path.stat().st_size == 0:
            logger.error("Private key file is empty (0 bytes): %s", key_path)

    if os.getenv("PREWARM_PROSE", "").lower() in ("1", "true"):
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


@app.get("/health")
def health():
    """Liveness probe for Cloud Run and smoke tests."""
    return {"status": "ok"}


# Wildcard is intentional when CORS_ORIGINS is unset — this is a public
# read-only API and the wildcard is the safe default for unauthenticated
# endpoints. Production deploys set CORS_ORIGINS to the actual domain.
_cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,  # nosemgrep
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' https://dev.to"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Static assets (images, data files)
_STATIC_DIR = _PROJECT_ROOT / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


_STATE_CODE_PATTERN = re.compile(r"^[A-Za-z]{2}$")


@app.get(
    "/h3-density",
    responses={
        400: {"description": "Invalid resolution (must be 2-7) or invalid state code"},
        503: {"description": "Data layer unavailable"},
    },
)
def h3_density(resolution: int = 4, state: str | None = None):
    """H3 hexbin mine density — active vs abandoned extraction footprint.

    Reads from ``raw/msha_mines.parquet`` via DuckDB. H3 cell IDs are computed
    at query time. When ``state`` is a 2-letter US state code, only mines in
    that state are returned and the small-cluster threshold drops to 1 so
    single-mine hexes still appear on the focused view.

    The Cortex Complete H3 summary still routes through Snowflake in Phase 2
    and will be replaced with a Claude-baked prose in Phase 3.
    """
    if resolution < 2 or resolution > 7:
        raise HTTPException(status_code=400, detail="Resolution must be 2-7")
    if state and not _STATE_CODE_PATTERN.match(state):
        raise HTTPException(status_code=400, detail="State must be a 2-letter code")

    normalized_state = state.upper() if state else None

    try:
        cells = query_h3_density(resolution, normalized_state)
        totals = query_h3_registry_totals(normalized_state)
    except Exception:
        logger.warning("H3 density query failed for resolution %s", resolution, exc_info=True)
        raise HTTPException(status_code=503, detail="Data layer unavailable")

    total = totals["total"]
    active = totals["active"]
    abandoned = totals["abandoned"]

    # Prose summary still routes through Snowflake Cortex Complete in Phase 2.
    # The degraded flag hides the "Cortex, on this map" byline when the
    # generator falls back to a template so the byline is never misattributed.
    summary = ""
    summary_degraded = False
    if total > 0:
        from app.config import settings

        try:
            summary, summary_degraded = generate_h3_summary(
                state=normalized_state,
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
        "cells": cells,
        "totals": {"total": total, "active": active, "abandoned": abandoned},
        "summary": summary,
        "summary_degraded": summary_degraded,
    }


_CACHE_MAXSIZE = 256

_emissions_cache: OrderedDict[str, dict] = OrderedDict()
_emissions_lock = threading.Lock()


@app.get(
    "/emissions/{plant_name}",
    responses={503: {"description": "Data layer unavailable"}},
)
def plant_emissions(plant_name: str):
    """EPA emissions data for a plant — pre-aggregated from EPA Clean Air Markets.

    Reads from a parquet file in Cloudflare R2 via DuckDB ``httpfs`` (or a
    local fixture parquet during tests, controlled by ``DATA_BASE_URL``).
    """
    cache_key = normalize_plant_name(plant_name)
    with _emissions_lock:
        if cache_key in _emissions_cache:
            _emissions_cache.move_to_end(cache_key)
            return _emissions_cache[cache_key]

    try:
        emissions = query_emissions_for_plant(plant_name)
    except Exception:
        logger.warning("Emissions query failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Data layer unavailable")

    if emissions is None:
        return {"plant": plant_name, "co2_tons": None, "so2_tons": None, "nox_tons": None}

    result = {
        "plant": plant_name,
        "co2_tons": emissions["co2_tons"],
        "so2_tons": emissions["so2_tons"],
        "nox_tons": emissions["nox_tons"],
        "source": "EPA Clean Air Markets",
    }
    with _emissions_lock:
        _emissions_cache[cache_key] = result
        if len(_emissions_cache) > _CACHE_MAXSIZE:
            _emissions_cache.popitem(last=False)
    return result


_GENERIC_SUGGESTIONS = [
    "How much has Bailey Mine produced since 2020?",
    "What other plants buy from Consol Pennsylvania Coal Company?",
    "Is Bailey Mine still active?",
    "What is the total coal tonnage for SRVC?",
    "Who is the largest coal supplier in Wyoming?",
]

_mine_context: OrderedDict[str, dict] = OrderedDict()
_mine_context_lock = threading.Lock()


def _suggestions_for(subregion_id: str | None) -> list[str]:
    """Build contextual suggestions from cached mine data for this subregion."""
    if not subregion_id:
        return _GENERIC_SUGGESTIONS
    with _mine_context_lock:
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
    """Return the top mine→plant shipment for an eGRID subregion.

    Falls back to bundled per-subregion JSON when Snowflake is unreachable;
    returns 404 only when both sources miss. Response schema is stable across
    the Cortex, fallback, and error paths — ``stats`` counts are always
    populated (0 means "none on file"), and ``degraded`` flips true when
    either the data layer or the prose layer had to degrade.
    """
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
    with _mine_context_lock:
        _mine_context[subregion] = mine_data
        if len(_mine_context) > _CACHE_MAXSIZE:
            _mine_context.popitem(last=False)
    prose, prose_degraded, stats = generate_prose(mine_data)
    degraded = degraded or prose_degraded

    return MineForMeResponse(
        mine=mine_data["mine"],
        mine_id=mine_data.get("mine_id"),
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
        fatalities=stats["fatalities"],
        injuries_lost_time=stats["injuries_lost_time"],
        days_lost=stats["days_lost"],
    )


def _summarize_analyst_rows(question: str, results: list[dict]) -> tuple[str | None, bool]:
    """Run Cortex Complete against Analyst rows; return ``(summary, degraded)``.

    ``degraded=True`` covers two indistinguishable user-facing failure modes:
    an exception from Cortex Complete, or a successful call that returned an
    empty string. Both leave rows on screen with no prose, and both require
    the frontend to hide the "Cortex, reading the record" byline so template
    silence isn't attributed to the model. Extracted from ``ask`` so the
    endpoint keeps its cognitive complexity under the project lint threshold.
    """
    try:
        summary = summarize_analyst_results(question, results)
    except Exception:
        logger.warning("Analyst summary generation failed", exc_info=True)
        return None, True
    if summary:
        return summary, False
    logger.warning("Analyst summary returned empty text")
    return None, True


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """Pass a natural-language question through Cortex Analyst.

    Three outcome branches:
    1. SQL generated → execute under the readonly role, optionally summarize
       the rows via Cortex Complete. Sets ``summary_degraded=True`` if the
       summary path raises so the frontend can hide the Cortex byline.
    2. No SQL, Cortex gave a conversational ``answer`` → return as-is.
    3. Upstream error (``query_cortex_analyst`` raised or returned ``error``)
       → return suggestions with an ``error`` message; no SQL, no results.

    ``suggestions`` is always populated (contextual if ``subregion_id`` is set,
    default otherwise) so the UI never dead-ends a user.
    """
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

    summary_degraded = False
    if results and not result.get("answer"):
        summary, summary_degraded = _summarize_analyst_rows(req.question, results)
        if summary:
            answer = summary

    suggestions = result.get("suggestions") or _suggestions_for(req.subregion_id)

    return AskResponse(
        answer=answer,
        interpretation=interpretation,
        sql=sql,
        error=error,
        suggestions=suggestions,
        results=results,
        summary_degraded=summary_degraded,
    )


# The SPA mount at "/" below is greedy: it matches any path the API routes
# haven't claimed. That means `GET /mine-for-me` (POST-only API route) would
# normally bypass Starlette's built-in 405 handling and get served by the SPA
# mount as a missing static file — which would return 404, not 405. This
# middleware runs before the mount is reached, checks every request against
# the registered APIRoute set, and surfaces the correct 405 (with an `Allow`
# header) when the path matches an API route but the method does not.
@app.middleware("http")
async def api_method_guard(request, call_next):
    # OPTIONS is reserved for the CORS preflight the CORSMiddleware below
    # intercepts; returning 405 here would swallow that handshake and break
    # browser-initiated POSTs from the frontend.
    if request.method == "OPTIONS":
        return await call_next(request)
    scope = request.scope
    matched_methods: set[str] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        match, _ = route.matches(scope)
        if match == Match.PARTIAL:
            # Path matched but method didn't — record what this route allows.
            matched_methods.update(route.methods or ())
        elif match == Match.FULL:
            matched_methods = set()
            break
    if matched_methods:
        return JSONResponse(
            status_code=405,
            content={"detail": "Method Not Allowed"},
            headers={"Allow": ", ".join(sorted(matched_methods))},
        )
    return await call_next(request)


# Serve SvelteKit build output in production (must be AFTER API routes).
_FRONTEND_DIR = _PROJECT_ROOT / "frontend" / "build"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
else:
    logger.warning(
        "Frontend build directory not found at %s — the SPA will not be served. "
        "This is expected in local dev (Vite serves the frontend), "
        "but signals a broken Dockerfile COPY in production.",
        _FRONTEND_DIR,
    )
