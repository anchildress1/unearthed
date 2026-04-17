from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_private_key_path: str = ""
    snowflake_private_key_passphrase: str = ""
    snowflake_role: str = "UNEARTHED_APP_ROLE"
    snowflake_warehouse: str = "UNEARTHED_APP_WH"
    snowflake_database: str = "UNEARTHED_DB"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    allow_password_auth: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    """Lazy proxy so `from app.config import settings` works without
    crashing at import time when env vars are missing."""

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
