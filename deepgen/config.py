from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DeepGen"
    database_url: str = "sqlite:///./deepgen.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    llm_backend: str = "openai"
    mlx_model: str = "mlx-community/Llama-3.2-3B-Instruct-4bit"
    enable_mlx: bool = False
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
