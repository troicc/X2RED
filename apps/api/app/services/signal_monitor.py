from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.domain.discovery import DiscoveryCandidate
from app.domain.studio import (
    AnalysisLevel,
    AnalysisStatus,
    ContentAnalysis,
    MetricSnapshot,
    MonitorTarget,
    ScoreRecord,
    WritingProject,
    utcnow,
)
from app.services.scoring import SCORE_VERSION, baseline_median, calculate_score, core_engagement


class SignalMonitorMixin:
    def create_target(
        self,
        db: Session,
        *,
        name: str,
        kind: str,
        target: str,
        interval_minutes: int,
        enabled: bool,
        config: dict[str, Any],
    ) -> MonitorTarget:
        normalized = target.strip().lstrip("@") if kind == "profile" else target.strip()
        existing = db.scalar(
            select(MonitorTarget).where(
                MonitorTarget.platform == "x",
                MonitorTarget.kind == kind,
                MonitorTarget.target == normalized,
            )
        )
        if existing is not None:
            raise ValueError("这个监控目标已经存在")
        item = MonitorTarget(
            name=name.strip() or normalized,
            kind=kind,
            target=normalized,
            interval_minutes=interval_minutes,
            enabled=enabled,
            config_json=json.dumps(config, ensure_ascii=False),
            next_run_at=utcnow() if enabled else None,
        )
        db.add(item)
        db.flush()
        return item

    def update_target(
        self,
        target: MonitorTarget,
        *,
        name: str,
        interval_minutes: int,
        enabled: bool,
        config: dict[str, Any],
    ) -> MonitorTarget:
        target.name = name.strip() or target.target
        target.interval_minutes = interval_minutes
        target.enabled = enabled
        target.config_json = json.dumps(config, ensure_ascii=False)
        target.next_run_at = utcnow() if enabled and target.next_run_at is None else target.next_run_at
        if not enabled:
            target.next_run_at = None
        return target

    def due_target_ids(self, db: Session, *, limit: int = 20) -> list[str]:
        return list(
            db.scalars(
                select(MonitorTarget.id)
                .where(
                    MonitorTarget.enabled.is_(True),
                    MonitorTarget.next_run_at.is_not(None),
                    MonitorTarget.next_run_at <= utcnow(),
                )
                .order_by(MonitorTarget.next_run_at, MonitorTarget.created_at)
                .limit(limit)
            ).all()
        )

    async def scan_target(self, db: Session, target_id: str) -> dict[str, Any]:
        target = db.get(MonitorTarget, target_id)
        if target is None:
            raise ValueError("监控目标不存在")
        config = self._json(target.config_json, {})
        cursor = self._json(target.cursor_json, {})
        count = min(max(self._int(config.get("count")) or 30, 5), 100)
        followers = 0
        try:
            if target.kind == "profile":
                followers = self._profile_followers(
                    await self.provider.get_profile(target.target, about_account=True)
                )
                result = await self.discovery.timeline(
                    db,
                    handle=target.target,
                    count=count,
                    cursor=str(cursor.get("bottom") or "") or None,
                    since=self._int(config.get("since")) or None,
                    media_only=bool(config.get("media_only", False)),
                )
            elif target.kind == "search":
                result = await self.discovery.search(
                    db,
                    query=target.target,
                    feed=str(config.get("feed") or "latest"),
                    count=count,
                    cursor=str(cursor.get("bottom") or "") or None,
                    language=str(config.get("language") or "") or None,
                )
            elif target.kind == "quotes":
                result = await self.discovery.quotes(
                    db,
                    post_id=target.target,
                    count=count,
                    cursor=str(cursor.get("bottom") or "") or None,
                )
            elif target.kind == "trends":
                result = await self.discovery.trends(db, count=count)
            else:
                raise ValueError(f"不支持的监控类型：{target.kind}")

            target.cursor_json = json.dumps(result.cursor or {}, ensure_ascii=False)
            observations = [
                (
                    candidate,
                    self._snapshot_candidate(
                        db,
                        candidate=candidate,
                        target=target,
                        followers=followers,
                    ),
                )
                for candidate in result.candidates
                if candidate.kind == "status"
            ]
            scored = []
            for candidate, snapshot in observations:
                score = self._score_candidate(db, candidate, target, snapshot)
                scored.append(
                    {
                        "candidate_id": candidate.id,
                        "grade": score.grade,
                        "r_value": score.r_value,
                        "m_value": score.m_value,
                    }
                )
            target.last_run_at = utcnow()
            target.next_run_at = target.last_run_at + timedelta(minutes=target.interval_minutes)
            target.last_error = ""
            db.flush()
            return {
                "target_id": target.id,
                "candidate_count": len(result.candidates),
                "scored": scored,
                "cursor": result.cursor,
            }
        except Exception as exc:
            target.last_run_at = utcnow()
            target.next_run_at = target.last_run_at + timedelta(
                minutes=max(min(target.interval_minutes // 4, 60), 15)
            )
            target.last_error = str(exc)[:2000]
            db.flush()
            raise

    def _snapshot_candidate(
        self,
        db: Session,
        *,
        candidate: DiscoveryCandidate,
        target: MonitorTarget,
        followers: int,
    ) -> MetricSnapshot:
        metadata = self._json(candidate.metadata_json, {})
        created_raw = metadata.get("created_at") or metadata.get("created_timestamp")
        created_at: datetime | None = None
        if isinstance(created_raw, (int, float)):
            created_at = datetime.fromtimestamp(float(created_raw), tz=UTC)
        elif isinstance(created_raw, str) and created_raw:
            try:
                created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            except ValueError:
                created_at = None
        age_hours = 0.0
        if created_at is not None:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            age_hours = max((datetime.now(UTC) - created_at).total_seconds() / 3600.0, 0.0)

        metrics = {
            name: self._int(metadata.get(name))
            for name in ("likes", "reposts", "quotes", "replies", "views", "bookmarks")
        }
        weights = self._json(target.config_json, {}).get("weights")
        engagement = core_engagement(metrics, weights if isinstance(weights, dict) else None)
        snapshot = MetricSnapshot(
            candidate_id=candidate.id,
            target_id=target.id,
            author_handle=candidate.author_handle,
            followers=followers,
            core_engagement=engagement,
            content_age_hours=age_hours,
            raw_json=json.dumps(metadata, ensure_ascii=False),
            **metrics,
        )
        db.add(snapshot)
        db.flush()
        return snapshot

    def _baseline_samples(
        self,
        db: Session,
        *,
        candidate: DiscoveryCandidate,
        target_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            select(MetricSnapshot, DiscoveryCandidate.external_id)
            .join(DiscoveryCandidate, MetricSnapshot.candidate_id == DiscoveryCandidate.id)
            .where(
                MetricSnapshot.target_id == target_id,
                MetricSnapshot.author_handle == candidate.author_handle,
                MetricSnapshot.candidate_id != candidate.id,
            )
            .order_by(desc(MetricSnapshot.observed_at))
            .limit(limit * 6)
        ).all()
        seen: set[str] = set()
        samples: list[dict[str, Any]] = []
        for snapshot, external_id in rows:
            key = str(external_id or snapshot.candidate_id)
            if key in seen:
                continue
            seen.add(key)
            samples.append(
                {
                    "candidate_id": snapshot.candidate_id,
                    "external_id": external_id,
                    "core_engagement": snapshot.core_engagement,
                    "observed_at": snapshot.observed_at.isoformat(),
                }
            )
            if len(samples) >= limit:
                break
        return samples

    def _score_candidate(
        self,
        db: Session,
        candidate: DiscoveryCandidate,
        target: MonitorTarget,
        snapshot: MetricSnapshot,
    ) -> ScoreRecord:
        existing = db.scalar(
            select(ScoreRecord)
            .where(
                ScoreRecord.candidate_id == candidate.id,
                ScoreRecord.score_version == SCORE_VERSION,
            )
            .order_by(ScoreRecord.first_scored_at)
            .limit(1)
        )
        previous = db.scalar(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.candidate_id == candidate.id,
                MetricSnapshot.id != snapshot.id,
            )
            .order_by(desc(MetricSnapshot.observed_at))
            .limit(1)
        )
        if existing is None:
            samples = self._baseline_samples(db, candidate=candidate, target_id=target.id)
            baseline = baseline_median(item["core_engagement"] for item in samples)
            frozen_followers = snapshot.followers
        else:
            samples = self._json(existing.baseline_sample_json, [])
            baseline = existing.baseline_value
            frozen_followers = existing.followers_snapshot
        result = calculate_score(
            current_engagement=snapshot.core_engagement,
            baseline_value=baseline,
            followers=frozen_followers or snapshot.followers,
            views=snapshot.views,
            age_hours=snapshot.content_age_hours,
            previous_engagement=previous.core_engagement if previous is not None else None,
            previous_age_hours=previous.content_age_hours if previous is not None else None,
        )
        minimum_samples = max(
            self._int(self._json(target.config_json, {}).get("minimum_baseline_samples")) or 5,
            3,
        )
        warming_up = existing is None and len(samples) < minimum_samples
        record = existing or ScoreRecord(
            candidate_id=candidate.id,
            target_id=target.id,
            score_version=SCORE_VERSION,
            baseline_value=result.baseline_value,
            followers_snapshot=frozen_followers,
            baseline_sample_json=json.dumps(samples, ensure_ascii=False),
        )
        record.grade = "warming_up" if warming_up else result.grade
        record.label = "基线积累中" if warming_up else result.label
        record.r_value = result.r_value
        record.m_value = result.m_value
        record.v_value = result.v_value
        record.velocity = result.velocity
        record.thresholds_json = json.dumps(result.thresholds, ensure_ascii=False)
        record.evidence_json = json.dumps(
            {
                "snapshot_id": snapshot.id,
                "current_engagement": snapshot.core_engagement,
                "observed_at": snapshot.observed_at.isoformat(),
                "baseline_frozen": True,
            },
            ensure_ascii=False,
        )
        record.last_refreshed_at = utcnow()
        if existing is None:
            db.add(record)
        db.flush()
        return record

    def latest_score(self, db: Session, candidate_id: str) -> ScoreRecord | None:
        return db.scalar(
            select(ScoreRecord)
            .where(ScoreRecord.candidate_id == candidate_id)
            .order_by(desc(ScoreRecord.last_refreshed_at))
            .limit(1)
        )

    def feed(self, db: Session, *, grade: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        candidates = list(
            db.scalars(
                select(DiscoveryCandidate)
                .where(DiscoveryCandidate.kind == "status")
                .order_by(desc(DiscoveryCandidate.updated_at))
                .limit(min(max(limit, 1), 200))
            ).all()
        )
        output = []
        for candidate in candidates:
            score = self.latest_score(db, candidate.id)
            if grade and (score is None or score.grade != grade):
                continue
            l1 = db.scalar(
                select(ContentAnalysis)
                .where(
                    ContentAnalysis.candidate_id == candidate.id,
                    ContentAnalysis.level == AnalysisLevel.l1.value,
                    ContentAnalysis.status == AnalysisStatus.succeeded.value,
                )
                .order_by(desc(ContentAnalysis.updated_at))
                .limit(1)
            )
            output.append(
                {
                    "candidate": candidate,
                    "metadata": self._json(candidate.metadata_json, {}),
                    "score": score,
                    "l1_analysis": self._json(l1.result_json, {}) if l1 else None,
                }
            )
        output.sort(
            key=lambda item: (
                {"T3": 5, "T2": 4, "T1": 3, "low_quality": 2, "ordinary": 1}.get(
                    item["score"].grade if item["score"] else "", 0
                ),
                item["score"].velocity if item["score"] else 0,
            ),
            reverse=True,
        )
        return output

    def dashboard(self, db: Session) -> dict[str, Any]:
        now = utcnow()
        grade_rows = db.execute(
            select(ScoreRecord.grade, func.count(ScoreRecord.id)).group_by(ScoreRecord.grade)
        ).all()
        return {
            "active_targets": db.scalar(
                select(func.count(MonitorTarget.id)).where(MonitorTarget.enabled.is_(True))
            )
            or 0,
            "due_targets": db.scalar(
                select(func.count(MonitorTarget.id)).where(
                    MonitorTarget.enabled.is_(True),
                    MonitorTarget.next_run_at.is_not(None),
                    MonitorTarget.next_run_at <= now,
                )
            )
            or 0,
            "candidates": db.scalar(select(func.count(DiscoveryCandidate.id))) or 0,
            "grade_counts": {grade: count for grade, count in grade_rows},
            "pending_l1": db.scalar(
                select(func.count(ContentAnalysis.id)).where(
                    ContentAnalysis.level == "l1",
                    ContentAnalysis.status.in_(["pending", "running"]),
                )
            )
            or 0,
            "pending_l2": db.scalar(
                select(func.count(ContentAnalysis.id)).where(
                    ContentAnalysis.level == "l2",
                    ContentAnalysis.status.in_(["pending", "running"]),
                )
            )
            or 0,
            "writing_projects": db.scalar(select(func.count(WritingProject.id))) or 0,
        }
