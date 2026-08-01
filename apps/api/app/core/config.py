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
    native_skill_dir: Path = Path("./data/native-skills")
    card_font_path: Path | None = None
    download_media: bool = True
    max_media_bytes: int = Field(default=200 * 1024 * 1024, ge=1)
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = ""
    image_base_url: str = ""
    image_api_key: str = ""
    image_model: str = ""
    image_size: str = "1024x1536"
    request_timeout_seconds: float = 20.0

    material_user_agent: str = "X2RED-MaterialResearch/0.13 (+local research)"
    material_min_interval_seconds: float = Field(default=2.0, ge=0.5, le=60.0)
    material_max_page_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=100_000,
        le=20_000_000,
    )
    material_browser_enabled: bool = True
    material_browser_timeout_seconds: float = Field(default=40.0, ge=5.0, le=180.0)
    material_browser_wait_ms: int = Field(default=1800, ge=0, le=15_000)
    material_search_provider: str = "mediacrawler"

    mediacrawler_root: Path = Path("./.vendor/MediaCrawler")
    mediacrawler_python: str = ""
    mediacrawler_revision: str = "1779dde9725f6b7ef42e29022c0054b3e678f1af"
    mediacrawler_platform: str = "xhs"
    mediacrawler_login_type: str = "qrcode"
    mediacrawler_connect_existing: bool = True
    mediacrawler_cdp_port: int = Field(default=9222, ge=1024, le=65535)
    mediacrawler_timeout_seconds: int = Field(default=600, ge=30, le=3600)
    mediacrawler_max_results: int = Field(default=30, ge=1, le=100)

    # Existing provider configuration remains for old internal modules only;
    # the material-library API and UI do not route through these providers.
    material_gdelt_base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    serpapi_api_key: str = ""
    serpapi_base_url: str = "https://serpapi.com/search.json"
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    dataforseo_base_url: str = "https://api.dataforseo.com"
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    tavily_search_depth: str = "basic"
    brave_search_api_key: str = ""
    brave_search_base_url: str = "https://api.search.brave.com/res/v1/web/search"

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
            self.native_skill_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
