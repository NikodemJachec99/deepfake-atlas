from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cała konfiguracja z env — zero hardkodowanych sekretów."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    gemini_api_key: str = ""


settings = Settings()
