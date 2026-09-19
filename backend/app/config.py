from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/crm.db"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    n8n_webhook_url: str = ""
    n8n_public_url: str = "http://localhost:5678"
    webhook_secret: str = "dev-webhook-secret-change-me"
    log_level: str = "INFO"
    google_sheets_credentials_file: str = ""
    google_sheets_credentials_json: str = ""
    google_sheets_spreadsheet_id: str = ""
    google_sheets_worksheet: str = "Qualified Leads"

    @property
    def groq_enabled(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token.strip() and self.telegram_chat_id.strip())

    @property
    def google_sheets_enabled(self) -> bool:
        has_creds = bool(
            self.google_sheets_credentials_file.strip()
            or self.google_sheets_credentials_json.strip()
        )
        return has_creds and bool(self.google_sheets_spreadsheet_id.strip())

    @property
    def n8n_sheets_configured(self) -> bool:
        return bool(self.google_sheets_spreadsheet_id.strip())

    @property
    def n8n_executions_url(self) -> str:
        base = self.n8n_public_url.strip().rstrip("/") or "http://localhost:5678"
        return f"{base}/home/executions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
