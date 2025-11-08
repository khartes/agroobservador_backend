from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_env_files() -> None:
    """Load optional .env files walking up the directory tree."""
    config_path = Path(__file__).resolve()
    checked: set[Path] = set()
    for parent in (config_path.parent, *config_path.parents):
        candidate = parent / ".env"
        if candidate in checked:
            continue
        checked.add(candidate)
        if candidate.exists():
            load_dotenv(candidate, override=False)


_load_env_files()


class Settings(BaseSettings):
    """Application configuration driven by environment variables."""

    project_name: str = "Vazio Sanitario API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://hack_user:hack_pass@db:5432/hackathon"

    model_config = SettingsConfigDict(env_prefix="", extra="allow")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
