import json
import logging
from pathlib import Path

import requests
import snowflake.connector

from app.config import settings

logger = logging.getLogger(__name__)

# Hand-written SQL for /mine-for-me — not Cortex Analyst.
# CTEs clean MSHA embedded quotes and EIA comma-formatted numbers
# so joins and filters operate on typed, pre-cleaned columns.
MINE_FOR_SUBREGION_SQL = """
WITH fr_clean AS (
    SELECT
        PLANT_ID,
        PLANT_NAME,
        YEAR,
        FUEL_GROUP,
        TRY_TO_NUMBER(COALMINE_MSHA_ID) AS COALMINE_MSHA_ID_NUM,
        TRY_TO_NUMBER(REPLACE(QUANTITY, ',', ''), 18, 1) AS QUANTITY_NUM
    FROM UNEARTHED_DB.RAW.EIA_923_FUEL_RECEIPTS
),
m_clean AS (
    SELECT
        TRY_TO_NUMBER(REPLACE(MINE_ID, '"', '')) AS MINE_ID_NUM,
        TRIM(REPLACE(CURRENT_MINE_NAME, '"', '')) AS MINE_NAME,
        TRIM(REPLACE(CURRENT_OPERATOR_NAME, '"', '')) AS MINE_OPERATOR,
        TRIM(REPLACE(FIPS_CNTY_NM, '"', '')) AS MINE_COUNTY,
        TRIM(REPLACE(STATE, '"', '')) AS MINE_STATE,
        TRIM(REPLACE(CURRENT_MINE_TYPE, '"', '')) AS MINE_TYPE,
        TRY_TO_DOUBLE(REPLACE(LATITUDE, '"', '')) AS MINE_LAT,
        TRY_TO_DOUBLE(REPLACE(LONGITUDE, '"', '')) AS MINE_LON,
        REPLACE(COAL_METAL_IND, '"', '') AS COAL_METAL_IND_CLEAN
    FROM UNEARTHED_DB.RAW.MSHA_MINES
)
SELECT
    m.MINE_NAME,
    m.MINE_OPERATOR,
    m.MINE_COUNTY,
    m.MINE_STATE,
    m.MINE_TYPE,
    m.MINE_LAT,
    m.MINE_LON,
    p.PLANTNAME AS PLANT_NAME,
    p.UTILITYNAME AS PLANT_OPERATOR,
    p.LATITUDE AS PLANT_LAT,
    p.LONGITUDE AS PLANT_LON,
    SUM(fr.QUANTITY_NUM) AS TOTAL_TONS,
    MAX(fr.YEAR) AS TONS_YEAR
FROM fr_clean fr
JOIN UNEARTHED_DB.RAW.PLANT_SUBREGION_LOOKUP lk
    ON fr.PLANT_ID = lk.PLANT_CODE
JOIN UNEARTHED_DB.RAW.EIA_860_PLANTS p
    ON fr.PLANT_ID = p.PLANTCODE
JOIN m_clean m
    ON fr.COALMINE_MSHA_ID_NUM = m.MINE_ID_NUM
WHERE fr.FUEL_GROUP = 'Coal'
    AND lk.EGRID_SUBREGION = %(subregion_id)s
    AND m.COAL_METAL_IND_CLEAN = 'C'
GROUP BY
    m.MINE_NAME,
    m.MINE_OPERATOR,
    m.MINE_COUNTY,
    m.MINE_STATE,
    m.MINE_TYPE,
    m.MINE_LAT,
    m.MINE_LON,
    p.PLANTNAME,
    p.UTILITYNAME,
    p.LATITUDE,
    p.LONGITUDE
ORDER BY TOTAL_TONS DESC
LIMIT 1
"""


def _get_connection() -> snowflake.connector.SnowflakeConnection:
    connect_args = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "role": settings.snowflake_role,
        "warehouse": settings.snowflake_warehouse,
        "database": settings.snowflake_database,
    }
    if settings.snowflake_private_key_path:
        from cryptography.hazmat.primitives import serialization

        key_path = Path(settings.snowflake_private_key_path).expanduser()
        key_data = key_path.read_bytes()
        passphrase = (
            settings.snowflake_private_key_passphrase.encode()
            if settings.snowflake_private_key_passphrase
            else None
        )
        private_key = serialization.load_pem_private_key(key_data, password=passphrase)
        connect_args["private_key"] = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    else:
        logger.warning(
            "Using password auth — key-pair auth is required for production. "
            "Set SNOWFLAKE_PRIVATE_KEY_PATH to use key-pair auth."
        )
        connect_args["password"] = settings.snowflake_password

    return snowflake.connector.connect(**connect_args)


def query_mine_for_subregion(subregion_id: str) -> dict | None:
    """Return the top mine-plant pair for a given eGRID subregion."""
    conn = _get_connection()
    try:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(MINE_FOR_SUBREGION_SQL, {"subregion_id": subregion_id.upper()})
        row = cur.fetchone()
        if not row:
            return None
        return {
            "mine": row["MINE_NAME"],
            "mine_operator": row["MINE_OPERATOR"],
            "mine_county": row["MINE_COUNTY"],
            "mine_state": row["MINE_STATE"],
            "mine_type": row["MINE_TYPE"],
            "mine_coords": [row["MINE_LAT"], row["MINE_LON"]],
            "plant": row["PLANT_NAME"],
            "plant_operator": row["PLANT_OPERATOR"],
            "plant_coords": [row["PLANT_LAT"], row["PLANT_LON"]],
            "tons": float(row["TOTAL_TONS"]),
            "tons_year": int(row["TONS_YEAR"]),
        }
    finally:
        conn.close()


def query_cortex_analyst(question: str) -> dict:
    """Answer a question using the Snowflake Cortex Analyst REST API.

    Posts the question plus the semantic model to the Cortex Analyst
    endpoint. Returns both the text answer and any generated SQL so
    the frontend can display SQL for the PRD honesty path.
    """
    semantic_model_path = Path(__file__).parent.parent / "assets" / "semantic_model.yaml"
    semantic_model = semantic_model_path.read_text()

    conn = _get_connection()
    try:
        token = conn.rest.token
        account = settings.snowflake_account.lower()
        url = f"https://{account}.snowflakecomputing.com/api/v2/cortex/analyst/message"

        resp = requests.post(
            url,
            headers={
                "Authorization": f'Snowflake Token="{token}"',
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": question}],
                    }
                ],
                "semantic_model": semantic_model,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()

        answer_parts = []
        sql = None
        for item in body.get("message", {}).get("content", []):
            if item.get("type") == "text":
                answer_parts.append(item["text"])
            elif item.get("type") == "sql":
                sql = item.get("statement", "")

        answer = "\n\n".join(answer_parts) if answer_parts else ""
        return {"answer": answer, "sql": sql, "error": None}
    except Exception as exc:
        logger.exception("Cortex Analyst query failed")
        return {
            "answer": "",
            "sql": None,
            "error": f"Query failed: {exc}",
        }
    finally:
        conn.close()


def load_fallback_data(subregion_id: str) -> dict | None:
    """Load cached fallback JSON for a subregion when Snowflake is down."""
    fallback_dir = Path(__file__).parent.parent / "assets" / "fallback"
    fallback_file = fallback_dir / f"{subregion_id.upper()}.json"
    if fallback_file.exists():
        return json.loads(fallback_file.read_text())
    return None
