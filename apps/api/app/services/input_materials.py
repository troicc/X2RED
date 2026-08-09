from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain.models import DraftRevision, SourceItem
from app.domain.platforms import PlatformVariant


class InputMaterialError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedInputMaterials:
    primary_source: SourceItem
    sources: list[SourceItem]
    materials: list[dict[str, Any]]

    @property
    def refs(self) -> list[str]:
        return [str(item["ref"]) for item in self.materials]


def _object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean_excerpt(value: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _source_title(source: SourceItem) -> str:
    structured = _object(source.structured_content_json)
    return str(structured.get("title") or _clean_excerpt(source.text_original, 100) or "未命名来源")[:160]


def normalize_material_ref(value: str) -> str:
    ref = str(value or "").strip()
    if not ref:
        return ""
    if ":" in ref:
        kind, item_id = ref.split(":", 1)
        aliases = {
            "source": "source",
            "src": "source",
            "draft": "draft",
            "draft_revision": "draft",
            "variant": "variant",
            "platform_variant": "variant",
        }
        normalized = aliases.get(kind.strip().lower())
        if normalized and item_id.strip():
            return f"{normalized}:{item_id.strip()}"
        raise InputMaterialError(f"无法识别输入材料：{ref}")
    if ref.startswith("src_"):
        return f"source:{ref}"
    if ref.startswith("draft_"):
        return f"draft:{ref}"
    if ref.startswith("variant_"):
        return f"variant:{ref}"
    raise InputMaterialError(f"无法识别输入材料：{ref}")


def material_option_payloads(db: Session, *, limit: int = 300) -> list[dict[str, Any]]:
    sources = list(
        db.scalars(
            select(SourceItem)
            .where(SourceItem.workspace_state == "active")
            .order_by(desc(SourceItem.created_at))
            .limit(limit)
        ).all()
    )
    drafts = list(
        db.scalars(
            select(DraftRevision).order_by(desc(DraftRevision.created_at)).limit(limit)
        ).all()
    )
    variants = list(
        db.scalars(
            select(PlatformVariant).order_by(desc(PlatformVariant.updated_at)).limit(limit)
        ).all()
    )
    source_map = {item.id: item for item in sources}
    missing_source_ids = {
        item.source_id for item in [*drafts, *variants] if item.source_id not in source_map
    }
    if missing_source_ids:
        source_map.update(
            {
                item.id: item
                for item in db.scalars(
                    select(SourceItem).where(SourceItem.id.in_(missing_source_ids))
                ).all()
            }
        )

    output: list[dict[str, Any]] = []
    for source in sources:
        output.append(
            {
                "ref": f"source:{source.id}",
                "kind": "source",
                "id": source.id,
                "source_id": source.id,
                "title": _source_title(source),
                "excerpt": _clean_excerpt(source.text_original),
                "author": source.author_name or source.author_handle,
                "platform": source.platform,
                "version": None,
                "status": source.workspace_state,
                "created_at": source.created_at,
            }
        )
    for draft in drafts:
        source = source_map.get(draft.source_id)
        output.append(
            {
                "ref": f"draft:{draft.id}",
                "kind": "draft_revision",
                "id": draft.id,
                "source_id": draft.source_id,
                "title": draft.title or "未命名写作版本",
                "excerpt": _clean_excerpt(draft.body),
                "author": (source.author_name or source.author_handle) if source else "",
                "platform": "draft",
                "version": draft.version,
                "status": "written",
                "created_at": draft.created_at,
            }
        )
    for variant in variants:
        source = source_map.get(variant.source_id)
        output.append(
            {
                "ref": f"variant:{variant.id}",
                "kind": "platform_variant",
                "id": variant.id,
                "source_id": variant.source_id,
                "title": variant.title or "未命名平台版本",
                "excerpt": _clean_excerpt(variant.body_markdown),
                "author": (source.author_name or source.author_handle) if source else "",
                "platform": variant.platform,
                "version": variant.version,
                "status": variant.status,
                "created_at": variant.created_at,
            }
        )
    return output


def resolve_input_materials(
    db: Session,
    refs: list[str],
    *,
    preferred_source_id: str = "",
    max_materials: int = 32,
) -> ResolvedInputMaterials:
    ordered_refs = list(
        dict.fromkeys(normalize_material_ref(value) for value in refs if str(value or "").strip())
    )
    if preferred_source_id:
        preferred_ref = f"source:{preferred_source_id}"
        if preferred_ref not in ordered_refs:
            ordered_refs.insert(0, preferred_ref)
    if not ordered_refs:
        raise InputMaterialError("请至少选择一个库内材料或粘贴一段内容")
    if len(ordered_refs) > max_materials:
        raise InputMaterialError(f"一次最多选择 {max_materials} 个输入材料")

    materials: list[dict[str, Any]] = []
    evidence_source_ids: list[str] = []
    for ref in ordered_refs:
        kind, item_id = ref.split(":", 1)
        if kind == "source":
            source = db.get(SourceItem, item_id)
            if source is None:
                raise InputMaterialError(f"来源不存在：{item_id}")
            evidence_source_ids.append(source.id)
            materials.append(
                {
                    "ref": ref,
                    "kind": "source",
                    "id": source.id,
                    "source_id": source.id,
                    "title": _source_title(source),
                    "body_sha256": hashlib.sha256(source.text_original.encode()).hexdigest(),
                }
            )
            continue
        if kind == "draft":
            draft = db.get(DraftRevision, item_id)
            if draft is None:
                raise InputMaterialError(f"写作版本不存在：{item_id}")
            evidence_source_ids.append(draft.source_id)
            materials.append(
                {
                    "ref": ref,
                    "kind": "draft_revision",
                    "id": draft.id,
                    "source_id": draft.source_id,
                    "version": draft.version,
                    "title": draft.title,
                    "body": draft.body,
                    "body_sha256": hashlib.sha256(draft.body.encode()).hexdigest(),
                    "tags": draft.tags,
                    "provenance": _object(draft.provenance_json),
                    "created_at": draft.created_at.isoformat() if isinstance(draft.created_at, datetime) else "",
                }
            )
            continue
        variant = db.get(PlatformVariant, item_id)
        if variant is None:
            raise InputMaterialError(f"平台版本不存在：{item_id}")
        metadata = _object(variant.metadata_json)
        variant_evidence = metadata.get("evidence_source_ids")
        variant_evidence_ids = (
            list(dict.fromkeys(str(value) for value in variant_evidence if value))
            if isinstance(variant_evidence, list)
            else []
        )
        if variant_evidence_ids:
            evidence_source_ids.extend(variant_evidence_ids)
        else:
            evidence_source_ids.append(variant.source_id)
        materials.append(
            {
                "ref": ref,
                "kind": "platform_variant",
                "id": variant.id,
                "source_id": variant.source_id,
                "platform": variant.platform,
                "version": variant.version,
                "title": variant.title,
                "body": variant.body_markdown,
                "body_sha256": hashlib.sha256(variant.body_markdown.encode()).hexdigest(),
                "tags": variant.tags,
                "status": variant.status,
                "evidence_source_ids": variant_evidence_ids,
                "created_at": variant.created_at.isoformat() if isinstance(variant.created_at, datetime) else "",
            }
        )

    ordered_source_ids = list(dict.fromkeys(value for value in evidence_source_ids if value))
    if preferred_source_id:
        ordered_source_ids = [preferred_source_id, *(value for value in ordered_source_ids if value != preferred_source_id)]
    source_map = {
        item.id: item
        for item in db.scalars(select(SourceItem).where(SourceItem.id.in_(ordered_source_ids))).all()
    }
    missing = [source_id for source_id in ordered_source_ids if source_id not in source_map]
    if missing:
        raise InputMaterialError(f"输入版本关联的来源不存在：{', '.join(missing)}")
    sources = [source_map[source_id] for source_id in ordered_source_ids]
    if not sources:
        raise InputMaterialError("输入材料没有可追溯的来源")
    return ResolvedInputMaterials(primary_source=sources[0], sources=sources, materials=materials)


def compact_material_provenance(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "body"}
        for item in materials
    ]
