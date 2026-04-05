import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "GEO Audit API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # OpenRouter / Gemini (optional) — leave blank to use rule-based schema generation
    gemini_api_key: str = ""
    llm_model: str = "google/gemini-2.0-flash-001"
    llm_base_url: str = "https://openrouter.ai/api/v1"

    # Scraping
    REQUEST_TIMEOUT: int = 15
    MAX_HEADINGS: int = 50
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
