from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="X2RED_",
        extra="ignore",
    )

    app_name: str = "X2RED"
    database_url: str = "sqlite:///./data/x2red.db"
    fxtwitter_base_url: str = "https://api.fxtwitter.com"
    media_dir: Path = Path("./data/assets")
    raw_dir: Path = Path("./data/raw")
    export_dir: Path = Path("./data/exports")
    browser_profile_dir: Path = Path("./data/profiles/xhs")
    card_font_path: Path | None = None
    download_media: bool = True
    max_media_bytes: int = Field(default=200 * 1024 * 1024, ge=1)
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = ""
    request_timeout_seconds: float = 20.0
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Shanghai"
    scheduler_poll_seconds: int = Field(default=30, ge=10, le=3600)
    scheduler_batch_size: int = Field(default=20, ge=1, le=200)
    auto_l1_grades: str = "T1,T2,T3"
    auto_l2_grades: str = "T2,T3"
    auto_l2_daily_limit: int = Field(default=5, ge=0, le=100)

    def ensure_directories(self) -> None:
        for path in (
            self.media_dir,
            self.raw_dir,
            self.export_dir,
            self.browser_profile_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
