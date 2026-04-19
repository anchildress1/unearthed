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
    SUM(CASE WHEN TRIM(DEGREE_INJURY) = 'FATALITY'
        THEN 1 ELSE 0 END) AS fatalities,
    SUM(CASE WHEN TRIM(DEGREE_INJURY) LIKE '%%DAYS%%'
        THEN 1 ELSE 0 END) AS injuries_lost_time,
    SUM(DAYS_LOST) AS total_days_lost
FROM UNEARTHED_DB.RAW.MSHA_ACCIDENTS
WHERE MINE_ID = %(mine_id)s
    AND COAL_METAL_IND = 'C'
"""

_COMPLETE_PROMPT = """You are writing 3 short paragraphs for a data visualization about US coal.

The reader just learned their electricity comes from {plant_name}, a power plant
operated by {plant_operator}. In {tons_year}, that plant received {tons} tons of
coal from {mine_name}, a {mine_type} mine operated by {mine_operator}
in {mine_county} County, {mine_state}.

Federal mine safety records for that mine — cumulative across MSHA's full electronic
accident record (roughly 1983 to present), not a recent window — show:
- {injuries} workers were injured badly enough to miss work
- {days_lost} total days of work lost to injury
- {fatalities} workers have died at this mine
- {incidents} total recorded safety incidents

Write exactly 3 short paragraphs, 1-2 sentences each, separated by a blank line.
Rules:
- Paragraph 1 grounds the reader: the plant and the grid relationship. You may
  name the plant once. Present tense for the ongoing relationship.
- Paragraph 2 is the mine and the shipment: name the tonnage, the operator, the
  county/state, the mine type. Anchor to the data year. Make the scale felt.
- Paragraph 3 is the human cost. Lead with injuries — bodily, specific, name the
  days lost. Make clear these are lifetime figures from MSHA's record. Land the
  fatalities second, as the weight the injuries accumulate toward. Last sentence
  connects the extraction back to the reader's electricity.
- No acronyms. No jargon. No hope. No hedging. No "however." No markdown.
- Do not repeat the data bullets verbatim — write prose that lets the numbers land.
- If a number is zero, do not mention it at all.
"""

_FALLBACK = (
    "{plant_name} takes coal from {mine_name} in {mine_county} County, {mine_state}. "
    "In {tons_year}, {tons} tons moved from this {mine_type} mine to that plant.\n\n"
    "{fatalities} workers have died here. {injuries} more were injured badly enough "
    "to miss work — {days_lost} days lost in total. "
    "The coal kept moving to your grid."
)

_FALLBACK_NO_DATA = "This mine ships coal to your power grid. The earth does not grow back."


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

    format_args = {
        "mine_name": mine_data["mine"],
        "mine_operator": mine_data.get("mine_operator", ""),
        "mine_county": mine_data["mine_county"],
        "mine_state": mine_data["mine_state"],
        "mine_type": mine_data.get("mine_type", ""),
        "plant_name": mine_data.get("plant", ""),
        "plant_operator": mine_data.get("plant_operator", ""),
        "tons": f"{int(mine_data.get('tons', 0)):,}",
        "tons_year": mine_data.get("tons_year", ""),
        "fatalities": fatalities,
        "injuries": injuries,
        "days_lost": f"{days_lost:,}",
        "incidents": incidents,
    }
    prompt = _COMPLETE_PROMPT.format(**format_args)

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
    return _FALLBACK.format(**format_args), True
