from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DeepGen"
    database_url: str = "sqlite:///./deepgen.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"
    llm_backend: str = "openai"
    mlx_model: str = "mlx-community/Llama-3.2-3B-Instruct-4bit"
    enable_mlx: bool = False
    research_v2_enabled: bool = True
    research_prompt_template_version: str = "v2"
    familysearch_access_token: str | None = None
    nara_api_key: str | None = None
    loc_api_key: str | None = None
    census_api_key: str | None = None
    geonames_username: str | None = None
    europeana_api_key: str | None = None
    openrefine_service_url: str | None = None
    gnis_dataset_path: str | None = None
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
