from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/crm.db"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    webhook_secret: str = "dev-webhook-secret-change-me"
    log_level: str = "INFO"

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token.strip() and self.telegram_chat_id.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
