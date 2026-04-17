import json
import logging
from pathlib import Path

import requests
import snowflake.connector

from app.config import settings

logger = logging.getLogger(__name__)

# Query against the MRT view — all CTE cleanup lives in the view definition.
MINE_FOR_SUBREGION_SQL = """
SELECT
    MINE_NAME,
    MINE_OPERATOR,
    MINE_COUNTY,
    MINE_STATE,
    MINE_TYPE,
    MINE_LAT,
    MINE_LON,
    PLANT_NAME,
    PLANT_OPERATOR,
    PLANT_LAT,
    PLANT_LON,
    TOTAL_TONS,
    TONS_YEAR
FROM UNEARTHED_DB.MRT.V_MINE_FOR_SUBREGION
WHERE EGRID_SUBREGION = %(subregion_id)s
    AND TONS_YEAR = 2024
ORDER BY TOTAL_TONS DESC
LIMIT 1
"""


def _get_connection() -> snowflake.connector.SnowflakeConnection:
    if not settings.snowflake_account or not settings.snowflake_user:
        raise RuntimeError(
            "SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set."
        )
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
    elif settings.allow_password_auth and settings.snowflake_password:
        logger.warning("Using password auth — set SNOWFLAKE_PRIVATE_KEY_PATH for production.")
        connect_args["password"] = settings.snowflake_password
    else:
        raise RuntimeError(
            "No auth method configured. Set SNOWFLAKE_PRIVATE_KEY_PATH for key-pair auth, "
            "or set ALLOW_PASSWORD_AUTH=true with SNOWFLAKE_PASSWORD for local dev."
        )

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
            "mine_coords": [float(row["MINE_LAT"]), float(row["MINE_LON"])],
            "plant": row["PLANT_NAME"],
            "plant_operator": row["PLANT_OPERATOR"],
            "plant_coords": [float(row["PLANT_LAT"]), float(row["PLANT_LON"])],
            "tons": float(row["TOTAL_TONS"]),
            "tons_year": int(row["TONS_YEAR"]),
        }
    finally:
        conn.close()


_SEMANTIC_MODEL: str = (
    Path(__file__).parent.parent / "assets" / "semantic_model.yaml"
).read_text()


def query_cortex_analyst(question: str) -> dict:
    """Answer a question using the Snowflake Cortex Analyst REST API.

    Posts the question plus the semantic model to the Cortex Analyst
    endpoint. Returns both the text answer and any generated SQL so
    the frontend can display SQL for the PRD honesty path.
    """
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
                "semantic_model": _SEMANTIC_MODEL,
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
    except Exception:
        logger.exception("Cortex Analyst query failed")
        return {
            "answer": "",
            "sql": None,
            "error": "We couldn't answer that question right now. Please try again later.",
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
