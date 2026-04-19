"""Generate mine prose using Snowflake Cortex.

Chain: Analyst pulls fatality/injury stats → Complete writes the grief.

Analyst asks about the mine's human cost — fatalities, injuries, days lost.
Complete takes those numbers and the mine data and writes prose that makes
the reader feel the weight. Not a data summary. An accusation with sources.

Falls back to a template if either service is unavailable.
"""

import json
import logging

from app.snowflake_client import (
    _get_connection,
    execute_analyst_sql,
    query_cortex_analyst,
)

logger = logging.getLogger(__name__)

# Cache: subregion_id -> prose string. TTL = until next deploy.
_prose_cache: dict[str, str] = {}

# Question for Analyst — pulls stats NOT on the page.
_ANALYST_QUESTION = (
    "For the mine with MSHA ID matching '{mine_name}' operated by "
    "'{mine_operator}': how many total fatalities, how many total injuries "
    "that caused days away from work, and how many total days of work were "
    "lost across all recorded accidents?"
)

# Prompt for Complete — turns numbers into grief.
_COMPLETE_PROMPT = """You are writing for a data visualization that shows people which coal mine
powers their home. The reader just learned that {mine_name} in {mine_county}, {mine_state}
sends {tons:,.0f} tons of coal per year to {plant_name} to keep their lights on.

Here are the human costs at this mine from federal MSHA records:
{facts}

Write 3-4 sentences. Rules:
- Present tense. This is happening now.
- Name the mine once. Do not repeat the operator name or plant name — those are already on screen.
- Lead with the human cost — deaths, injuries, days lost. Not tonnage.
- No acronyms. Say "federal mine safety records" not "MSHA."
- No hope. No silver linings. No "however." No hedging.
- End with the reader. Their electricity. Their demand.
- Short sentences. Each one is a verdict.
"""

_FALLBACK_TEMPLATE = (
    "{mine_name} has been extracting coal from {mine_county}, {mine_state} "
    "for your power grid. In {tons_year}, {tons:,.0f} tons moved from this "
    "mine to {plant_name}. The earth does not grow back."
)


def generate_prose(mine_data: dict) -> tuple[str, bool]:
    """Generate prose about a mine using Cortex Analyst + Complete.

    Returns (prose_text, degraded). Degraded is True if Cortex
    failed and a template fallback was used.
    """
    subregion_id = mine_data.get("subregion_id", "")

    if subregion_id and subregion_id in _prose_cache:
        return _prose_cache[subregion_id], False

    try:
        prose = _generate_from_cortex(mine_data)
        if subregion_id:
            _prose_cache[subregion_id] = prose
        return prose, False
    except Exception:
        logger.exception("Cortex prose generation failed, using fallback")
        prose = _fallback_prose(mine_data)
        if subregion_id:
            _prose_cache[subregion_id] = prose
        return prose, True


def _generate_from_cortex(mine_data: dict) -> str:
    """Analyst pulls the numbers. Complete writes the grief."""

    # Step 1: Ask Analyst for fatality/injury stats
    question = _ANALYST_QUESTION.format(
        mine_name=mine_data["mine"],
        mine_operator=mine_data["mine_operator"],
    )

    result = query_cortex_analyst(question)
    sql = result.get("sql")

    facts_text = "No accident records found for this mine."
    if sql:
        try:
            rows = execute_analyst_sql(sql)
            if rows:
                facts_text = json.dumps(rows[0], default=str)
        except Exception:
            logger.warning("Analyst SQL execution failed for prose stats")

    # Step 2: Feed facts to Complete
    prompt = _COMPLETE_PROMPT.format(
        mine_name=mine_data["mine"],
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        tons=mine_data["tons"],
        plant_name=mine_data["plant"],
        facts=facts_text,
    )

    conn = _get_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b', %s) AS prose",
                (prompt,),
            )
            row = cur.fetchone()
            if row and row[0]:
                prose = row[0].strip().strip('"')
                if prose:
                    return prose
        finally:
            cur.close()
    finally:
        conn.close()

    raise RuntimeError("Complete returned empty prose")


def _fallback_prose(mine_data: dict) -> str:
    return _FALLBACK_TEMPLATE.format(
        mine_name=mine_data["mine"],
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        plant_name=mine_data["plant"],
        tons_year=mine_data["tons_year"],
        tons=mine_data["tons"],
    )
