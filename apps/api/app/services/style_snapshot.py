from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import DraftRevision, SourceItem
from app.domain.studio import StyleProfile, WritingArtifact, WritingProject
from app.domain.style_snapshot import WritingStyleSnapshot
from app.services.pool_memory import PoolMemoryService

_DEFAULT_STYLE = {
    "identity": "专业但不端着的中文内容创作者",
    "reader_relationship": "把复杂问题讲给聪明但不熟悉细节的读者",
    "rhythm": "短段落；先建立画面，再解释术语；判断落在具体证据上",
    "forbidden": [
        "阅读时注意以下边界",
        "本文基于已归档来源整理",
        "值得关注的3个点",
        "不难发现",
        "总的来说",
    ],
}


class StyleSnapshotMixin:
    def create_project(
        self,
        db: Session,
        *,
        source: SourceItem,
        mode: str,
        reader: str,
        promise: str,
        main_thesis: str,
        style_profile_id: str | None,
        budget_limit_cents: int,
    ) -> WritingProject:
        profile = db.get(StyleProfile, style_profile_id) if style_profile_id else None
        if style_profile_id and profile is None:
            raise ValueError("风格档案不存在")

        project = super().create_project(
            db,
            source=source,
            mode=mode,
            reader=reader,
            promise=promise,
            main_thesis=main_thesis,
            style_profile_id=style_profile_id,
            budget_limit_cents=budget_limit_cents,
        )
        payload: dict[str, Any]
        if profile is None:
            payload = dict(_DEFAULT_STYLE)
            profile_name = "Default"
            profile_version = 0
        else:
            samples = self._json(profile.samples_json, {})
            samples_serialized = json.dumps(samples, ensure_ascii=False, sort_keys=True)
            payload = {
                "name": profile.name,
                "description": profile.description,
                "rules": self._json(profile.rules_json, {}),
                "forbidden": self._json(profile.forbidden_json, []),
                "sample_bundle": {
                    "stored_in_style_profile": True,
                    "content_injected": False,
                    "sha256": hashlib.sha256(samples_serialized.encode()).hexdigest(),
                    "note": "原始样本不整包注入；需要长期复用的短例应经人工批准进入池子记忆。",
                },
                "version": profile.version,
            }
            profile_name = profile.name
            profile_version = profile.version
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        snapshot = WritingStyleSnapshot(
            project_id=project.id,
            style_profile_id=profile.id if profile else None,
            style_profile_version=profile_version,
            profile_name=profile_name,
            snapshot_json=serialized,
            snapshot_hash=hashlib.sha256(serialized.encode()).hexdigest(),
        )
        db.add(snapshot)
        db.flush()
        memory_service = PoolMemoryService(self.settings, self.editorial)
        memory_service.create_snapshot(
            db,
            target_type="writing_project",
            target_id=project.id,
            query={
                "platform": "xhs",
                "format": "article",
                "article_type": "technical_explainer",
                "style_profile_id": profile.id if profile else "",
                "audience": project.reader,
                "source_text": source.text_original[:30000],
                "topics": [project.main_thesis] if project.main_thesis else [],
                "limit": 6,
                "max_chars": 6500,
            },
            model_configured=bool(self.settings.model_base_url and self.settings.model_name),
            model_name=self.settings.model_name,
        )
        return project

    def _style_payload(self, db: Session, project: WritingProject) -> dict[str, Any]:
        snapshot = self.style_snapshot(db, project.id)
        if snapshot is not None:
            return self._json(snapshot.snapshot_json, dict(_DEFAULT_STYLE))
        # Compatibility for projects created before migration 0007.
        return super()._style_payload(db, project)

    def _create_draft_revision(
        self,
        db: Session,
        project: WritingProject,
        artifact: WritingArtifact,
    ) -> DraftRevision:
        draft = super()._create_draft_revision(db, project, artifact)
        snapshot = self.style_snapshot(db, project.id)
        if snapshot is None:
            return draft
        provenance = self._json(draft.provenance_json, {})
        provenance.update(
            {
                "style_snapshot_id": snapshot.id,
                "style_profile_version": snapshot.style_profile_version,
                "style_snapshot_hash": snapshot.snapshot_hash,
            }
        )
        draft.provenance_json = json.dumps(provenance, ensure_ascii=False)
        return draft

    def style_snapshot(self, db: Session, project_id: str) -> WritingStyleSnapshot | None:
        return db.scalar(
            select(WritingStyleSnapshot).where(WritingStyleSnapshot.project_id == project_id)
        )
