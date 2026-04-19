import json
import logging
import re
import threading
from pathlib import Path

import requests
import snowflake.connector

from app.config import settings

logger = logging.getLogger(__name__)

# --- Connection pool ---
# Two persistent connections: one for APP_ROLE, one for READONLY_ROLE.
# Reconnects automatically on failure. Thread-safe via lock.
_pool: dict[str, snowflake.connector.SnowflakeConnection] = {}
_pool_lock = threading.Lock()

# CTE: top mine from the MRT view, then join raw tables for plant details.
# The view ranks mines per subregion but doesn't carry plant coordinates.
# latest_year resolves dynamically so we never chase a hardcoded year.
# Scoped to the subregion to avoid a global EIA_923 full-table scan on every request.
MINE_FOR_SUBREGION_SQL = """
WITH latest_year AS (
    -- Single-row CTE: MAX(YEAR) for coal receipts reaching this subregion.
    -- CROSS JOIN in the final SELECT is safe because this CTE always returns exactly one row.
    SELECT MAX(fr.YEAR) AS YEAR
    FROM UNEARTHED_DB.RAW.EIA_923_FUEL_RECEIPTS fr
    JOIN UNEARTHED_DB.RAW.PLANT_SUBREGION_LOOKUP lk
        ON fr.PLANT_ID = lk.PLANT_CODE
    WHERE fr.FUEL_GROUP = 'Coal'
        AND lk.EGRID_SUBREGION = %(subregion_id)s
),
top_mine AS (
    SELECT
        MINE_ID,
        MINE_NAME,
        MINE_OPERATOR,
        MINE_COUNTY,
        MINE_STATE,
        MINE_TYPE,
        MINE_LATITUDE,
        MINE_LONGITUDE,
        TOTAL_TONS_TO_SUBREGION
    FROM UNEARTHED_DB.MRT.V_MINE_FOR_SUBREGION
    WHERE EGRID_SUBREGION = %(subregion_id)s
        AND MINE_RANK = 1
    LIMIT 1
),
top_plant AS (
    SELECT
        p.PLANTNAME AS PLANT_NAME,
        p.UTILITYNAME AS PLANT_OPERATOR,
        p.LATITUDE AS PLANT_LATITUDE,
        p.LONGITUDE AS PLANT_LONGITUDE,
        SUM(TRY_TO_NUMBER(REPLACE(fr.QUANTITY, ',', ''), 18, 1)) AS TONS
    FROM UNEARTHED_DB.RAW.EIA_923_FUEL_RECEIPTS fr
    JOIN UNEARTHED_DB.RAW.EIA_860_PLANTS p
        ON fr.PLANT_ID = p.PLANTCODE
    JOIN UNEARTHED_DB.RAW.PLANT_SUBREGION_LOOKUP lk
        ON p.PLANTCODE = lk.PLANT_CODE
    JOIN top_mine tm
        ON TRY_TO_NUMBER(fr.COALMINE_MSHA_ID) = TRY_TO_NUMBER(tm.MINE_ID)
    WHERE fr.FUEL_GROUP = 'Coal'
        AND fr.YEAR = (SELECT YEAR FROM latest_year)
        AND lk.EGRID_SUBREGION = %(subregion_id)s
    GROUP BY p.PLANTNAME, p.UTILITYNAME, p.LATITUDE, p.LONGITUDE
    QUALIFY ROW_NUMBER() OVER (ORDER BY TONS DESC) = 1
)
SELECT
    tm.MINE_ID,
    tm.MINE_NAME,
    tm.MINE_OPERATOR,
    tm.MINE_COUNTY,
    tm.MINE_STATE,
    tm.MINE_TYPE,
    tm.MINE_LATITUDE,
    tm.MINE_LONGITUDE,
    tp.PLANT_NAME,
    tp.PLANT_OPERATOR,
    tp.PLANT_LATITUDE,
    tp.PLANT_LONGITUDE,
    tm.TOTAL_TONS_TO_SUBREGION AS TOTAL_TONS,
    ly.YEAR AS DATA_YEAR
FROM top_mine tm
LEFT JOIN top_plant tp ON 1 = 1
CROSS JOIN latest_year ly
"""

_MINE_TYPE_LABELS = {"U": "Underground", "S": "Surface", "F": "Facility"}


def _create_connection(role: str) -> snowflake.connector.SnowflakeConnection:
    """Create a fresh Snowflake connection for the given role."""
    if not settings.snowflake_account or not settings.snowflake_user:
        raise RuntimeError("SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set.")
    connect_args = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "role": role,
        "warehouse": settings.snowflake_warehouse,
        "database": settings.snowflake_database,
        "client_session_keep_alive": True,
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


