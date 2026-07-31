from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import assets, cards, drafts, extension, intake, publish, sources
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.providers.fxtwitter import FxTwitterProvider
from app.services.cards import CardService
from app.services.editorial import EditorialService
from app.services.intake import IntakeService
from app.services.media_store import MediaStore
from app.services.publisher import PublishService
from app.services.raw_store import RawStore

settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    app.state.provider = provider
    app.state.media_store = media_store
    app.state.intake_service = IntakeService(
        settings,
        provider,
        RawStore(settings.raw_dir),
        media_store,
    )
    app.state.editorial_service = EditorialService(settings)
    app.state.card_service = CardService(settings)
    app.state.publish_service = PublishService(settings)
    yield
    await provider.close()
    await media_store.close()


app = FastAPI(title="X2RED", version="0.2.0", lifespan=lifespan)
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
    return {"ok": True, "name": settings.app_name, "version": app.version}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
