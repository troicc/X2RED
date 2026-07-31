from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import assets, cards, discovery, drafts, extension, intake, jobs, publish, sources
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.providers.fxtwitter import FxTwitterProvider
from app.services.cards import CardService
from app.services.discovery import DiscoveryService
from app.services.editorial import EditorialService
from app.services.intake import IntakeService
from app.services.jobs import JobEngine
from app.services.media_store import MediaStore
from app.services.publisher import PublishService
from app.services.raw_store import RawStore

settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # CLI startup applies versioned Alembic migrations. create_all keeps direct
    # ASGI/test embedding usable for a brand-new SQLite database.
    Base.metadata.create_all(engine)
    provider = FxTwitterProvider(
        settings.fxtwitter_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )
    media_store = MediaStore(
        settings.media_dir,
        max_bytes=settings.max_media_bytes,
        timeout_seconds=settings.request_timeout_seconds,
    )
    raw_store = RawStore(settings.raw_dir)
    intake_service = IntakeService(
        settings,
        provider,
        raw_store,
        media_store,
    )
    job_engine = JobEngine(intake_service)
    app.state.provider = provider
    app.state.media_store = media_store
    app.state.intake_service = intake_service
    app.state.discovery_service = DiscoveryService(provider, raw_store)
    app.state.job_engine = job_engine
    app.state.editorial_service = EditorialService(settings)
    app.state.card_service = CardService(settings)
    app.state.publish_service = PublishService(settings)
    await job_engine.start()
    yield
    await job_engine.stop()
    await provider.close()
    await media_store.close()


app = FastAPI(title="X2RED", version="0.5.0", lifespan=lifespan)
app.include_router(jobs.router)
app.include_router(discovery.router)
app.include_router(intake.router)
app.include_router(assets.router)
app.include_router(sources.router)
app.include_router(drafts.router)
app.include_router(cards.router)
app.include_router(publish.router)
app.include_router(extension.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health() -> dict:
    model_configured = bool(settings.model_base_url and settings.model_name)
    return {
        "ok": True,
        "name": settings.app_name,
        "version": app.version,
        "model_configured": model_configured,
        "model_name": settings.model_name if model_configured else "",
        "editorial_pipeline": "three-pass" if model_configured else "structured-fallback",
    }


@app.get("/ready")
def ready() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database is not ready") from exc

    required_dirs = {
        "media": settings.media_dir,
        "raw": settings.raw_dir,
        "exports": settings.export_dir,
        "browser_profile": settings.browser_profile_dir,
    }
    missing = [name for name, path in required_dirs.items() if not path.is_dir()]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"required directories are not ready: {', '.join(missing)}",
        )
    return {
        "ok": True,
        "database": "ready",
        "directories": sorted(required_dirs),
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
