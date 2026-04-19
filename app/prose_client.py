"""Generate mine prose using Snowflake Cortex Complete.

Safety stats (fatalities, injuries, days lost) arrive pre-aggregated
in the mine_data dict from the MINE_PLANT_FOR_SUBREGION MRT table.
Cortex Complete turns those numbers into prose.
"""

import logging

from app.snowflake_client import _get_connection

logger = logging.getLogger(__name__)

_prose_cache: dict[str, tuple[str, bool]] = {}

_COMPLETE_PROMPT = """\
{plant_name} ({plant_operator}) received {tons} tons of coal in {tons_year} from \
{mine_name}, a {mine_type} mine ({mine_operator}) in {mine_county} County, {mine_state}. \
Safety record: {fatalities} deaths, {injuries} lost-time injuries, {days_lost} days lost.

Write a single paragraph, 3-5 sentences. This is a eulogy for the land and the \
workers — not a report. Name the plant, name the mine, say what it cost in human \
life. If a number is zero, leave it out entirely. Plain language, no hedging, no \
markdown. End on the reader: their lights stayed on because of this."""


def _build_fallback(args: dict) -> str:
    """Build fallback prose, omitting any zero safety stats."""
    parts = [
        f"{args['plant_name']} burns coal from {args['mine_name']}"
        f" in {args['mine_county']} County, {args['mine_state']}.",
        f"In {args['tons_year']}, {args['tons']} tons moved"
        f" from this {args['mine_type']} mine to that plant.",
    ]
    if args["fatalities"]:
        parts.append(f"{args['fatalities']} workers have died here.")
    if args["injuries"]:
        parts.append(
            f"{args['injuries']} more were injured badly enough"
            f" to miss work — {args['days_lost']} days lost in total."
        )
    parts.append("The coal kept moving to your grid.")
    return " ".join(parts)


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

    fatalities = int(mine_data.get("fatalities") or 0)
    injuries = int(mine_data.get("injuries") or 0)
    days_lost = int(mine_data.get("days_lost") or 0)

    format_args = {
        "mine_name": mine_data.get("mine", ""),
        "mine_operator": mine_data.get("mine_operator", ""),
        "mine_county": mine_data.get("mine_county", ""),
        "mine_state": mine_data.get("mine_state", ""),
        "mine_type": mine_data.get("mine_type", ""),
        "plant_name": mine_data.get("plant", ""),
        "plant_operator": mine_data.get("plant_operator", ""),
        "tons": f"{int(mine_data.get('tons', 0)):,}",
        "tons_year": mine_data.get("tons_year", ""),
        "fatalities": fatalities,
        "injuries": injuries,
        "days_lost": f"{days_lost:,}",
    }
    prompt = _COMPLETE_PROMPT.format(**format_args)

    cur2 = conn.cursor()
    try:
        cur2.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b', %s)",
            (prompt,),
        )
        result = cur2.fetchone()
        if result and result[0]:
            prose = result[0].strip().strip('"')
            if prose:
                return prose, False
    finally:
        cur2.close()

    logger.warning(
        "Cortex Complete returned empty for %s — using template fallback",
        mine_data.get("mine", "unknown"),
    )
    return _build_fallback(format_args), True
