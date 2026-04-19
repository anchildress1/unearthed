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

_COMPLETE_PROMPT = """Write a short data memorial—three paragraphs, 1-2 sentences
each, blank line between—for a US resident who just learned where their electricity
actually comes from.

FACTS (do not quote verbatim; weave them into prose)
Plant: {plant_name}, operated by {plant_operator}.
Source mine: {mine_name}, a {mine_type} mine operated by {mine_operator} in
{mine_county} County, {mine_state}.
Shipment: in {tons_year}, the plant received {tons:,} tons of coal from this mine.
This tonnage is the most recent full year of public data, not a live feed.
Federal mine safety record (MSHA, cumulative from roughly 1983 to present, not a
single year):
  incidents: {incidents}
  workers injured badly enough to miss shifts: {injuries}
  workdays lost to injury: {days_lost}
  workers killed: {fatalities}

VOICE
Bare facts, flat sentences. No hedging, no argument, no apology, no hope.
Verbs attach to the actor—the plant burns, the mine shipped, workers died.
Never blame the coal: coal doesn't act, burners do. Use past tense for the
shipment ("shipped", "burned", "received"); present tense for the grid
relationship. Do not use the words "still", "continues to", or "keeps"—they
imply the reader expected the activity to have stopped.

Between the deaths and the reader's electricity, no bridging phrase. Reject
"part of what", "helped power", "contributed to", "was the cost of", "helped
produce". Two flat facts, one period between them. The reader supplies the
connection.

If a number is zero, omit it entirely. No acronyms, no markdown, no headers,
no bullets, no paragraph labels. Em-dashes are tight ("word—word"), never
"word — word".

GOAL
Build from facts to emotion. Open with the grid relationship—plant, operator,
the reader's electricity—in plain present tense. Move to the shipment: the
mine, the tonnage, where it came from, in past tense anchored to the year.
Close on the human cost—the injuries, then the fatalities as a short bare
sentence of their own, then one flat fact about the reader's grid next to it.
The arc is concrete → scale → gut punch. Never lead with the deaths; let the
earlier facts do the work of setting them up so the final sentence lands.
Write prose that lets the numbers land; do not restate them as bullets.
"""

_FALLBACK_NO_DATA = "This mine ships coal to your power grid. The earth does not grow back."

_H3_SUMMARY_PROMPT = """You are writing ONE short paragraph (2-3 sentences) that explains a
coal-mine density map to a general reader. No jargon. No acronyms.

Scope:
{scope_line}

Numbers from MSHA's public mine registry:
- {total:,} coal mines on record
- {active:,} active (currently producing)
- {abandoned:,} closed / abandoned
- {active_pct}% of mines are active
- The {top_n_counties} counties with the most mines: {top_counties}

Rules:
- Lead with what the reader is looking at, then the scale (e.g. "most of these
  mines are already closed" or "this is where the industry cuts coal now").
- Do not use "still", "continues to", or "keeps"—they imply the reader was
  expecting the activity to have stopped. State what is.
- Quote the active-vs-abandoned ratio in plain English, not as a raw percentage
  unless it is the cleanest way to say it.
- If the numbers are cumulative across MSHA's full registry (roughly 1983 to
  present), say so—readers must not mistake the figure for a recent window.
- End on a sentence that grounds the reader: "what this map is telling you."
- No markdown, no bullets, no headers. Em-dashes are tight ("word—word"),
  never "word — word".
"""

_H3_SUMMARY_FALLBACK_STATE = (
    "In {state}, MSHA has {total:,} coal mines on record across its full registry "
    "(roughly 1983 to present). {abandoned:,} are already closed; {active:,} are "
    "active. What this map shows is the shape of an industry mostly in retreat—"
    "the rust dots are the few active mines, the ash dots are what the earth will "
    "not grow back."
)

_H3_SUMMARY_FALLBACK_NATIONAL = (
    "MSHA's full registry holds {total:,} US coal mines, roughly 1983 to present. "
    "{abandoned:,} are closed; {active:,} are active. Across the country the map "
    "is mostly ash—a map of what was, not what is."
)


