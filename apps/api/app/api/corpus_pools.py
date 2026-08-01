from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_editorial_service
from app.core.config import get_settings
from app.db.session import get_db
from app.domain.schemas import (
    CorpusBatchOut,
    CorpusPoolBatchRequest,
    CorpusPoolCreateRequest,
    CorpusPoolDetail,
    CorpusPoolDraftResult,
    CorpusPoolGenerateRequest,
    CorpusPoolOut,
    CorpusPoolSourcesRequest,
    CorpusPoolUpdateRequest,
)
from app.services.corpus_pools import CorpusPoolError, CorpusPoolService
from app.services.editorial import EditorialService

router = APIRouter(prefix="/api/corpus-pools", tags=["corpus-pools"])


def _service() -> CorpusPoolService:
    return CorpusPoolService(get_settings())


def _bad_request(exc: CorpusPoolError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[CorpusPoolOut])
def list_corpus_pools(
    state: str = Query(default="active"),
    db: Session = Depends(get_db),
) -> list[dict]:
    try:
        return _service().list_pools(db, state=state)
    except CorpusPoolError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "",
    response_model=CorpusPoolDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_corpus_pool(
    body: CorpusPoolCreateRequest,
    db: Session = Depends(get_db),
) -> dict:
    service = _service()
    try:
        pool = service.create_pool(
            db,
            source_ids=body.source_ids,
            name=body.name,
            description=body.description,
            batch_size=body.batch_size,
        )
        db.commit()
        return service.detail(db, pool.id)
    except CorpusPoolError as exc:
        db.rollback()
        raise _bad_request(exc) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"创建语料池失败：{str(exc)[:800]}",
        ) from exc


@router.get("/{pool_id}", response_model=CorpusPoolDetail)
def get_corpus_pool(pool_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return _service().detail(db, pool_id)
    except CorpusPoolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{pool_id}", response_model=CorpusPoolDetail)
def update_corpus_pool(
    pool_id: str,
    body: CorpusPoolUpdateRequest,
    db: Session = Depends(get_db),
) -> dict:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        service.update_pool(
            db,
            pool,
            name=body.name,
            description=body.description,
            batch_size=body.batch_size,
            state=body.state,
            unlock_name=body.unlock_name,
        )
        db.commit()
        return service.detail(db, pool.id)
    except CorpusPoolError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.delete("/{pool_id}", status_code=204)
def delete_corpus_pool(pool_id: str, db: Session = Depends(get_db)) -> None:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        service.delete_pool(db, pool)
        db.commit()
    except CorpusPoolError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{pool_id}/sources", response_model=CorpusPoolDetail)
def add_corpus_pool_sources(
    pool_id: str,
    body: CorpusPoolSourcesRequest,
    db: Session = Depends(get_db),
) -> dict:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        service.add_sources(db, pool, body.source_ids)
        db.commit()
        return service.detail(db, pool.id)
    except CorpusPoolError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.delete("/{pool_id}/sources/{source_id}", response_model=CorpusPoolDetail)
def remove_corpus_pool_source(
    pool_id: str,
    source_id: str,
    db: Session = Depends(get_db),
) -> dict:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        service.remove_source(db, pool, source_id)
        db.commit()
        return service.detail(db, pool.id)
    except CorpusPoolError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.post("/{pool_id}/compile", response_model=CorpusPoolDetail)
def compile_corpus_pool(pool_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        service.compile_pool(db, pool)
        db.commit()
        return service.detail(db, pool.id)
    except CorpusPoolError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.post("/{pool_id}/preview-batch", response_model=CorpusBatchOut)
def preview_corpus_batch(
    pool_id: str,
    body: CorpusPoolBatchRequest,
    db: Session = Depends(get_db),
) -> dict:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        return service.preview_batch(
            db,
            pool,
            batch_size=body.batch_size,
            focus=body.focus,
        )
    except CorpusPoolError as exc:
        raise _bad_request(exc) from exc


@router.get("/{pool_id}/batches", response_model=list[CorpusBatchOut])
def list_corpus_batches(pool_id: str, db: Session = Depends(get_db)) -> list[dict]:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        return service.list_batches(db, pool)
    except CorpusPoolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{pool_id}/drafts", response_model=CorpusPoolDraftResult)
async def generate_corpus_pool_draft(
    pool_id: str,
    body: CorpusPoolGenerateRequest,
    db: Session = Depends(get_db),
    editorial: EditorialService = Depends(get_editorial_service),
) -> dict:
    service = _service()
    try:
        pool = service.get_pool(db, pool_id)
        batch, anchor, _ = service.create_generation_batch(
            db,
            pool,
            batch_size=body.batch_size,
            focus=body.focus,
        )
        draft = await editorial.generate(db, anchor, body.style)
        service.finalize_batch(db, pool=pool, batch=batch, draft=draft)
        db.commit()
        db.refresh(draft)
        pool_payload = service.detail(db, pool.id)
        batch_payload = next(
            item for item in pool_payload["batches"] if item["id"] == batch.id
        )
        return {
            "pool": pool_payload,
            "batch": batch_payload,
            "draft": draft,
        }
    except CorpusPoolError as exc:
        db.rollback()
        raise _bad_request(exc) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"语料池批次生成失败：{str(exc)[:1200]}",
        ) from exc
