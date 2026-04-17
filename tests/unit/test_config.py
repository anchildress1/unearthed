"""Unit tests for app configuration."""

import os
from unittest.mock import patch

from app.config import Settings

# Prevent .env from leaking into tests
_CLEAN_ENV = {
    k: v for k, v in os.environ.items()
    if not k.startswith("SNOWFLAKE_") and not k.startswith("GEMINI_")
}


class TestSettings:
    @patch.dict(os.environ, _CLEAN_ENV, clear=True)
    def test_defaults(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            _env_file=None,
        )
        assert s.snowflake_role == "UNEARTHED_APP_ROLE"
        assert s.snowflake_warehouse == "UNEARTHED_APP_WH"
        assert s.snowflake_database == "UNEARTHED_DB"
        assert s.gemini_model == "gemini-2.0-flash"
        assert s.snowflake_password == ""
        assert s.snowflake_private_key_path == ""
        assert s.gemini_api_key == ""

    def test_password_auth_config(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            snowflake_password="secret",
            _env_file=None,
        )
        assert s.snowflake_password == "secret"
        assert s.snowflake_private_key_path == ""

    def test_keypair_auth_config(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            snowflake_private_key_path="/path/to/key.p8",
            snowflake_private_key_passphrase="pass",
            _env_file=None,
        )
        assert s.snowflake_private_key_path == "/path/to/key.p8"
        assert s.snowflake_private_key_passphrase == "pass"

    def test_gemini_api_key(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            gemini_api_key="AIza-fake",
            _env_file=None,
        )
        assert s.gemini_api_key == "AIza-fake"
