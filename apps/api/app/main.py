from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import (
    assets,
    cards,
    corpus_pools,
    discovery,
    drafts,
    extension,
    intake,
    integrations,
    jobs,
    materials,
    native_skills,
    platforms,
    publish,
    reviews,
    settings as settings_api,
    signals,
    sources,
    writing,
)
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.domain import review_artifacts as review_artifact_models  # noqa: F401
from app.domain.studio import ContentAnalysis, WritingProject
from app.providers.fxtwitter import FxTwitterProvider
from app.services.discovery import DiscoveryService
from app.services.intake import IntakeService
from app.services.jobs import JobEngine
from app.services.media_store import MediaStore
from app.services.native_cards import NativeAwareCardService
from app.services.platform_studio import PlatformStudioService
from app.services.publisher import PublishService
from app.services.raw_store import RawStore
from app.services.review_flow import ReviewFlowService
from app.services.signal_studio import SignalStudioService
from app.services.skill_pack_editorial import SkillPackEditorialService
from app.services.studio_scheduler import StudioScheduler
from app.services.writing_studio import MultiAgentWritingService
from app.services.x2pdf_import import X2PDFImportService

settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"
STYLESHEET = (
    "[hidden]{display:none!important;}\n"
    + (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    + "\n"
    + (STATIC_DIR / "workbench-v06.css").read_text(encoding="utf-8")
    + "\n"
    + (STATIC_DIR / "studio-v07.css").read_text(encoding="utf-8")
    + "\n"
    + (STATIC_DIR / "style-v07.css").read_text(encoding="utf-8")
    + "\n"
    + (STATIC_DIR / "platform-v08.css").read_text(encoding="utf-8")
)


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
    raw_store = RawStore(settings.raw_dir)
    intake_service = IntakeService(settings, provider, raw_store, media_store)
    editorial_service = SkillPackEditorialService(settings)
    writing_service = MultiAgentWritingService(settings, editorial_service)
    signal_service = SignalStudioService(settings, provider, raw_store, editorial_service)
    platform_service = PlatformStudioService(settings, editorial_service)
    card_service = NativeAwareCardService(settings)
    review_flow_service = ReviewFlowService(
        settings,
        card_service,
        platform_service,
    )
    job_engine = JobEngine(intake_service)

    async def scan_target_handler(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        result = await signal_service.scan_target(db, str(payload["target_id"]))
        auto_l1 = {item.strip() for item in settings.auto_l1_grades.split(",") if item.strip()}
        auto_l2 = {item.strip() for item in settings.auto_l2_grades.split(",") if item.strip()}
        queued: list[dict[str, str]] = []
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        l2_count = int(
            db.scalar(
                select(func.count(ContentAnalysis.id)).where(
                    ContentAnalysis.level == "l2",
                    ContentAnalysis.created_at >= today_start,
                )
            )
            or 0
        )
        for item in result.get("scored", []):
            grade = str(item.get("grade") or "")
            candidate_id = str(item.get("candidate_id") or "")
            if not candidate_id:
                continue
            if grade in auto_l1:
                job_engine.enqueue(
                    db,
                    kind="signal.analyze",
                    payload={"candidate_id": candidate_id, "level": "l1"},
                    priority=95,
                    max_attempts=2,
                    dedupe_key=f"signal.analyze:{candidate_id}:l1",
                )
                queued.append({"candidate_id": candidate_id, "level": "l1"})
            if (
                grade in auto_l2
                and settings.auto_l2_daily_limit > 0
                and l2_count < settings.auto_l2_daily_limit
            ):
                job_engine.enqueue(
                    db,
                    kind="signal.analyze",
                    payload={"candidate_id": candidate_id, "level": "l2"},
                    priority=90,
                    max_attempts=2,
                    dedupe_key=f"signal.analyze:{candidate_id}:l2",
                )
                queued.append({"candidate_id": candidate_id, "level": "l2"})
                l2_count += 1
        result["analysis_jobs"] = queued
        return result

    async def analyze_handler(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = await signal_service.analyze_candidate(
            db,
            candidate_id=str(payload["candidate_id"]),
            level=str(payload.get("level") or "l1"),
        )
        return {
            "analysis_id": analysis.id,
            "candidate_id": analysis.candidate_id,
            "level": analysis.level,
            "status": analysis.status,
        }

    async def writing_handler(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        project = db.get(WritingProject, str(payload["project_id"]))
        if project is None:
            raise ValueError("写作项目不存在")
        artifacts = (
            await writing_service.run_until_gate(db, project)
            if bool(payload.get("continuous", True))
            else [await writing_service.run_next(db, project)]
        )
        return {
            "project_id": project.id,
            "state": project.state,
            "current_stage": project.current_stage,
            "artifact_ids": [artifact.id for artifact in artifacts],
        }

    async def style_training_handler(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        profile = await writing_service.train_style(
            db,
            name=str(payload["name"]),
            description=str(payload.get("description") or ""),
            original_samples=[str(item) for item in payload.get("original_samples") or []],
            held_out_samples=[str(item) for item in payload.get("held_out_samples") or []],
            author_feedback=[str(item) for item in payload.get("author_feedback") or []],
        )
        return {
            "style_profile_id": profile.id,
            "name": profile.name,
            "version": profile.version,
        }

    job_engine.register("signal.scan_target", scan_target_handler)
    job_engine.register("signal.analyze", analyze_handler)
    job_engine.register("writing.advance", writing_handler)
    job_engine.register("writing.train_style", style_training_handler)
    scheduler = StudioScheduler(settings, job_engine, signal_service)

    app.state.provider = provider
    app.state.media_store = media_store
    app.state.intake_service = intake_service
    app.state.discovery_service = DiscoveryService(provider, raw_store)
    app.state.job_engine = job_engine
    app.state.editorial_service = editorial_service
    app.state.writing_service = writing_service
    app.state.signal_service = signal_service
    app.state.platform_service = platform_service
    app.state.review_flow_service = review_flow_service
    app.state.scheduler = scheduler
    app.state.card_service = card_service
    app.state.publish_service = PublishService(settings)
    app.state.x2pdf_import_service = X2PDFImportService(raw_store)

    await job_engine.start()
    scheduler.start()
    yield
    scheduler.stop()
    await job_engine.stop()
    await provider.close()
    await media_store.close()


app = FastAPI(title="X2RED", version="0.11.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://[a-z]{32}|http://(?:127\.0\.0\.1|localhost)(?::\d+)?)$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(jobs.router)
app.include_router(discovery.router)
app.include_router(signals.router)
app.include_router(writing.router)
app.include_router(platforms.router)
app.include_router(reviews.router)
app.include_router(intake.router)
app.include_router(integrations.router)
app.include_router(materials.router)
app.include_router(corpus_pools.router)
app.include_router(native_skills.router)
app.include_router(assets.router)
app.include_router(sources.router)
app.include_router(drafts.router)
app.include_router(cards.router)
app.include_router(publish.router)
app.include_router(settings_api.router)
app.include_router(extension.router)


@app.get("/static/styles.css", include_in_schema=False)
def stylesheet() -> Response:
    return Response(STYLESHEET, media_type="text/css")


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
        "editorial_pipeline": "multi-agent-signal-to-story-plus-platform-skill-packs"
        if model_configured
        else "multi-agent-structured-fallback",
        "intelligence_pipeline": "monitor-score-l1-l2",
        "writing_pipeline": "editor-research-outline-writer-three-reviews-chief-editor",
        "style_pipeline": "original-samples-held-out-feedback",
        "platform_pipeline": "reviewable-artifacts-shared-evidence-platform-variants",
        "review_pipeline": "storyboard-module-tree-cover-brief-versioned-approval",
        "light_content_pipeline": "corpus-grounded-multi-agent-candidates-independent-reviews-human-gate",
        "corpus_pool_pipeline": "compiled-global-memory-plus-rotating-detailed-batches",
        "corpus_pools": True,
        "light_content_lab": True,
        "light_content_source_fit_gate": True,
        "signal_to_studio": True,
        "platforms": ["xiaohongshu", "wechat"],
        "wechat_workbench": True,
        "wechat_light_series": True,
        "wechat_publisher_assistant": True,
        "skill_pack_registry": True,
        "scheduler_enabled": settings.scheduler_enabled,
        "sqlite_wal": settings.database_url.startswith("sqlite"),
        "x2pdf_bridge": "/api/integrations/x2pdf/documents",
        "card_renderer": "reviewed-semantic-playwright",
        "native_card_renderer": "guizang-native-upstream-seed-playwright",
        "wechat_renderer": "reviewed-module-tree-plus-cover-brief",
        "light_content_renderer": "six-route-distinct-visual-v12-or-native-minimal-zine-image",
        "material_pipeline": "mediacrawler-cdp-jsonl-limited-quote",
        "native_skill_runtime": True,
        "native_skill_source_available": True,
        "image_generation_configured": bool(
            settings.image_model and (settings.image_base_url or settings.model_base_url)
        ),
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
        "native_skills": settings.native_skill_dir,
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
        "scheduler": "enabled" if settings.scheduler_enabled else "disabled",
    }


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    scripts = (
        '<script src="/static/studio-v07.js"></script>'
        '<script src="/static/style-v07.js"></script>'
        '<script src="/static/platform-v08.js"></script>'
        '<script src="/static/card-skill-v08.js"></script>'
        '<script src="/static/review-v09.js"></script>'
        '<script src="/static/review-bridge-v09.js"></script>'
        '<script src="/static/signal-to-studio-v10.js"></script>'
        '<script src="/static/materials-v11.js"></script>'
        '<script src="/static/corpus-pools-v13.js"></script>'
        '<script src="/static/product-shell-v15.js"></script>'
        '<script src="/static/light-content-v15.js"></script>'
        '<script src="/static/native-skills-v11.js"></script>'
    )
    html = html.replace("</body>", f"{scripts}</body>")
    return HTMLResponse(html)
