from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import (
    CorpusBatch,
    CorpusPool,
    CorpusPoolSource,
    DraftRevision,
    RightsStatus,
    SourceItem,
    SourceRelation,
    SourceState,
    WorkspaceState,
    new_id,
    utcnow,
)


class CorpusPoolError(RuntimeError):
    pass


_STOP_TERMS = {
    "一个",
    "一些",
    "一种",
    "这个",
    "那个",
    "这些",
    "那些",
    "自己",
    "我们",
    "你们",
    "他们",
    "她们",
    "其实",
    "就是",
    "已经",
    "没有",
    "可以",
    "需要",
    "觉得",
    "因为",
    "所以",
    "但是",
    "如果",
    "时候",
    "很多",
    "更多",
    "可能",
    "现在",
    "今天",
    "每天",
    "什么",
    "怎么",
    "如何",
    "为什么",
    "来源",
    "内容",
    "文章",
    "视频",
    "作者",
    "原文",
    "相关",
    "问题",
    "事情",
    "工作",
    "生活",
}
_STOP_CHARS = re.compile(r"[的了是在与和及或把被对从为就也都而但并很更最让给中上下里后前时着过]")


class CorpusPoolService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_pools(self, db: Session, *, state: str = "active") -> list[dict[str, Any]]:
        query = select(CorpusPool).order_by(CorpusPool.updated_at.desc())
        if state != "all":
            if state not in {"active", "archived"}:
                raise CorpusPoolError("未知的语料池状态")
            query = query.where(CorpusPool.state == state)
        return [self._pool_dict(pool) for pool in db.scalars(query).all()]

    def get_pool(self, db: Session, pool_id: str) -> CorpusPool:
        pool = db.get(CorpusPool, pool_id)
        if pool is None:
            raise CorpusPoolError("语料池不存在")
        return pool

    def detail(self, db: Session, pool_id: str) -> dict[str, Any]:
        pool = self.get_pool(db, pool_id)
        rows = db.execute(
            select(CorpusPoolSource, SourceItem)
            .join(SourceItem, SourceItem.id == CorpusPoolSource.source_id)
            .where(CorpusPoolSource.pool_id == pool.id)
            .order_by(CorpusPoolSource.added_at.desc())
        ).all()
        batches = list(
            db.scalars(
                select(CorpusBatch)
                .where(CorpusBatch.pool_id == pool.id)
                .order_by(CorpusBatch.sequence.desc())
                .limit(20)
            ).all()
        )
        return {
            **self._pool_dict(pool),
            "members": [
                self._member_dict(member, source) for member, source in rows
            ],
            "batches": [self._batch_dict(db, batch) for batch in batches],
        }

    def create_pool(
        self,
        db: Session,
        *,
        source_ids: list[str],
        name: str = "",
        description: str = "",
        batch_size: int = 6,
    ) -> CorpusPool:
        unique_ids = self._unique_ids(source_ids)
        if not unique_ids:
            raise CorpusPoolError("至少选择一条来源")
        sources = self._load_sources(db, unique_ids)
        pool = CorpusPool(
            id=new_id("pool"),
            name=name.strip()[:160] or "正在整理",
            name_locked=bool(name.strip()),
            description=description.strip()[:4000],
            batch_size=max(1, min(int(batch_size), 12)),
        )
        db.add(pool)
        db.flush()
        for source in sources:
            db.add(CorpusPoolSource(pool_id=pool.id, source_id=source.id))
        db.flush()
        self.compile_pool(db, pool)
        return pool

    def update_pool(
        self,
        db: Session,
        pool: CorpusPool,
        *,
        name: str | None = None,
        description: str | None = None,
        batch_size: int | None = None,
        state: str | None = None,
        unlock_name: bool = False,
    ) -> CorpusPool:
        if name is not None:
            cleaned = name.strip()[:160]
            if cleaned:
                pool.name = cleaned
                pool.name_locked = True
            elif unlock_name:
                pool.name_locked = False
        if description is not None:
            pool.description = description.strip()[:4000]
        if batch_size is not None:
            pool.batch_size = max(1, min(int(batch_size), 12))
        if state is not None:
            if state not in {"active", "archived"}:
                raise CorpusPoolError("未知的语料池状态")
            pool.state = state
        pool.updated_at = utcnow()
        if unlock_name:
            pool.name_locked = False
            self.compile_pool(db, pool)
        db.flush()
        return pool

    def add_sources(
        self,
        db: Session,
        pool: CorpusPool,
        source_ids: list[str],
    ) -> int:
        unique_ids = self._unique_ids(source_ids)
        if not unique_ids:
            return 0
        sources = self._load_sources(db, unique_ids)
        existing = set(
            db.scalars(
                select(CorpusPoolSource.source_id).where(
                    CorpusPoolSource.pool_id == pool.id,
                    CorpusPoolSource.source_id.in_(unique_ids),
                )
            ).all()
        )
        added = 0
        for source in sources:
            if source.id in existing:
                continue
            db.add(CorpusPoolSource(pool_id=pool.id, source_id=source.id))
            added += 1
        db.flush()
        if added:
            self.compile_pool(db, pool)
        return added

    def remove_source(self, db: Session, pool: CorpusPool, source_id: str) -> None:
        member = db.scalar(
            select(CorpusPoolSource).where(
                CorpusPoolSource.pool_id == pool.id,
                CorpusPoolSource.source_id == source_id,
            )
        )
        if member is None:
            raise CorpusPoolError("该来源不在语料池中")
        db.delete(member)
        db.flush()
        self.compile_pool(db, pool)

    def delete_pool(self, db: Session, pool: CorpusPool) -> None:
        anchor_ids = list(
            db.scalars(
                select(CorpusBatch.anchor_source_id).where(
                    CorpusBatch.pool_id == pool.id,
                    CorpusBatch.anchor_source_id.is_not(None),
                )
            ).all()
        )
        db.delete(pool)
        db.flush()
        for anchor_id in anchor_ids:
            anchor = db.get(SourceItem, anchor_id)
            if anchor is not None:
                db.delete(anchor)
        db.flush()

    def compile_pool(self, db: Session, pool: CorpusPool) -> CorpusPool:
        rows = db.execute(
            select(CorpusPoolSource, SourceItem)
            .join(SourceItem, SourceItem.id == CorpusPoolSource.source_id)
            .where(CorpusPoolSource.pool_id == pool.id)
            .order_by(CorpusPoolSource.added_at.asc())
        ).all()
        keyword_counter: Counter[str] = Counter()
        memory_rows: list[dict[str, str]] = []
        platform_counter: Counter[str] = Counter()
        total_chars = 0

        for member, source in rows:
            normalized, title, summary, keywords = self._convert_source(source)
            member.normalized_text = normalized
            member.summary = summary
            member.keywords_json = json.dumps(keywords, ensure_ascii=False)
            total_chars += len(normalized)
            platform_counter[source.platform or source.provider] += 1
            for rank, keyword in enumerate(keywords):
                keyword_counter[keyword] += max(1, 12 - rank)
            memory_rows.append(
                {
                    "title": title,
                    "summary": summary,
                    "platform": source.platform or source.provider,
                    "author": source.author_name or source.author_handle,
                }
            )

        keywords = self._dedupe_keywords(
            [item for item, _ in keyword_counter.most_common(24)]
        )[:12]
        if not pool.name_locked:
            pool.name = self._auto_name(keywords, memory_rows)
        pool.topic_keywords_json = json.dumps(keywords, ensure_ascii=False)
        pool.source_count = len(rows)
        pool.total_chars = total_chars
        pool.revision += 1
        pool.last_compiled_at = utcnow()
        pool.updated_at = pool.last_compiled_at
        pool.profile_text = self._profile_text(
            pool=pool,
            keywords=keywords,
            platform_counter=platform_counter,
            memory_rows=memory_rows,
        )
        db.flush()
        return pool

    def preview_batch(
        self,
        db: Session,
        pool: CorpusPool,
        *,
        batch_size: int | None = None,
        focus: str = "",
    ) -> dict[str, Any]:
        sequence = self._next_sequence(db, pool.id)
        rows = self._select_rows(
            db,
            pool,
            batch_size=batch_size,
            focus=focus,
            sequence=sequence,
        )
        return {
            "id": "",
            "pool_id": pool.id,
            "sequence": sequence,
            "focus": focus.strip(),
            "source_ids": [source.id for _, source in rows],
            "sources": [self._source_dict(source) for _, source in rows],
            "source_fingerprint": self._fingerprint(
                [source.id for _, source in rows]
            ),
            "profile_revision": pool.revision,
            "anchor_source_id": None,
            "draft_id": "",
            "created_at": None,
            "draft": None,
        }

    def create_generation_batch(
        self,
        db: Session,
        pool: CorpusPool,
        *,
        batch_size: int | None = None,
        focus: str = "",
    ) -> tuple[CorpusBatch, SourceItem, list[SourceItem]]:
        if pool.revision <= 0:
            self.compile_pool(db, pool)
        sequence = self._next_sequence(db, pool.id)
        rows = self._select_rows(
            db,
            pool,
            batch_size=batch_size,
            focus=focus,
            sequence=sequence,
        )
        now = utcnow()
        source_ids = [source.id for _, source in rows]
        for member, _ in rows:
            member.used_count += 1
            member.last_used_at = now

        batch = CorpusBatch(
            id=new_id("batch"),
            pool_id=pool.id,
            sequence=sequence,
            focus=focus.strip()[:500],
            source_ids_json=json.dumps(source_ids, ensure_ascii=False),
            source_fingerprint=self._fingerprint(source_ids),
            profile_revision=pool.revision,
        )
        db.add(batch)
        db.flush()

        batch_sources = [source for _, source in rows]
        anchor = SourceItem(
            provider="corpus_pool",
            platform="local",
            external_id=batch.id,
            canonical_url=f"x2red://corpus-pools/{pool.id}/batches/{batch.id}",
            author_name=f"语料池 · {pool.name}",
            text_original=self._batch_anchor_text(pool, batch, rows),
            language="zh-CN",
            state=SourceState.private.value,
            workspace_state=WorkspaceState.active.value,
            content_kind="corpus_batch",
            structured_content_json=json.dumps(
                {
                    "document_type": "corpus_batch",
                    "pool_id": pool.id,
                    "pool_name": pool.name,
                    "pool_revision": pool.revision,
                    "batch_id": batch.id,
                    "batch_sequence": sequence,
                    "batch_source_ids": source_ids,
                    "focus": focus.strip(),
                    "topic_keywords": self._json_list(pool.topic_keywords_json),
                },
                ensure_ascii=False,
            ),
            editor_note=(
                "这是语料池的全局语义记忆，只用于发现跨来源关系、共识、差异和选题角度。"
                "具体事实、数字、引语和因果必须来自本批次关联的详细来源，不能只引用本锚点。"
            ),
            rights_status=RightsStatus.needs_review.value,
            rights_note="批次继承多个来源的权利状态，发布前必须逐条复核。",
        )
        db.add(anchor)
        db.flush()
        batch.anchor_source_id = anchor.id
        for position, source in enumerate(batch_sources, start=1):
            db.add(
                SourceRelation(
                    from_source_id=anchor.id,
                    to_source_id=source.id,
                    relation_type="corpus_batch",
                    position=position,
                )
            )
        pool.updated_at = now
        db.flush()
        return batch, anchor, batch_sources

    def finalize_batch(
        self,
        db: Session,
        *,
        pool: CorpusPool,
        batch: CorpusBatch,
        draft: DraftRevision,
    ) -> DraftRevision:
        provenance = self._json_object(draft.provenance_json)
        source_ids = self._json_list(batch.source_ids_json)
        provenance["corpus_pool"] = {
            "pool_id": pool.id,
            "pool_name": pool.name,
            "pool_revision": batch.profile_revision,
            "batch_id": batch.id,
            "batch_sequence": batch.sequence,
            "batch_source_ids": source_ids,
            "batch_size": len(source_ids),
            "focus": batch.focus,
            "memory_mode": "compiled-global-memory-plus-detailed-batch",
        }
        draft.provenance_json = json.dumps(provenance, ensure_ascii=False)
        batch.draft_id = draft.id
        db.flush()
        return draft

    def list_batches(self, db: Session, pool: CorpusPool) -> list[dict[str, Any]]:
        batches = db.scalars(
            select(CorpusBatch)
            .where(CorpusBatch.pool_id == pool.id)
            .order_by(CorpusBatch.sequence.desc())
            .limit(100)
        ).all()
        return [self._batch_dict(db, batch) for batch in batches]

    def _select_rows(
        self,
        db: Session,
        pool: CorpusPool,
        *,
        batch_size: int | None,
        focus: str,
        sequence: int,
    ) -> list[tuple[CorpusPoolSource, SourceItem]]:
        rows = list(
            db.execute(
                select(CorpusPoolSource, SourceItem)
                .join(SourceItem, SourceItem.id == CorpusPoolSource.source_id)
                .where(CorpusPoolSource.pool_id == pool.id)
            ).all()
        )
        if not rows:
            raise CorpusPoolError("语料池还没有来源")
        size = min(max(1, int(batch_size or pool.batch_size)), 12, len(rows))
        focus_text = focus.strip().lower()
        focus_terms = set(self._rank_keywords([(focus_text, 8)], limit=12))
        selected: list[tuple[CorpusPoolSource, SourceItem]] = []
        platform_counts: Counter[str] = Counter()
        keyword_counts: Counter[str] = Counter()
        remaining = list(rows)

        while remaining and len(selected) < size:
            def row_key(row: tuple[CorpusPoolSource, SourceItem]) -> tuple[Any, ...]:
                member, source = row
                keywords = self._json_list(member.keywords_json)
                keyword_set = set(keywords)
                focus_match = bool(
                    not focus_text
                    or focus_text in member.normalized_text.lower()
                    or focus_terms.intersection(keyword_set)
                )
                overlap = sum(keyword_counts[item] for item in keywords[:8])
                platform = source.platform or source.provider
                last_used = (
                    member.last_used_at.timestamp()
                    if isinstance(member.last_used_at, datetime)
                    else 0.0
                )
                jitter = int(
                    hashlib.sha256(
                        f"{pool.id}:{sequence}:{source.id}".encode("utf-8")
                    ).hexdigest()[:10],
                    16,
                )
                return (
                    0 if focus_match else 1,
                    member.used_count,
                    platform_counts[platform],
                    overlap,
                    last_used,
                    jitter,
                )

            chosen = min(remaining, key=row_key)
            remaining.remove(chosen)
            selected.append(chosen)
            member, source = chosen
            platform_counts[source.platform or source.provider] += 1
            for keyword in self._json_list(member.keywords_json)[:8]:
                keyword_counts[keyword] += 1
        return selected

    def _batch_anchor_text(
        self,
        pool: CorpusPool,
        batch: CorpusBatch,
        rows: list[tuple[CorpusPoolSource, SourceItem]],
    ) -> str:
        lines = [
            pool.profile_text,
            "",
            "【本批次任务】",
            f"批次：第 {batch.sequence} 批",
            f"详细来源数：{len(rows)}",
            f"本批聚焦：{batch.focus or '由模型从全池记忆与本批来源中选择新的角度'}",
            "全池记忆只用于理解主题版图；可发布事实必须回到下面关联的本批详细来源。",
            "",
            "【本批次来源索引】",
        ]
        for index, (member, source) in enumerate(rows, start=1):
            title = self._source_title(source)
            lines.append(
                f"{index}. {title}｜{source.platform or source.provider}｜"
                f"{source.author_name or source.author_handle or '未知作者'}｜{member.summary}"
            )
        return "\n".join(lines)[:18000]

    def _profile_text(
        self,
        *,
        pool: CorpusPool,
        keywords: list[str],
        platform_counter: Counter[str],
        memory_rows: list[dict[str, str]],
    ) -> str:
        if not memory_rows:
            return (
                f"【全池语义记忆】\n主题：{pool.name}\n来源数：0\n"
                "当前为空，加入来源后会自动完成清洗、摘要、主题命名和批次规划。"
            )
        platform_text = "、".join(
            f"{name} {count} 条" for name, count in platform_counter.most_common()
        )
        lines = [
            "【全池语义记忆】",
            f"主题：{pool.name}",
            f"来源数：{len(memory_rows)}",
            f"语料字符：{pool.total_chars}",
            f"主题关键词：{'、'.join(keywords) or '待整理'}",
            f"平台分布：{platform_text or '未知'}",
        ]
        if pool.description:
            lines.append(f"工作区说明：{pool.description}")
        lines.extend(
            [
                "",
                "【使用规则】",
                "下面是全池每条来源的压缩记忆，让任意小批次都能看见其他内容的主题位置。",
                "它用于发现共识、矛盾、互补角度和选题空缺，不可替代本批详细来源的事实核对。",
                "",
                "【全池来源记忆】",
            ]
        )
        budget = 10500
        for index, row in enumerate(memory_rows, start=1):
            item = (
                f"{index}. [{row['platform']}] {row['title']}｜"
                f"{row['author'] or '未知作者'}｜{row['summary']}"
            )
            if sum(len(line) for line in lines) + len(item) > budget:
                remaining = len(memory_rows) - index + 1
                lines.append(f"……其余 {remaining} 条已完成语料化，但未展开到本次全局记忆文本。")
                break
            lines.append(item)
        return "\n".join(lines)

    def _convert_source(
        self,
        source: SourceItem,
    ) -> tuple[str, str, str, list[str]]:
        title = self._source_title(source)
        body = self._normalize_text(source.text_original)
        metadata = self._json_object(source.structured_content_json)
        discovery_keyword = self._metadata_value(metadata, "discovery_keyword")
        summary = self._summary(body or title)
        normalized_parts = [
            f"标题：{title}",
            f"平台：{source.platform or source.provider}",
            f"作者：{source.author_name or source.author_handle or '未知作者'}",
        ]
        if discovery_keyword:
            normalized_parts.append(f"发现关键词：{discovery_keyword}")
        if source.editor_note.strip():
            normalized_parts.append(f"编辑备注：{self._normalize_text(source.editor_note)[:1200]}")
        normalized_parts.append(f"正文：{body}")
        normalized = "\n".join(normalized_parts)[:80000]
        keywords = self._rank_keywords(
            [
                (title, 7),
                (discovery_keyword, 8),
                (source.editor_note, 3),
                (summary, 4),
                (body[:12000], 1),
            ],
            limit=16,
        )
        return normalized, title, summary, keywords

    def _source_title(self, source: SourceItem) -> str:
        metadata = self._json_object(source.structured_content_json)
        title = self._metadata_value(metadata, "title")
        if not title and isinstance(metadata.get("metadata"), dict):
            title = str(metadata["metadata"].get("title") or "")
        title = self._normalize_text(title)
        if title:
            return title[:120]
        body = self._normalize_text(source.text_original)
        first = re.split(r"[。！？!?\n]", body, maxsplit=1)[0].strip()
        return first[:80] or source.author_name or source.author_handle or "未命名来源"

    @staticmethod
    def _summary(text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return "（无可用正文）"
        sentences = [
            item.strip()
            for item in re.split(r"(?<=[。！？!?；;])\s*", normalized)
            if len(item.strip()) >= 6
        ]
        output: list[str] = []
        for sentence in sentences or [normalized]:
            if sentence not in output:
                output.append(sentence)
            if len("".join(output)) >= 260 or len(output) >= 3:
                break
        summary = " ".join(output)
        return summary[:360] + ("…" if len(summary) > 360 else "")

    def _rank_keywords(
        self,
        weighted_texts: list[tuple[str, int]],
        *,
        limit: int,
    ) -> list[str]:
        counter: Counter[str] = Counter()
        for raw, weight in weighted_texts:
            text = str(raw or "").lower()
            if not text:
                continue
            for token in re.findall(r"[a-z][a-z0-9.+#_-]{1,30}", text):
                if token not in _STOP_TERMS:
                    counter[token] += weight
            for segment in re.findall(r"[\u4e00-\u9fff]{2,40}", text):
                pieces = [item for item in _STOP_CHARS.split(segment) if item]
                for piece in pieces:
                    if 2 <= len(piece) <= 8 and piece not in _STOP_TERMS:
                        counter[piece] += weight * 2
                    elif len(piece) > 8:
                        for width in (4, 3, 2):
                            for index in range(0, len(piece) - width + 1):
                                token = piece[index : index + width]
                                if token in _STOP_TERMS:
                                    continue
                                counter[token] += weight
        ranked = [
            token
            for token, score in counter.most_common(80)
            if score >= 2 and not token.isdigit()
        ]
        return self._dedupe_keywords(ranked)[:limit]

    @staticmethod
    def _dedupe_keywords(values: list[str]) -> list[str]:
        output: list[str] = []
        for raw in values:
            value = raw.strip("_- ，。！？；：")
            if len(value) < 2 or value in _STOP_TERMS:
                continue
            if any(value == item or (value in item and len(value) <= 3) for item in output):
                continue
            output.append(value)
        return output

    @staticmethod
    def _auto_name(keywords: list[str], memory_rows: list[dict[str, str]]) -> str:
        terms = [item for item in keywords if item not in _STOP_TERMS][:3]
        if len(terms) >= 3:
            return f"{terms[0]}、{terms[1]}与{terms[2]}"[:160]
        if len(terms) == 2:
            return f"{terms[0]}与{terms[1]}"[:160]
        if terms:
            return f"{terms[0]}相关"[:160]
        if memory_rows:
            return memory_rows[0]["title"][:80]
        return "未命名语料池"

    def _load_sources(self, db: Session, source_ids: list[str]) -> list[SourceItem]:
        sources = list(
            db.scalars(select(SourceItem).where(SourceItem.id.in_(source_ids))).all()
        )
        found = {source.id for source in sources}
        missing = [source_id for source_id in source_ids if source_id not in found]
        if missing:
            raise CorpusPoolError(f"有 {len(missing)} 条来源不存在")
        visible = [source for source in sources if source.provider != "corpus_pool"]
        if len(visible) != len(sources):
            raise CorpusPoolError("批次锚点不能再次加入语料池")
        order = {source_id: index for index, source_id in enumerate(source_ids)}
        return sorted(visible, key=lambda source: order[source.id])

    @staticmethod
    def _unique_ids(source_ids: list[str]) -> list[str]:
        output: list[str] = []
        for source_id in source_ids:
            cleaned = str(source_id or "").strip()
            if cleaned and cleaned not in output:
                output.append(cleaned)
        return output[:500]

    @staticmethod
    def _next_sequence(db: Session, pool_id: str) -> int:
        current = db.scalar(
            select(func.max(CorpusBatch.sequence)).where(CorpusBatch.pool_id == pool_id)
        )
        return int(current or 0) + 1

    @staticmethod
    def _fingerprint(source_ids: list[str]) -> str:
        payload = "|".join(sorted(source_ids)).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _pool_dict(self, pool: CorpusPool) -> dict[str, Any]:
        return {
            "id": pool.id,
            "name": pool.name,
            "name_locked": pool.name_locked,
            "description": pool.description,
            "state": pool.state,
            "batch_size": pool.batch_size,
            "topic_keywords": self._json_list(pool.topic_keywords_json),
            "profile_text": pool.profile_text,
            "source_count": pool.source_count,
            "total_chars": pool.total_chars,
            "revision": pool.revision,
            "created_at": pool.created_at,
            "updated_at": pool.updated_at,
            "last_compiled_at": pool.last_compiled_at,
        }

    def _member_dict(
        self,
        member: CorpusPoolSource,
        source: SourceItem,
    ) -> dict[str, Any]:
        return {
            "id": member.id,
            "pool_id": member.pool_id,
            "source_id": member.source_id,
            "summary": member.summary,
            "keywords": self._json_list(member.keywords_json),
            "used_count": member.used_count,
            "last_used_at": member.last_used_at,
            "added_at": member.added_at,
            "source": self._source_dict(source),
        }

    def _batch_dict(self, db: Session, batch: CorpusBatch) -> dict[str, Any]:
        source_ids = self._json_list(batch.source_ids_json)
        sources = list(
            db.scalars(select(SourceItem).where(SourceItem.id.in_(source_ids))).all()
        )
        source_map = {source.id: source for source in sources}
        draft = db.get(DraftRevision, batch.draft_id) if batch.draft_id else None
        return {
            "id": batch.id,
            "pool_id": batch.pool_id,
            "sequence": batch.sequence,
            "focus": batch.focus,
            "source_ids": source_ids,
            "sources": [
                self._source_dict(source_map[source_id])
                for source_id in source_ids
                if source_id in source_map
            ],
            "source_fingerprint": batch.source_fingerprint,
            "profile_revision": batch.profile_revision,
            "anchor_source_id": batch.anchor_source_id,
            "draft_id": batch.draft_id,
            "created_at": batch.created_at,
            "draft": self._draft_dict(draft) if draft is not None else None,
        }

    @staticmethod
    def _source_dict(source: SourceItem) -> dict[str, Any]:
        return {
            "id": source.id,
            "provider": source.provider,
            "platform": source.platform,
            "external_id": source.external_id,
            "canonical_url": source.canonical_url,
            "author_handle": source.author_handle,
            "author_name": source.author_name,
            "author_avatar_url": source.author_avatar_url,
            "text_original": source.text_original,
            "content_kind": source.content_kind,
            "workspace_state": source.workspace_state,
            "created_at": source.created_at,
            "captured_at": source.captured_at,
            "archived_at": source.archived_at,
            "last_published_at": source.last_published_at,
            "published_count": source.published_count,
            "state": source.state,
            "rights_status": source.rights_status,
            "rights_note": source.rights_note,
        }

    @staticmethod
    def _draft_dict(draft: DraftRevision) -> dict[str, Any]:
        return {
            "id": draft.id,
            "source_id": draft.source_id,
            "version": draft.version,
            "style": draft.style,
            "title": draft.title,
            "body": draft.body,
            "tags": draft.tags,
            "claims_json": draft.claims_json,
            "provenance_json": draft.provenance_json,
            "created_by": draft.created_by,
            "created_at": draft.created_at,
        }

    @staticmethod
    def _normalize_text(value: object) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        text = re.sub(r"https?://\S+", " ", text)
        lines: list[str] = []
        for raw in text.replace("\r\n", "\n").split("\n"):
            line = re.sub(r"\s+", " ", raw).strip()
            line = re.sub(r"^来源\s*[·:：-]?\s*", "", line)
            if line and line not in lines:
                lines.append(line)
        return "\n".join(lines).strip()

    @staticmethod
    def _metadata_value(metadata: dict[str, Any], key: str) -> str:
        value = metadata.get(key)
        return str(value or "").strip() if not isinstance(value, (dict, list)) else ""

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _json_list(value: str) -> list[str]:
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if str(item).strip()]
