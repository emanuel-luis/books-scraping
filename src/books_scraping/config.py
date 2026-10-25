"""Settings read from BOOKS_* environment variables and an optional .env file."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from books_scraping import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BOOKS_", env_file=".env", extra="ignore")

    base_url: str = "https://books.toscrape.com/"
    data_dir: Path = Path("data")
    user_agent: str = Field(
        default_factory=lambda: (
            f"books-scraping/{__version__} (+https://github.com/emanuel-luis/books-scraping)"
        )
    )
    min_interval_s: float = Field(default=0.5, ge=0)
    timeout_s: float = Field(default=20, gt=0)
    max_retries: int = Field(default=4, ge=1)
    fx_url: str = "https://api.frankfurter.dev/v1"
    fx_quotes: str = "EUR,USD,BRL"
    log_level: str = "INFO"
