from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings from environment variables, falling back to .env in the working directory."""

    # extra="ignore": .env also holds Docker-only values such as POSTGRES_USER
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None
    redis_url: str

    # Scraper: an honest user agent with a way to contact us, and a cap on requests per run
    scraper_user_agent: str = (
        "Lakshya/0.1 (+https://github.com/Shubham-0102/Lakshya; yadavvshubham0102@gmail.com)"
    )
    scraper_max_requests: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