# Only Cortex-sourced prose is cached. A cached fallback would pin the template
# under a "Cortex, on this map" byline long after Cortex recovers — for a site
# built around "the data must be explained by the model," that reads as a lie.
_h3_summary_cache: dict[str, str] = {}


def generate_h3_summary(
    *,
    state: str | None,
    total: int,
    active: int,
    abandoned: int,
    top_counties: list[str] | None = None,
    role: str | None = None,
) -> tuple[str, bool]:
    """Cortex-generated 2-3 sentence summary of the density map.

    Returns ``(text, degraded)``. ``degraded=True`` signals a hand-written
    fallback template fired because Cortex was unavailable — the caller must
    relabel or hide the "Cortex, on this map" byline so the site doesn't
    attribute template prose to the model. Cortex output is cached per scope;
    fallbacks are not, so a Cortex recovery shows up on the next request.

    ``role`` lets the caller scope the Snowflake connection to its own
    endpoint role (e.g. READONLY_ROLE for public endpoints). Without it, the
    default role from settings is used — which can bypass the least-privilege
    intent when ``/h3-density`` already opened a readonly cursor upstream.
    """
    cache_key = (state or "NATIONAL").upper()
    cached = _h3_summary_cache.get(cache_key)
    if cached is not None:
        return cached, False

    counties = top_counties or []
    active_pct = int(round((active / total) * 100)) if total else 0
    scope_line = (
        f"A map of coal mines in {state}." if state else "A map of coal mines across the US."
    )
    prompt = _H3_SUMMARY_PROMPT.format(
        scope_line=scope_line,
        total=total,
        active=active,
        abandoned=abandoned,
        active_pct=active_pct,
        top_n_counties=min(len(counties), 3) or 0,
        top_counties=", ".join(counties[:3]) if counties else "—",
    )

    try:
        conn = _get_connection(role=role)
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT SNOWFLAKE.CORTEX.COMPLETE('openai-gpt-5.2', %s)",
                (prompt,),
            )
            row = cur.fetchone()
        finally:
            cur.close()
        if row and row[0]:
            text = row[0].strip().strip('"').strip()
            if text:
                _h3_summary_cache[cache_key] = text
                return text, False
    except Exception:
        logger.exception("H3 summary generation failed—using fallback")

    fallback = (
        _H3_SUMMARY_FALLBACK_STATE.format(
            state=state, total=total, active=active, abandoned=abandoned
        )
        if state
        else _H3_SUMMARY_FALLBACK_NATIONAL.format(total=total, active=active, abandoned=abandoned)
    )
    return fallback, True


def _build_fallback(*, fatalities: int, injuries: int, days_lost: int) -> str:
    """Construct a deterministic fallback sentence—injuries first, fatalities second.

    Only emits clauses for non-zero numbers so we never read "0 workers died."
    All counts are cumulative across MSHA's full accident record (roughly 1983 to
    present), so the sentence spells that out rather than leaving a bare number
    that readers might mistake for a recent window. The closing line—
    "That is where your electricity was made."—is deliberately a flat fact set
    next to the death count with a period between them: the Cortex prompt
    enforces the same structure so the fallback and the generated prose land
    the same way.
    """
    parts: list[str] = []
    if injuries or days_lost or fatalities:
        parts.append("Across MSHA's full accident record for this mine:")
    if injuries:
        parts.append(f"{injuries:,} workers here were hurt badly enough to miss shifts.")
    if days_lost:
        parts.append(f"{days_lost:,} days of work lost to injury.")
    if fatalities:
        parts.append(f"{fatalities:,} were killed at this mine.")
    parts.append("That is where your electricity was made.")
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
        plant_name=mine_data.get("plant", ""),
        plant_operator=mine_data.get("plant_operator", ""),
        mine_name=mine_data["mine"],
        mine_operator=mine_data.get("mine_operator", ""),
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        mine_type=mine_data.get("mine_type", ""),
        tons=int(mine_data.get("tons", 0) or 0),
        tons_year=mine_data.get("tons_year", ""),
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

    # Complete returned empty—use template with real numbers (degraded)
    return _build_fallback(
        fatalities=fatalities,
        injuries=injuries,
        days_lost=days_lost,
    ), True
