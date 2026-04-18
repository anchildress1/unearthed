import logging
from pathlib import Path

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory cache: subregion_id -> (prose, degraded). TTL = until next deploy.
_prose_cache: dict[str, tuple[str, bool]] = {}

_PROMPT_TEMPLATE: str = (Path(__file__).parent.parent / "assets" / "gemini_prompt.txt").read_text()

_FALLBACK_TEMPLATE = (
    "In {mine_county}, {mine_state}, the {mine_type} operation known as {mine_name} "
    "— operated by {mine_operator} — shipped {tons_latest_year} tons of coal to "
    "{plant_name}, operated by {plant_operator}, in {tons_year}. "
    "The contract sustains the {subregion_id} grid."
)


def generate_prose(mine_data: dict) -> tuple[str, bool]:
    """Generate Gemini prose for a mine record.

    Returns (prose_text, degraded). Degraded is True if Gemini
    failed and a template fallback was used.
    """
    subregion_id = mine_data.get("subregion_id", "")

    if subregion_id and subregion_id in _prose_cache:
        return _prose_cache[subregion_id]

    prompt = _PROMPT_TEMPLATE.format(
        mine_name=mine_data["mine"],
        mine_operator=mine_data["mine_operator"],
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        mine_type=mine_data["mine_type"],
        plant_name=mine_data["plant"],
        plant_operator=mine_data["plant_operator"],
        tons_latest_year=f"{mine_data['tons']:,.0f}",
        tons_year=mine_data["tons_year"],
        subregion_id=subregion_id,
    )

    if not settings.gemini_api_key:
        logger.warning("No GEMINI_API_KEY configured, using fallback template")
        prose = _fallback_prose(mine_data)
        if subregion_id:
            _prose_cache[subregion_id] = (prose, True)
        return prose, True

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        if not response.text:
            logger.warning("Gemini returned empty response (possible safety filter)")
            prose = _fallback_prose(mine_data)
            if subregion_id:
                _prose_cache[subregion_id] = (prose, True)
            return prose, True
        prose = response.text.strip()
        if subregion_id:
            _prose_cache[subregion_id] = (prose, False)
        return prose, False
    except Exception:
        logger.exception("Gemini call failed, using fallback template")
        prose = _fallback_prose(mine_data)
        if subregion_id:
            _prose_cache[subregion_id] = (prose, True)
        return prose, True


def _fallback_prose(mine_data: dict) -> str:
    return _FALLBACK_TEMPLATE.format(
        mine_name=mine_data["mine"],
        mine_operator=mine_data["mine_operator"],
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        mine_type=mine_data["mine_type"].lower(),
        plant_name=mine_data["plant"],
        plant_operator=mine_data["plant_operator"],
        tons_latest_year=f"{mine_data['tons']:,.0f}",
        tons_year=mine_data["tons_year"],
        subregion_id=mine_data.get("subregion_id", ""),
    )