def _get_connection(
    *,
    role: str | None = None,
) -> snowflake.connector.SnowflakeConnection:
    """Get a pooled connection for the given role. Reconnects if stale."""
    effective_role = role or settings.snowflake_role
    with _pool_lock:
        conn = _pool.get(effective_role)
        if conn is not None:
            try:
                cur = conn.cursor()
                try:
                    cur.execute("SELECT 1").fetchone()
                finally:
                    cur.close()
                return conn
            except Exception:
                logger.info("Pooled connection stale for role %s, reconnecting", effective_role)
                try:
                    conn.close()
                except Exception:
                    pass
        conn = _create_connection(effective_role)
        _pool[effective_role] = conn
        return conn


def query_mine_for_subregion(subregion_id: str) -> dict | None:
    """Return the top mine-plant pair for a given eGRID subregion."""
    conn = _get_connection()
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        cur.execute(
            MINE_FOR_SUBREGION_SQL,
            {"subregion_id": subregion_id.upper()},
        )
        row = cur.fetchone()
    finally:
        cur.close()
    if not row:
        return None

    for field in (
        "MINE_LATITUDE",
        "MINE_LONGITUDE",
        "PLANT_LATITUDE",
        "PLANT_LONGITUDE",
        "TOTAL_TONS",
        "DATA_YEAR",
    ):
        if row.get(field) is None:
            logger.error("NULL %s for subregion %s", field, subregion_id)
            return None

    return {
        "mine_id": str(row["MINE_ID"]),
        "mine": row["MINE_NAME"],
        "mine_operator": row["MINE_OPERATOR"],
        "mine_county": row["MINE_COUNTY"],
        "mine_state": row["MINE_STATE"],
        "mine_type": _MINE_TYPE_LABELS.get(row["MINE_TYPE"] or "", "Surface"),
        "mine_coords": [
            float(row["MINE_LATITUDE"]),
            float(row["MINE_LONGITUDE"]),
        ],
        "plant": row["PLANT_NAME"],
        "plant_operator": row["PLANT_OPERATOR"],
        "plant_coords": [
            float(row["PLANT_LATITUDE"]),
            float(row["PLANT_LONGITUDE"]),
        ],
        "tons": float(row["TOTAL_TONS"]),
        "tons_year": int(row["DATA_YEAR"]),
    }


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
        if not resp.ok:
            logger.error(
                "Cortex Analyst HTTP %s: %s",
                resp.status_code,
                resp.text[:500],
            )
            resp.raise_for_status()
        body = resp.json()

        content = body.get("message", {}).get("content", [])
        has_sql = any(item.get("type") == "sql" for item in content)

        interpretation_parts: list[str] = []
        answer_parts: list[str] = []
        sql = None
        suggestions = None
        for item in content:
            if item.get("type") == "text":
                if has_sql:
                    interpretation_parts.append(item["text"])
                else:
                    answer_parts.append(item["text"])
            elif item.get("type") == "sql":
                sql = item.get("statement", "")
            elif item.get("type") == "suggestions":
                suggestions = item.get("suggestions", [])

        answer = "\n\n".join(answer_parts) if answer_parts else ""
        interpretation = "\n\n".join(interpretation_parts) if interpretation_parts else None
        return {
            "answer": answer,
            "interpretation": interpretation,
            "sql": sql,
            "suggestions": suggestions,
            "error": None,
        }
    except Exception:
        logger.exception("Cortex Analyst query failed")
        return {
            "answer": "",
            "interpretation": None,
            "sql": None,
            "error": "We couldn't answer that question right now. Please try again later.",
        }


_SAFE_SQL_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|"
    r"GRANT|REVOKE|CALL|EXECUTE|COPY|PUT|GET|REMOVE)\b",
    re.IGNORECASE,
)


def _is_safe_sql(sql: str) -> bool:
    """Check that SQL is a single read-only SELECT (or WITH/CTE)."""
    stripped = sql.strip()
    if not stripped:
        return False
    if ";" in stripped:
        return False
    if not _SAFE_SQL_START.match(stripped):
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
    # Cortex Analyst appends a trailing semicolon; strip it before safety check and execution.
    clean_sql = sql.strip().rstrip(";").strip()
    if not _is_safe_sql(clean_sql):
        raise ValueError("Only single read-only SELECT statements are allowed.")
    conn = _get_connection(role=settings.snowflake_readonly_role)
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 10")
        cur.execute(clean_sql)
        return [dict(row) for row in cur.fetchmany(500)]
    finally:
        cur.close()


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
