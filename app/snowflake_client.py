import functools
import json
import logging
import re
import threading
from pathlib import Path

import requests
import snowflake.connector

from app.config import settings

logger = logging.getLogger(__name__)

# --- Thread-local connection pool ---
# Each thread gets its own connections (one per role). Snowflake's Python
# connector is not thread-safe — sharing a connection across threads
# corrupts session state. Thread-local storage ensures the pre-warming
# daemon and request handler threads never interfere with each other.
_local = threading.local()

# Single-row read from the pre-materialized MRT table.
# MINE_PLANT_FOR_SUBREGION has one row per eGRID subregion with the top mine,
# its top receiving plant, coords, and data year — no joins at query time.
MINE_FOR_SUBREGION_SQL = """
SELECT
    MINE_ID,
    MINE_NAME,
    MINE_OPERATOR,
    MINE_COUNTY,
    MINE_STATE,
    MINE_TYPE,
    MINE_LATITUDE,
    MINE_LONGITUDE,
    PLANT_NAME,
    PLANT_OPERATOR,
    PLANT_LATITUDE,
    PLANT_LONGITUDE,
    TOTAL_TONS,
    DATA_YEAR,
    FATALITIES,
    INJURIES_LOST_TIME,
    TOTAL_DAYS_LOST
FROM UNEARTHED_DB.MRT.MINE_PLANT_FOR_SUBREGION
WHERE EGRID_SUBREGION = %(subregion_id)s
"""

_MINE_TYPE_LABELS = {"U": "Underground", "S": "Surface", "F": "Facility"}


@functools.lru_cache(maxsize=1)
def _get_private_key_der() -> bytes:
    """Parse the private key once and cache the DER bytes."""
    from cryptography.hazmat.primitives import serialization

    key_path = Path(settings.snowflake_private_key_path).expanduser()
    key_data = key_path.read_bytes()
    passphrase = (
        settings.snowflake_private_key_passphrase.encode()
        if settings.snowflake_private_key_passphrase
        else None
    )
    private_key = serialization.load_pem_private_key(key_data, password=passphrase)
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


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
        "login_timeout": 10,
        "network_timeout": 15,
    }
    if settings.snowflake_private_key_path:
        connect_args["private_key"] = _get_private_key_der()
    elif settings.allow_password_auth and settings.snowflake_password:
        logger.warning("Using password auth — set SNOWFLAKE_PRIVATE_KEY_PATH for production.")
        connect_args["password"] = settings.snowflake_password
    else:
        raise RuntimeError(
            "No auth method configured. Set SNOWFLAKE_PRIVATE_KEY_PATH for key-pair auth, "
            "or set ALLOW_PASSWORD_AUTH=true with SNOWFLAKE_PASSWORD for local dev."
        )

    conn = snowflake.connector.connect(**connect_args)
    cur = conn.cursor()
    try:
        cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 10, ROWS_PER_RESULTSET = 500")
    finally:
        cur.close()
    return conn


def _get_pool() -> dict[str, snowflake.connector.SnowflakeConnection]:
    """Return the thread-local connection pool, creating it if needed."""
    if not hasattr(_local, "pool"):
        _local.pool = {}
    return _local.pool


def _get_connection(
    *,
    role: str | None = None,
) -> snowflake.connector.SnowflakeConnection:
    """Get a thread-local connection for the given role. Reconnects if stale."""
    effective_role = role or settings.snowflake_role
    pool = _get_pool()
    conn = pool.get(effective_role)
    if conn is not None and conn.is_closed():
        logger.info("Connection closed for role %s, reconnecting", effective_role)
        conn = None
    if conn is None:
        conn = _create_connection(effective_role)
        pool[effective_role] = conn
    return conn


def _reconnect(role: str | None = None) -> snowflake.connector.SnowflakeConnection:
    """Force-replace this thread's connection for a role after a query failure."""
    effective_role = role or settings.snowflake_role
    pool = _get_pool()
    old = pool.pop(effective_role, None)
    if old is not None:
        try:
            old.close()
        except Exception:
            logger.debug(
                "Failed to close stale connection for role %s",
                effective_role,
                exc_info=True,
            )
    conn = _create_connection(effective_role)
    pool[effective_role] = conn
    return conn


def query_mine_for_subregion(subregion_id: str) -> dict | None:
    """Return the top mine-plant pair for a given eGRID subregion."""
    params = {"subregion_id": subregion_id.upper()}
    try:
        conn = _get_connection()
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(MINE_FOR_SUBREGION_SQL, params)
            row = cur.fetchone()
        finally:
            cur.close()
    except Exception as exc:
        logger.info("Query failed (%s), reconnecting and retrying", exc)
        conn = _reconnect()
        cur = conn.cursor(snowflake.connector.DictCursor)
        try:
            cur.execute(MINE_FOR_SUBREGION_SQL, params)
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
        "fatalities": int(row.get("FATALITIES") or 0),
        "injuries": int(row.get("INJURIES_LOST_TIME") or 0),
        "days_lost": int(row.get("TOTAL_DAYS_LOST") or 0),
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


def summarize_analyst_results(question: str, results: list[dict]) -> str:
    """Use Cortex Complete to turn SQL results into a prose answer."""
    if not results:
        return ""
    results_text = json.dumps(results[:10], default=str)
    prompt = (
        f'The user asked: "{question}"\n\n'
        f"The database returned:\n{results_text}\n\n"
        "The user can already see the raw table. Do NOT restate values the table shows. "
        "Instead, write 1-2 sentences that explain what the data means — context, "
        "significance, or implications the numbers alone do not convey. "
        "Be direct. No hedging, no markdown."
    )
    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b', %s)",
            (prompt,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0].strip().strip('"')
    finally:
        cur.close()
    return ""


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
        cur.execute(clean_sql)
        return [dict(row) for row in cur.fetchall()]
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
