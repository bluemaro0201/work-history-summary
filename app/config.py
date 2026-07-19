from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    collector_timeout_seconds: int = 30
    collector_max_activities_per_source: int = 100


# Module-level singleton — used by collectors for timeout/max_activities.
settings = Settings()


def get_settings() -> Settings:
    return settings
