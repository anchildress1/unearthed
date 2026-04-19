"""Generate mine prose using Snowflake Cortex Analyst.

Asks Cortex for stats NOT already on the page — worker counts,
total lifetime production, plant count — then formats them into
prose that makes the reader feel the weight of the numbers.

Falls back to a template if Cortex is unavailable.
"""

import logging

from app.snowflake_client import execute_analyst_sql, query_cortex_analyst

logger = logging.getLogger(__name__)

# Cache: subregion_id -> prose string. TTL = until next deploy.
_prose_cache: dict[str, str] = {}

# The question we ask Cortex to get stats for the prose.
# Pulls data the user does NOT already see on the page:
# - avg employees at the mine
# - total hours worked
# - total lifetime production (all years)
# - number of plants this mine ships to
_CORTEX_QUESTION = (
    "For the mine named '{mine_name}' operated by '{mine_operator}' in {mine_state}, "
    "tell me: how many employees work there on average, how many total hours were "
    "worked in the most recent year, what is the total coal production across all years, "
    "and how many different power plants does this mine ship coal to?"
)

_PROSE_TEMPLATE = (
    "{avg_employees} people clock in at {mine_name} every day. "
    "In {tons_year} alone they logged {hours_worked} hours underground to pull "
    "{tons_latest:,.0f} tons of coal out of {mine_county}, {mine_state}. "
    "Since records began, this single mine has produced {lifetime_tons:,.0f} tons. "
    "It feeds {plant_count} power plant{plant_s}. Yours is one of them."
)

_FALLBACK_TEMPLATE = (
    "{mine_name} in {mine_county}, {mine_state} is being {verb} by {mine_operator} "
    "to feed {plant_name}. In {tons_year}, {tons_latest:,.0f} tons of coal moved "
    "from this mine to your grid. The earth does not grow back."
)

_VERB_BY_MINE_TYPE: dict[str, str] = {
    "Surface": "stripped",
    "Underground": "hollowed out",
    "Facility": "excavated",
}


def generate_prose(mine_data: dict) -> tuple[str, bool]:
    """Generate prose about a mine using Cortex Analyst data.

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
    """Ask Cortex Analyst for mine stats and format into prose."""
    question = _CORTEX_QUESTION.format(
        mine_name=mine_data["mine"],
        mine_operator=mine_data["mine_operator"],
        mine_state=mine_data["mine_state"],
    )

    result = query_cortex_analyst(question)

    if result.get("error") or not result.get("sql"):
        raise RuntimeError("Cortex did not generate SQL for prose query")

    rows = execute_analyst_sql(result["sql"])
    if not rows:
        raise RuntimeError("Cortex SQL returned no rows")

    row = rows[0]

    # Extract stats — column names vary based on Cortex SQL generation
    avg_employees = _extract_number(row, ["AVG_EMPLOYEE", "EMPLOYEE", "EMP"], default=0)
    hours_worked = _extract_number(row, ["HOURS", "TOTAL_HOURS"], default=0)
    lifetime_tons = _extract_number(
        row, ["TOTAL", "PRODUCTION", "COAL_PRODUCTION", "TONS"], default=0,
    )
    plant_count = _extract_number(row, ["PLANT", "COUNT", "PLANTS_SERVED"], default=1)

    # Format hours into something human
    hours_str = f"{hours_worked:,.0f}" if hours_worked else "countless"

    plant_s = "s" if plant_count != 1 else ""

    return _PROSE_TEMPLATE.format(
        avg_employees=int(avg_employees) if avg_employees else "Dozens of",
        mine_name=mine_data["mine"],
        tons_year=mine_data["tons_year"],
        hours_worked=hours_str,
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        tons_latest=mine_data["tons"],
        lifetime_tons=lifetime_tons if lifetime_tons else mine_data["tons"],
        plant_count=plant_count,
        plant_s=plant_s,
    )


def _extract_number(row: dict, key_hints: list[str], default: float = 0) -> float:
    """Find a numeric value in a row by partial column name match."""
    for col, val in row.items():
        col_upper = col.upper()
        for hint in key_hints:
            if hint.upper() in col_upper:
                try:
                    return float(val) if val is not None else default
                except (ValueError, TypeError):
                    return default
    return default


def _fallback_prose(mine_data: dict) -> str:
    mine_type = mine_data["mine_type"]
    verb = _VERB_BY_MINE_TYPE.get(mine_type, "excavated")
    return _FALLBACK_TEMPLATE.format(
        mine_name=mine_data["mine"],
        mine_operator=mine_data["mine_operator"],
        mine_county=mine_data["mine_county"],
        mine_state=mine_data["mine_state"],
        plant_name=mine_data["plant"],
        tons_year=mine_data["tons_year"],
        tons_latest=mine_data["tons"],
        verb=verb,
    )
