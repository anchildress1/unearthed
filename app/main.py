import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.gemini_client import generate_prose
from app.models import AskRequest, AskResponse, MineForMeRequest, MineForMeResponse
from app.snowflake_client import (
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


@app.get("/")
def index():
    return FileResponse(_PROJECT_ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=_PROJECT_ROOT / "static"), name="static")

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

    suggestions = result.get("suggestions") or DEFAULT_SUGGESTIONS

    return AskResponse(
        answer=result["answer"],
        sql=sql,
        error=error,
        suggestions=suggestions,
        results=results,
    )
