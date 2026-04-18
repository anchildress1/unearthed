import json
import logging
import re
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


def _get_connection(
    *,
    role: str | None = None,
) -> snowflake.connector.SnowflakeConnection:
    if not settings.snowflake_account or not settings.snowflake_user:
        raise RuntimeError("SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set.")
    connect_args = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "role": role or settings.snowflake_role,
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


_SEMANTIC_MODEL: str = (Path(__file__).parent.parent / "assets" / "semantic_model.yaml").read_text()


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
        suggestions = None
        for item in body.get("message", {}).get("content", []):
            if item.get("type") == "text":
                answer_parts.append(item["text"])
            elif item.get("type") == "sql":
                sql = item.get("statement", "")
            elif item.get("type") == "suggestions":
                suggestions = item.get("suggestions", [])

        answer = "\n\n".join(answer_parts) if answer_parts else ""
        return {
            "answer": answer,
            "sql": sql,
            "suggestions": suggestions,
            "error": None,
        }
    except Exception:
        logger.exception("Cortex Analyst query failed")
        return {
            "answer": "",
            "sql": None,
            "error": "We couldn't answer that question right now. Please try again later.",
        }
    finally:
        conn.close()


_SAFE_SQL_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|"
    r"GRANT|REVOKE|CALL|EXECUTE|COPY|PUT|GET|REMOVE)\b",
    re.IGNORECASE,
)


def _is_safe_sql(sql: str) -> bool:
    """Check that SQL is a single read-only SELECT (or WITH/CTE)."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return False
    if not _SAFE_SQL_START.match(stripped):
        return False
    if ";" in stripped:
        return False
    if _DANGEROUS_KEYWORDS.search(stripped):
        return False
    return True


def execute_analyst_sql(sql: str) -> list[dict]:
    """Execute SQL generated by Cortex Analyst using a read-only role.

    Two layers of protection:
    1. Snowflake role (UNEARTHED_READONLY_ROLE) — only has SELECT grants.
    2. Regex validation — rejects non-SELECT SQL before it hits the wire.
    """
    if not _is_safe_sql(sql):
        raise ValueError("Only single read-only SELECT statements are allowed.")
    conn = _get_connection(role=settings.snowflake_readonly_role)
    try:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 10")
        cur.execute(sql)
        return [dict(row) for row in cur.fetchmany(500)]
    finally:
        conn.close()


_FALLBACK_DIR = (Path(__file__).parent.parent / "assets" / "fallback").resolve()

# Pre-load the set of valid fallback subregion IDs from filenames on disk.
# This allowlist prevents any user-controlled data from reaching file paths.
_VALID_FALLBACK_IDS: dict[str, Path] = {
    f.stem: f for f in _FALLBACK_DIR.glob("*.json") if f.is_file()
}


def load_fallback_data(subregion_id: str) -> dict | None:
    """Load cached fallback JSON for a subregion when Snowflake is down."""
    fallback_file = _VALID_FALLBACK_IDS.get(subregion_id.upper())
    if fallback_file is None:
        return None
    try:
        return json.loads(fallback_file.read_text())
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read fallback file: %s", fallback_file.name)
        return None
