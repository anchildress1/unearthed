"""Generate mine prose using Snowflake Cortex Complete.

Direct SQL pulls fatality/injury stats from MSHA_ACCIDENTS by MINE_ID.
Cortex Complete turns those numbers into prose.
"""

import logging

from app.snowflake_client import _get_connection

logger = logging.getLogger(__name__)

_prose_cache: dict[str, tuple[str, bool]] = {}

_STATS_SQL = """
SELECT
    COUNT(*) AS total_incidents,
    SUM(CASE WHEN TRIM(REPLACE(DEGREE_INJURY, '"', '')) = 'FATALITY'
        THEN 1 ELSE 0 END) AS fatalities,
    SUM(CASE WHEN TRIM(REPLACE(DEGREE_INJURY, '"', '')) LIKE '%%DAYS%%'
        THEN 1 ELSE 0 END) AS injuries_lost_time,
    SUM(TRY_TO_NUMBER(REPLACE(DAYS_LOST, '"', ''))) AS total_days_lost
FROM UNEARTHED_DB.RAW.MSHA_ACCIDENTS
WHERE TRY_TO_NUMBER(REPLACE(MINE_ID, '"', '')) = %(mine_id)s
    AND REPLACE(COAL_METAL_IND, '"', '') = 'C'
"""

_COMPLETE_PROMPT = """You are writing 2-3 sentences for a data visualization about US coal.
The reader just learned their electricity comes from {mine_name} in {mine_county}, {mine_state}.

Federal mine safety records show:
- {injuries} workers were injured badly enough to miss work
- {days_lost} total days of work lost to injury
- {fatalities} workers have died at this mine
- {incidents} total recorded safety incidents

Write 2-3 SHORT sentences. Rules:
- Present tense. This is happening now.
- Lead with the injuries — these are daily, specific, bodily. Name days lost.
- Land the fatalities second, as the weight the injuries accumulate toward.
- No acronyms. No jargon.
- No hope. No hedging. No "however."
- Last sentence connects to the reader's electricity.
- Do NOT name the mine or operator — those are already on screen.
"""

_FALLBACK_NO_DATA = "This mine ships coal to your power grid. The earth does not grow back."


def _build_fallback(*, fatalities: int, injuries: int, days_lost: int) -> str:
    """Construct a deterministic fallback sentence — injuries first, fatalities second.

    Only emits clauses for non-zero numbers so we never read "0 never came home."
    """
    parts: list[str] = []
    if injuries:
        parts.append(f"{injuries:,} workers here were hurt badly enough to miss shifts.")
    if days_lost:
        parts.append(f"{days_lost:,} days of work lost to injury.")
    if fatalities:
        parts.append(f"{fatalities:,} never came home.")
    parts.append("The coal kept moving to your grid.")
    return " ".join(parts)


def generate_prose(mine_data: dict) -> tuple[str, bool]:
    subregion_id = mine_data.get("subregion_id", "")

    if subregion_id and subregion_id in _prose_cache:
        return _prose_cache[subregion_id]

    try:
        prose, degraded = _generate(mine_data)
        if subregion_id and not degraded:
            _prose_cache[subregion_id] = (prose, degraded)
        return prose, degraded
    except Exception:
        logger.exception("Prose generation failed")
        return _FALLBACK_NO_DATA, True


def _generate(mine_data: dict) -> tuple[str, bool]:
    """Returns (prose, degraded). degraded=True if Complete failed."""
    conn = _get_connection()

    cur = conn.cursor()
    try:
        cur.execute(_STATS_SQL, {"mine_id": int(mine_data["mine_id"])})
        row = cur.fetchone()
    finally:
        cur.close()

    if not row:
        return _FALLBACK_NO_DATA, True

    fatalities = int(row[1] or 0)
    injuries = int(row[2] or 0)
    days_lost = int(row[3] or 0)
    incidents = int(row[0] or 0)

    if fatalities == 0 and injuries == 0:
        return _FALLBACK_NO_DATA, True

    prompt = _COMPLETE_PROMPT.format(
        mine_name=mine_data["mine"],
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        fatalities=fatalities,
        injuries=injuries,
        days_lost=f"{days_lost:,}",
        incidents=incidents,
    )

    cur2 = conn.cursor()
    try:
        cur2.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE('openai-gpt-5.2', %s)",
            (prompt,),
        )
        result = cur2.fetchone()
        if result and result[0]:
            prose = result[0].strip().strip('"')
            if prose:
                return prose, False
    finally:
        cur2.close()

    # Complete returned empty — use template with real numbers (degraded)
    return _build_fallback(
        fatalities=fatalities,
        injuries=injuries,
        days_lost=days_lost,
    ), True
