"""Generate mine prose using Snowflake Cortex Complete.

Safety stats (fatalities, injuries, days lost) arrive pre-aggregated
in the mine_data dict from the MINE_PLANT_FOR_SUBREGION MRT table.
Cortex Complete turns those numbers into prose.
"""

import logging

from app.snowflake_client import _get_connection

logger = logging.getLogger(__name__)

_prose_cache: dict[str, tuple[str, bool, dict]] = {}

_COMPLETE_PROMPT = """\
{plant_name} ({plant_operator}) received {tons} tons of coal in {tons_year} from \
{mine_name}, a {mine_type} mine ({mine_operator}) in {mine_county} County, {mine_state}. \
Safety record: {fatalities} deaths, {injuries} lost-time injuries, {days_lost} days lost.

Write a single paragraph, 3-5 sentences. This is a eulogy for the land and the \
workers — not a report. Name the plant, name the mine, say what it cost in human \
life. If a number is zero, leave it out entirely. Plain language, no hedging, no \
markdown. End on the reader: their lights stayed on because of this."""

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
                "SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b', %s)",
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
        injury_text = f"{args['injuries']} more were injured badly enough to miss work."
        days = int(str(args.get("days_lost", 0)).replace(",", "") or 0)
        if days:
            injury_text = injury_text[:-1] + f" — {args['days_lost']} days lost in total."
        parts.append(injury_text)
    parts.append("The coal kept moving to your grid.")
    return " ".join(parts)


def _stats_from(mine_data: dict) -> dict:
    """Extract the three MSHA stat fields surfaced on PlantReveal's cost block.

    The MRT table carries fatalities / injuries_lost_time / days_lost
    pre-aggregated. The UI treats 0 as "none on file" rather than "unknown," so
    a missing field is safe — the response schema stays stable either way. See
    ``MineForMeResponse.fatalities`` etc. — ``Field(default=0, ge=0)`` is the
    other half of the stability contract.
    """
    return {
        "fatalities": int(mine_data.get("fatalities") or 0),
        "injuries_lost_time": int(mine_data.get("injuries") or 0),
        "days_lost": int(mine_data.get("days_lost") or 0),
    }


def generate_prose(mine_data: dict) -> tuple[str, bool, dict]:
    """Generate memorial prose plus the safety stats the UI surfaces.

    Returns ``(prose, degraded, stats)``. ``stats`` is always a dict — never
    None — so the response schema stays stable across the Cortex, fallback,
    and error paths. Only Cortex-sourced prose is cached; a cached fallback
    would pin template copy under a "Cortex" byline after the model recovers.
    """
    subregion_id = mine_data.get("subregion_id", "")

    if subregion_id and subregion_id in _prose_cache:
        return _prose_cache[subregion_id]

    stats = _stats_from(mine_data)
    try:
        prose, degraded = _generate(mine_data)
        if subregion_id and not degraded:
            _prose_cache[subregion_id] = (prose, degraded, stats)
        return prose, degraded, stats
    except Exception:
        logger.exception("Prose generation failed")
        return _FALLBACK_NO_DATA, True, stats


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
