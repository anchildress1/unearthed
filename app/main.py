import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.gemini_client import generate_prose
from app.models import AskRequest, AskResponse, MineForMeRequest, MineForMeResponse
from app.snowflake_client import (
    load_fallback_data,
    query_cortex_analyst,
    query_mine_for_subregion,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="unearthed", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/mine-for-me", response_model=MineForMeResponse)
def mine_for_me(req: MineForMeRequest):
    degraded = False

    try:
        mine_data = query_mine_for_subregion(req.subregion_id)
    except Exception:
        logger.exception("Snowflake query failed, trying fallback")
        mine_data = load_fallback_data(req.subregion_id)
        degraded = True

    if not mine_data:
        mine_data = load_fallback_data(req.subregion_id)
        degraded = True

    if not mine_data:
        return MineForMeResponse(
            mine="Unknown",
            mine_operator="Unknown",
            mine_county="Unknown",
            mine_state="Unknown",
            mine_type="Surface",
            mine_coords=[0.0, 0.0],
            plant="Unknown",
            plant_operator="Unknown",
            plant_coords=[0.0, 0.0],
            tons=0,
            tons_year=2024,
            prose="No data available for this subregion.",
            subregion_id=req.subregion_id,
            degraded=True,
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
    try:
        result = query_cortex_analyst(req.question)
    except Exception:
        logger.exception("Cortex Analyst failed")
        return AskResponse(
            answer="",
            error="The data assistant is temporarily unavailable. Try one of the suggested questions.",
        )

    return AskResponse(
        answer=result["answer"],
        sql=result.get("sql"),
        error=result.get("error"),
    )
