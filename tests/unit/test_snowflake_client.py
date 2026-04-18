"""Unit tests for Snowflake client: query result mapping, fallback loading."""

from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
import requests as req_lib

from app.snowflake_client import (
    _get_connection,
    execute_analyst_sql,
    load_fallback_data,
    query_cortex_analyst,
    query_mine_for_subregion,
)

MOCK_ROW = {
    "MINE_NAME": "Bailey Mine",
    "MINE_OPERATOR": "Consol Pennsylvania Coal Company LLC",
    "MINE_COUNTY": "Greene",
    "MINE_STATE": "PA",
    "MINE_TYPE": "U",
    "MINE_LATITUDE": 39.9175,
    "MINE_LONGITUDE": -80.471944,
    "PLANT_NAME": "Cross",
    "PLANT_OPERATOR": "South Carolina Public Service Authority",
    "PLANT_LATITUDE": "33.371506",
    "PLANT_LONGITUDE": "-80.113235",
    "TOTAL_TONS": "3811733.0",
    "DATA_YEAR": 2024,
}


class TestQueryMineForSubregion:
    def _mock_connection(self, rows):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = rows[0] if rows else None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn

    @patch("app.snowflake_client._get_connection")
    def test_valid_result_maps_fields(self, mock_get_conn):
        mock_get_conn.return_value = self._mock_connection([MOCK_ROW])
        result = query_mine_for_subregion("SRVC")

        assert result["mine"] == "Bailey Mine"
        assert result["mine_operator"] == "Consol Pennsylvania Coal Company LLC"
        assert result["mine_county"] == "Greene"
        assert result["mine_state"] == "PA"
        assert result["mine_type"] == "Underground"
        assert result["mine_coords"] == [39.9175, -80.471944]
        assert result["plant"] == "Cross"
        assert result["plant_operator"] == "South Carolina Public Service Authority"
        assert result["plant_coords"] == [33.371506, -80.113235]
        assert result["tons"] == pytest.approx(3811733.0)
        assert result["tons_year"] == 2024

    @patch("app.snowflake_client._get_connection")
    def test_no_rows_returns_none(self, mock_get_conn):
        mock_get_conn.return_value = self._mock_connection([])
        result = query_mine_for_subregion("NONEXISTENT")
        assert result is None

    @patch("app.snowflake_client._get_connection")
    def test_subregion_uppercased(self, mock_get_conn):
        mock_conn = self._mock_connection([MOCK_ROW])
        mock_get_conn.return_value = mock_conn
        query_mine_for_subregion("srvc")
        # Access the cursor reference directly; calling cursor() again would
        # register a spurious extra call and couple the test to call-count state.
        call_args = mock_conn.cursor.return_value.execute.call_args
        assert call_args[0][1]["subregion_id"] == "SRVC"

    @patch("app.snowflake_client._get_connection")
    def test_connection_closed_on_success(self, mock_get_conn):
        mock_conn = self._mock_connection([MOCK_ROW])
        mock_get_conn.return_value = mock_conn
        query_mine_for_subregion("SRVC")
        mock_conn.close.assert_called_once()

    @patch("app.snowflake_client._get_connection")
    def test_connection_closed_on_error(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.execute.side_effect = Exception("DB error")
        mock_get_conn.return_value = mock_conn

        with pytest.raises(Exception, match="DB error"):
            query_mine_for_subregion("SRVC")

        mock_conn.close.assert_called_once()

    @patch("app.snowflake_client._get_connection")
    def test_tons_converted_to_float(self, mock_get_conn):
        row = {**MOCK_ROW, "TOTAL_TONS": "5000000.0"}
        mock_get_conn.return_value = self._mock_connection([row])
        result = query_mine_for_subregion("SRVC")
        assert isinstance(result["tons"], float)

    @patch("app.snowflake_client._get_connection")
    def test_coords_are_two_element_lists(self, mock_get_conn):
        mock_get_conn.return_value = self._mock_connection([MOCK_ROW])
        result = query_mine_for_subregion("SRVC")
        assert len(result["mine_coords"]) == 2
        assert len(result["plant_coords"]) == 2

    # --- NULL / no-plant-found paths (LEFT JOIN on top_plant) ---

    @patch("app.snowflake_client._get_connection")
    def test_null_plant_latitude_returns_none(self, mock_get_conn):
        """LEFT JOIN yields NULL plant coords when no plant matches; must signal degraded."""
        row = {**MOCK_ROW, "PLANT_LATITUDE": None, "PLANT_LONGITUDE": None}
        mock_get_conn.return_value = self._mock_connection([row])
        assert query_mine_for_subregion("SRVC") is None

    @patch("app.snowflake_client._get_connection")
    def test_null_mine_latitude_returns_none(self, mock_get_conn):
        row = {**MOCK_ROW, "MINE_LATITUDE": None}
        mock_get_conn.return_value = self._mock_connection([row])
        assert query_mine_for_subregion("SRVC") is None

    @patch("app.snowflake_client._get_connection")
    def test_null_total_tons_returns_none(self, mock_get_conn):
        row = {**MOCK_ROW, "TOTAL_TONS": None}
        mock_get_conn.return_value = self._mock_connection([row])
        assert query_mine_for_subregion("SRVC") is None

    @patch("app.snowflake_client._get_connection")
    def test_null_mine_longitude_only_returns_none(self, mock_get_conn):
        """Lone MINE_LONGITUDE NULL must trigger degraded mode independent of MINE_LATITUDE."""
        row = {**MOCK_ROW, "MINE_LONGITUDE": None}
        mock_get_conn.return_value = self._mock_connection([row])
        assert query_mine_for_subregion("SRVC") is None

    @patch("app.snowflake_client._get_connection")
    def test_null_plant_longitude_only_returns_none(self, mock_get_conn):
        """Lone PLANT_LONGITUDE NULL must trigger degraded mode independent of PLANT_LATITUDE."""
        row = {**MOCK_ROW, "PLANT_LONGITUDE": None}
        mock_get_conn.return_value = self._mock_connection([row])
        assert query_mine_for_subregion("SRVC") is None

    @patch("app.snowflake_client._get_connection")
    def test_null_data_year_returns_none(self, mock_get_conn):
        """NULL DATA_YEAR must not crash with TypeError; must signal degraded mode."""
        row = {**MOCK_ROW, "DATA_YEAR": None}
        mock_get_conn.return_value = self._mock_connection([row])
        assert query_mine_for_subregion("SRVC") is None

    # --- cursor cleanup ---

    @patch("app.snowflake_client._get_connection")
    def test_cursor_closed_on_execute_error(self, mock_get_conn):
        """cur.close() must be called even when execute raises (inner finally)."""
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("SQL error")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        with pytest.raises(Exception, match="SQL error"):
            query_mine_for_subregion("SRVC")

        mock_cursor.close.assert_called_once()

    # --- mine_type label mapping ---

    @patch("app.snowflake_client._get_connection")
    def test_surface_mine_type_maps_correctly(self, mock_get_conn):
        row = {**MOCK_ROW, "MINE_TYPE": "S"}
        mock_get_conn.return_value = self._mock_connection([row])
        result = query_mine_for_subregion("SRVC")
        assert result["mine_type"] == "Surface"

    @patch("app.snowflake_client._get_connection")
    def test_unknown_mine_type_falls_back_to_surface(self, mock_get_conn):
        """Unrecognised MSHA codes must not leak raw codes into the response."""
        row = {**MOCK_ROW, "MINE_TYPE": "X"}
        mock_get_conn.return_value = self._mock_connection([row])
        result = query_mine_for_subregion("SRVC")
        assert result["mine_type"] == "Surface"

    @patch("app.snowflake_client._get_connection")
    def test_null_mine_type_falls_back_to_surface(self, mock_get_conn):
        row = {**MOCK_ROW, "MINE_TYPE": None}
        mock_get_conn.return_value = self._mock_connection([row])
        result = query_mine_for_subregion("SRVC")
        assert result["mine_type"] == "Surface"

    @patch("app.snowflake_client._get_connection")
    def test_facility_mine_type_maps_correctly(self, mock_get_conn):
        row = {**MOCK_ROW, "MINE_TYPE": "F"}
        mock_get_conn.return_value = self._mock_connection([row])
        result = query_mine_for_subregion("SRVC")
        assert result["mine_type"] == "Facility"

    # --- dynamic tons_year ---

    @patch("app.snowflake_client._get_connection")
    def test_tons_year_comes_from_data(self, mock_get_conn):
        """tons_year must reflect DATA_YEAR from the query, not a hardcoded constant."""
        row = {**MOCK_ROW, "DATA_YEAR": 2023}
        mock_get_conn.return_value = self._mock_connection([row])
        result = query_mine_for_subregion("SRVC")
        assert result["tons_year"] == 2023


class TestLoadFallbackData:
    def test_existing_fallback_file_loads(self):
        # SRVC.json was generated by scripts/generate_fallbacks.py
        result = load_fallback_data("SRVC")
        if result is not None:
            assert "mine" in result
            assert "tons" in result

    def test_missing_fallback_returns_none(self):
        result = load_fallback_data("DEFINITELY_NOT_A_REAL_SUBREGION_XYZ")
        assert result is None

    def test_case_insensitive_lookup(self):
        # load_fallback_data uppercases the subregion_id
        result_upper = load_fallback_data("SRVC")
        result_lower = load_fallback_data("srvc")
        assert result_upper == result_lower

    def test_corrupt_json_returns_none(self, tmp_path):
        """Corrupt fallback JSON should return None, not crash."""
        corrupt_file = tmp_path / "CORRUPT.json"
        corrupt_file.write_text("{invalid json content")
        with patch(
            "app.snowflake_client._VALID_FALLBACK_IDS",
            {"CORRUPT": corrupt_file},
        ):
            result = load_fallback_data("CORRUPT")
        assert result is None

    def test_permission_denied_returns_none(self, tmp_path):
        """OSError (permission denied) must be caught and return None."""
        restricted_file = tmp_path / "NOPERM.json"
        restricted_file.write_text('{"mine": "Test"}')
        with patch(
            "app.snowflake_client._VALID_FALLBACK_IDS",
            {"NOPERM": restricted_file},
        ):
            with patch.object(
                type(restricted_file),
                "read_text",
                side_effect=OSError("Permission denied"),
            ):
                result = load_fallback_data("NOPERM")
        assert result is None

    def test_fallback_has_required_structure(self):
        """Loaded fallback data must have mine, plant, coords, and tons keys."""
        result = load_fallback_data("SRVC")
        if result is not None:
            for key in ("mine", "plant", "mine_coords", "plant_coords", "tons"):
                assert key in result, f"Missing key: {key}"


class TestAuthPolicy:
    @patch("app.snowflake_client.settings")
    def test_missing_account_raises(self, mock_settings):
        mock_settings.snowflake_account = ""
        mock_settings.snowflake_user = "user"

        with pytest.raises(RuntimeError, match="SNOWFLAKE_ACCOUNT"):
            _get_connection()

    @patch("app.snowflake_client.settings")
    def test_no_auth_raises_runtime_error(self, mock_settings):
        mock_settings.snowflake_account = "test"
        mock_settings.snowflake_user = "user"
        mock_settings.snowflake_role = "ROLE"
        mock_settings.snowflake_warehouse = "WH"
        mock_settings.snowflake_database = "DB"
        mock_settings.snowflake_private_key_path = ""
        mock_settings.snowflake_password = ""
        mock_settings.allow_password_auth = False

        with pytest.raises(RuntimeError, match="No auth method configured"):
            _get_connection()

    @patch("app.snowflake_client.settings")
    def test_password_without_opt_in_raises(self, mock_settings):
        mock_settings.snowflake_account = "test"
        mock_settings.snowflake_user = "user"
        mock_settings.snowflake_role = "ROLE"
        mock_settings.snowflake_warehouse = "WH"
        mock_settings.snowflake_database = "DB"
        mock_settings.snowflake_private_key_path = ""
        mock_settings.snowflake_password = "secret"
        mock_settings.allow_password_auth = False

        with pytest.raises(RuntimeError, match="No auth method configured"):
            _get_connection()

    @patch("app.snowflake_client.settings")
    def test_missing_user_raises(self, mock_settings):
        mock_settings.snowflake_account = "test"
        mock_settings.snowflake_user = ""

        with pytest.raises(RuntimeError, match="SNOWFLAKE_USER"):
            _get_connection()

    @patch("app.snowflake_client.snowflake.connector.connect")
    @patch("app.snowflake_client.settings")
    def test_password_with_opt_in_connects(self, mock_settings, mock_connect):
        mock_settings.snowflake_account = "test"
        mock_settings.snowflake_user = "user"
        mock_settings.snowflake_role = "ROLE"
        mock_settings.snowflake_warehouse = "WH"
        mock_settings.snowflake_database = "DB"
        mock_settings.snowflake_private_key_path = ""
        mock_settings.snowflake_password = "secret"
        mock_settings.allow_password_auth = True

        _get_connection()
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["password"] == "secret"

    @patch("app.snowflake_client.snowflake.connector.connect")
    @patch("app.snowflake_client.settings")
    def test_custom_role_forwarded(self, mock_settings, mock_connect):
        """role= kwarg must override settings.snowflake_role."""
        mock_settings.snowflake_account = "test"
        mock_settings.snowflake_user = "user"
        mock_settings.snowflake_role = "DEFAULT_ROLE"
        mock_settings.snowflake_warehouse = "WH"
        mock_settings.snowflake_database = "DB"
        mock_settings.snowflake_private_key_path = ""
        mock_settings.snowflake_password = "secret"  # NOSONAR — test mock value
        mock_settings.allow_password_auth = True

        _get_connection(role="CUSTOM_ROLE")
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["role"] == "CUSTOM_ROLE"

    @patch("app.snowflake_client.snowflake.connector.connect")
    @patch("app.snowflake_client.settings")
    def test_private_key_auth_path(self, mock_settings, mock_connect, tmp_path):
        """Private key file path must be read and passed to connector."""
        mock_settings.snowflake_account = "test"
        mock_settings.snowflake_user = "user"
        mock_settings.snowflake_role = "ROLE"
        mock_settings.snowflake_warehouse = "WH"
        mock_settings.snowflake_database = "DB"
        mock_settings.snowflake_private_key_passphrase = ""
        mock_settings.allow_password_auth = False

        # Generate a real RSA key for realistic test
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_path = tmp_path / "test_key.p8"
        key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        mock_settings.snowflake_private_key_path = str(key_path)

        _get_connection()
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert "private_key" in call_kwargs
        assert isinstance(call_kwargs["private_key"], bytes)

    @patch("app.snowflake_client.settings")
    def test_private_key_file_not_found_raises(self, mock_settings):
        """Missing key file must raise, not silently fall back."""
        mock_settings.snowflake_account = "test"
        mock_settings.snowflake_user = "user"
        mock_settings.snowflake_role = "ROLE"
        mock_settings.snowflake_warehouse = "WH"
        mock_settings.snowflake_database = "DB"
        mock_settings.snowflake_private_key_path = "/nonexistent/key.p8"
        mock_settings.snowflake_private_key_passphrase = ""
        mock_settings.allow_password_auth = False

        with pytest.raises(FileNotFoundError):
            _get_connection()


ANALYST_INTERP = "This is our interpretation of your question: Total coal tonnage for SRVC."

ANALYST_RESPONSE = {
    "message": {
        "role": "analyst",
        "content": [
            {"type": "text", "text": ANALYST_INTERP},
            {"type": "sql", "statement": "SELECT SUM(QUANTITY) FROM ..."},
        ],
    }
}


class TestQueryCortexAnalyst:
    def _mock_connection(self):
        mock_conn = MagicMock()
        mock_conn.rest.token = "fake-session-token"
        return mock_conn

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_returns_answer_and_sql(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = ANALYST_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("How much coal for SRVC?")

        # When SQL is present the text item is the interpretation, not the answer.
        assert result["answer"] == ""
        assert result["interpretation"] == ANALYST_INTERP
        assert result["sql"] == "SELECT SUM(QUANTITY) FROM ..."
        assert result["error"] is None

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_text_only_response_has_no_sql(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {
                "role": "analyst",
                "content": [{"type": "text", "text": "I cannot answer that."}],
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("What's the weather?")

        # No SQL → text is the answer, not an interpretation.
        assert result["answer"] == "I cannot answer that."
        assert result["interpretation"] is None
        assert result["sql"] is None
        assert result["error"] is None

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_http_error_returns_error_dict(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_post.side_effect = Exception("Connection refused")

        result = query_cortex_analyst("test question")

        assert result["answer"] == ""
        assert result["sql"] is None
        assert "couldn't answer" in result["error"]

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_connection_closed_after_call(self, mock_get_conn, mock_post):
        mock_conn = self._mock_connection()
        mock_get_conn.return_value = mock_conn
        mock_resp = MagicMock()
        mock_resp.json.return_value = ANALYST_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        query_cortex_analyst("test")

        mock_conn.close.assert_called_once()

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_connection_closed_on_error(self, mock_get_conn, mock_post):
        mock_conn = self._mock_connection()
        mock_get_conn.return_value = mock_conn
        mock_post.side_effect = Exception("fail")

        query_cortex_analyst("test")

        mock_conn.close.assert_called_once()

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_posts_to_correct_url(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = ANALYST_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch("app.snowflake_client.settings") as mock_settings:
            mock_settings.snowflake_account = "OJIDCKD-MDC60154"
            query_cortex_analyst("test")

        call_url = mock_post.call_args[0][0]
        parsed = urlparse(call_url)
        assert parsed.hostname == "ojidckd-mdc60154.snowflakecomputing.com"
        assert parsed.path == "/api/v2/cortex/analyst/message"

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_sends_auth_header_with_token(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = ANALYST_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        query_cortex_analyst("test")

        call_headers = mock_post.call_args[1]["headers"]
        assert "Snowflake Token=" in call_headers["Authorization"]
        assert "fake-session-token" in call_headers["Authorization"]

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_multiple_text_blocks_joined_into_interpretation(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {
                "role": "analyst",
                "content": [
                    {"type": "text", "text": "Part one."},
                    {"type": "text", "text": "Part two."},
                    {"type": "sql", "statement": "SELECT 1"},
                ],
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        # SQL present → text items become interpretation, joined by double newline.
        assert result["answer"] == ""
        assert "Part one." in result["interpretation"]
        assert "Part two." in result["interpretation"]
        assert result["sql"] == "SELECT 1"

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_suggestions_parsed(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {
                "role": "analyst",
                "content": [
                    {"type": "text", "text": "Here are some suggestions:"},
                    {
                        "type": "suggestions",
                        "suggestions": [
                            "How many mines are in PA?",
                            "What is the total tonnage?",
                        ],
                    },
                ],
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["suggestions"] == [
            "How many mines are in PA?",
            "What is the total tonnage?",
        ]

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_no_suggestions_returns_none(self, mock_get_conn, mock_post):
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = ANALYST_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["suggestions"] is None

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_no_text_no_sql_returns_empty(self, mock_get_conn, mock_post):
        """Empty content → answer and interpretation are both empty/None."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"role": "analyst", "content": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["answer"] == ""
        assert result["interpretation"] is None
        assert result["sql"] is None

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_suggestions_response_text_is_answer_not_interpretation(self, mock_get_conn, mock_post):
        """Out-of-scope: text + suggestions (no SQL) → text is the answer, not interpretation."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {
                "role": "analyst",
                "content": [
                    {"type": "text", "text": "I cannot answer that. Try these instead:"},
                    {"type": "suggestions", "suggestions": ["Mine production?", "Active mines?"]},
                ],
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("What is the meaning of life?")

        assert result["answer"] == "I cannot answer that. Try these instead:"
        assert result["interpretation"] is None
        assert result["sql"] is None
        assert result["suggestions"] == ["Mine production?", "Active mines?"]

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_http_error_status_returns_error_dict(self, mock_get_conn, mock_post):
        """resp.ok=False triggers raise_for_status → caught by except → error dict."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("500 Server Error")
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["error"] is not None
        assert "couldn't answer" in result["error"]
        assert result["answer"] == ""

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_missing_message_key_returns_empty(self, mock_get_conn, mock_post):
        """Response without 'message' key should not crash."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {}
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["answer"] == ""
        assert result["sql"] is None

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_sql_without_statement_key_defaults_empty(self, mock_get_conn, mock_post):
        """SQL item missing 'statement' key defaults to empty string."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "message": {
                "role": "analyst",
                "content": [{"type": "sql"}],
            }
        }
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["sql"] == ""

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_interpretation_joined_with_double_newline(self, mock_get_conn, mock_post):
        """Multiple text blocks must be joined by exactly two newlines."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "message": {
                "role": "analyst",
                "content": [
                    {"type": "text", "text": "Alpha"},
                    {"type": "text", "text": "Beta"},
                    {"type": "sql", "statement": "SELECT 1"},
                ],
            }
        }
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["interpretation"] == "Alpha\n\nBeta"

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_multiple_text_blocks_no_sql_joined_as_answer(self, mock_get_conn, mock_post):
        """Multiple text blocks without SQL → joined as answer, not interpretation."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "message": {
                "role": "analyst",
                "content": [
                    {"type": "text", "text": "Part 1."},
                    {"type": "text", "text": "Part 2."},
                ],
            }
        }
        mock_post.return_value = mock_resp

        result = query_cortex_analyst("test")

        assert result["answer"] == "Part 1.\n\nPart 2."
        assert result["interpretation"] is None

    @patch("app.snowflake_client.requests.post")
    @patch("app.snowflake_client._get_connection")
    def test_sends_question_in_request_body(self, mock_get_conn, mock_post):
        """The question must appear in the POST body."""
        mock_get_conn.return_value = self._mock_connection()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = ANALYST_RESPONSE
        mock_post.return_value = mock_resp

        query_cortex_analyst("How many mines in PA?")

        body = mock_post.call_args[1]["json"]
        assert body["messages"][0]["content"][0]["text"] == "How many mines in PA?"


class TestExecuteAnalystSql:
    def _mock_connection(self, rows):
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn

    @patch("app.snowflake_client._get_connection")
    def test_select_executes(self, mock_get_conn):
        mock_get_conn.return_value = self._mock_connection([{"TOTAL_TONS": 5000000}])
        results = execute_analyst_sql("SELECT SUM(TOTAL_TONS) AS TOTAL_TONS FROM ...")
        assert results == [{"TOTAL_TONS": 5000000}]

    @patch("app.snowflake_client._get_connection")
    def test_uses_readonly_role(self, mock_get_conn):
        mock_get_conn.return_value = self._mock_connection([])
        execute_analyst_sql("SELECT 1")
        mock_get_conn.assert_called_once_with(role="UNEARTHED_READONLY_ROLE")

    @patch("app.snowflake_client._get_connection")
    def test_select_case_insensitive(self, mock_get_conn):
        mock_get_conn.return_value = self._mock_connection([{"X": 1}])
        results = execute_analyst_sql("select 1 as X")
        assert results == [{"X": 1}]

    @patch("app.snowflake_client._get_connection")
    def test_with_cte_allowed(self, mock_get_conn):
        mock_get_conn.return_value = self._mock_connection([{"X": 1}])
        results = execute_analyst_sql("WITH cte AS (SELECT 1 AS X) SELECT * FROM cte")
        assert results == [{"X": 1}]

    @patch("app.snowflake_client._get_connection")
    def test_trailing_semicolon_stripped_and_executed(self, mock_get_conn):
        # Cortex Analyst always appends a trailing semicolon.
        # execute_analyst_sql must strip it and execute the clean statement.
        mock_get_conn.return_value = self._mock_connection([{"X": 1}])
        results = execute_analyst_sql("SELECT 1 AS X;")
        assert results == [{"X": 1}]

    def test_drop_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("DROP TABLE users")

    def test_insert_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("INSERT INTO t VALUES (1)")

    def test_update_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("UPDATE t SET x = 1")

    def test_multi_statement_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("SELECT 1; DROP TABLE users")

    def test_delete_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("DELETE FROM t WHERE 1=1")

    def test_create_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("CREATE TABLE t (id INT)")

    def test_truncate_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("TRUNCATE TABLE t")

    def test_grant_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("GRANT SELECT ON t TO PUBLIC")

    def test_select_into_with_create_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("SELECT 1; CREATE TABLE t AS SELECT 1")

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="read-only"):
            execute_analyst_sql("   ")

    @patch("app.snowflake_client._get_connection")
    def test_connection_closed(self, mock_get_conn):
        mock_conn = self._mock_connection([])
        mock_get_conn.return_value = mock_conn
        execute_analyst_sql("SELECT 1")
        mock_conn.close.assert_called_once()

    @patch("app.snowflake_client._get_connection")
    def test_connection_closed_on_error(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.execute.side_effect = Exception("fail")
        mock_get_conn.return_value = mock_conn

        with pytest.raises(Exception, match="fail"):
            execute_analyst_sql("SELECT 1")

        mock_conn.close.assert_called_once()

    @patch("app.snowflake_client._get_connection")
    def test_session_timeout_set_before_query(self, mock_get_conn):
        """ALTER SESSION must be called before the actual SQL to enforce timeout."""
        mock_conn = self._mock_connection([])
        mock_get_conn.return_value = mock_conn
        execute_analyst_sql("SELECT 1")

        cursor = mock_conn.cursor.return_value
        calls = [str(c) for c in cursor.execute.call_args_list]
        assert "STATEMENT_TIMEOUT_IN_SECONDS" in calls[0]
        assert "SELECT 1" in calls[1]

    @patch("app.snowflake_client._get_connection")
    def test_fetchmany_limited_to_500(self, mock_get_conn):
        """Results must be capped at 500 rows."""
        mock_conn = self._mock_connection([{"X": 1}])
        mock_get_conn.return_value = mock_conn
        execute_analyst_sql("SELECT 1")

        cursor = mock_conn.cursor.return_value
        cursor.fetchmany.assert_called_once_with(500)

    @patch("app.snowflake_client._get_connection")
    def test_cursor_closed_in_execute(self, mock_get_conn):
        """Cursor must be closed via finally block after execution."""
        mock_conn = self._mock_connection([])
        mock_get_conn.return_value = mock_conn
        execute_analyst_sql("SELECT 1")

        mock_conn.cursor.return_value.close.assert_called_once()

    @patch("app.snowflake_client._get_connection")
    def test_multiple_trailing_semicolons_stripped(self, mock_get_conn):
        """Leading/trailing whitespace and semicolons must be fully stripped."""
        mock_conn = self._mock_connection([{"X": 1}])
        mock_get_conn.return_value = mock_conn
        execute_analyst_sql("  SELECT 1 ;  ")

        cursor = mock_conn.cursor.return_value
        # Second execute call is the actual SQL (first is ALTER SESSION)
        actual_sql = cursor.execute.call_args_list[1][0][0]
        assert actual_sql == "SELECT 1"
