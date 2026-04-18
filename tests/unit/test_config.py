"""Unit tests for app configuration."""

import os
from unittest.mock import patch

import pytest

from app.config import Settings, _SettingsProxy, get_settings

# Prevent .env from leaking into tests
_CLEAN_ENV = {
    k: v
    for k, v in os.environ.items()
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
        assert s.snowflake_readonly_role == "UNEARTHED_READONLY_ROLE"
        assert s.snowflake_warehouse == "UNEARTHED_APP_WH"
        assert s.snowflake_database == "UNEARTHED_DB"
        assert s.gemini_model == "gemini-3.1-flash-lite-preview"
        assert s.snowflake_password == ""
        assert s.snowflake_private_key_path == ""
        assert s.gemini_api_key == ""
        assert s.allow_password_auth is False

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

    @patch.dict(os.environ, _CLEAN_ENV, clear=True)
    def test_constructs_without_snowflake_vars(self):
        s = Settings(gemini_api_key="AIza-fake", _env_file=None)
        assert s.snowflake_account == ""
        assert s.snowflake_user == ""
        assert s.gemini_api_key == "AIza-fake"

    def test_gemini_api_key(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            gemini_api_key="AIza-fake",
            _env_file=None,
        )
        assert s.gemini_api_key == "AIza-fake"

    def test_allow_password_auth_explicit_true(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            allow_password_auth=True,
            _env_file=None,
        )
        assert s.allow_password_auth is True

    def test_snowflake_readonly_role_can_be_overridden(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            snowflake_readonly_role="MY_READONLY_ROLE",
            _env_file=None,
        )
        assert s.snowflake_readonly_role == "MY_READONLY_ROLE"

    def test_gemini_model_can_be_overridden(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            gemini_model="gemini-pro",
            _env_file=None,
        )
        assert s.gemini_model == "gemini-pro"

    def test_private_key_passphrase_defaults_empty(self):
        s = Settings(
            snowflake_account="test",
            snowflake_user="user",
            _env_file=None,
        )
        assert s.snowflake_private_key_passphrase == ""

    @patch.dict(os.environ, {**_CLEAN_ENV, "SNOWFLAKE_ACCOUNT": "env-account", "SNOWFLAKE_USER": "env-user"}, clear=True)
    def test_reads_from_environment_variables(self):
        s = Settings(_env_file=None)
        assert s.snowflake_account == "env-account"
        assert s.snowflake_user == "env-user"


class TestGetSettings:
    def test_get_settings_returns_settings_instance(self):
        # Clear lru_cache to ensure a fresh call
        get_settings.cache_clear()
        s = get_settings()
        assert isinstance(s, Settings)

    def test_get_settings_is_cached(self):
        """Two calls to get_settings() must return the exact same object."""
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_cache_clear(self):
        """After cache_clear(), get_settings() returns a new object."""
        get_settings.cache_clear()
        s1 = get_settings()
        get_settings.cache_clear()
        s2 = get_settings()
        # They may be equal by value but after cache clear they are different objects.
        assert s1 is not s2


class TestSettingsProxy:
    def test_proxy_forwards_attribute_access(self):
        """_SettingsProxy must delegate attribute lookups to get_settings()."""
        proxy = _SettingsProxy()
        with patch("app.config.get_settings") as mock_get:
            mock_settings = Settings(
                snowflake_account="proxy-account",
                snowflake_user="user",
                _env_file=None,
            )
            mock_get.return_value = mock_settings
            assert proxy.snowflake_account == "proxy-account"

    def test_proxy_missing_attr_raises(self):
        proxy = _SettingsProxy()
        with pytest.raises(AttributeError):
            _ = proxy.nonexistent_attribute_xyz

    def test_module_level_settings_is_proxy(self):
        """The module-level `settings` object must be a _SettingsProxy."""
        from app.config import settings
        assert isinstance(settings, _SettingsProxy)

    def test_module_level_settings_forwards_snowflake_role(self):
        """Accessing settings.snowflake_role through proxy must not crash."""
        from app.config import settings
        # Will read from actual env / defaults — just ensure no AttributeError.
        _ = settings.snowflake_role
