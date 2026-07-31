from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from typing import Any, Iterable

SCORE_VERSION = "x-v1"


@dataclass(frozen=True)
class ScoreThresholds:
    tier: str
    m_base: float
    t1_r: float = 2.0
    t2_r: float = 4.0
    t3_r: float = 8.0
    t1_m_multiple: float = 1.0
    t2_m_multiple: float = 1.5
    t3_m_multiple: float = 3.0


@dataclass(frozen=True)
class ScoreResult:
    grade: str
    label: str
    r_value: float
    m_value: float
    v_value: float
    velocity: float
    baseline_value: float
    thresholds: dict[str, Any]


DEFAULT_WEIGHTS = {
    "likes": 1.0,
    "reposts": 2.0,
    "quotes": 2.0,
    "replies": 0.5,
    "bookmarks": 1.5,
}


def core_engagement(metrics: dict[str, Any], weights: dict[str, float] | None = None) -> float:
    active = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = 0.0
    for name, weight in active.items():
        try:
            total += max(float(metrics.get(name) or 0), 0.0) * float(weight)
        except (TypeError, ValueError):
            continue
    return total


def baseline_median(values: Iterable[float]) -> float:
    clean = [max(float(value), 0.0) for value in values]
    if not clean:
        return 1.0
    return max(float(statistics.median(clean)), 1.0)


def thresholds_for_followers(followers: int) -> ScoreThresholds:
    if followers < 10_000:
        return ScoreThresholds("C", 0.10)
    if followers < 100_000:
        return ScoreThresholds("B", 0.05)
    if followers < 1_000_000:
        return ScoreThresholds("A", 0.025)
    return ScoreThresholds("S", 0.012)


def grade_work(r_value: float, m_value: float, thresholds: ScoreThresholds) -> tuple[str, str]:
    if r_value >= thresholds.t3_r and m_value >= thresholds.t3_m_multiple * thresholds.m_base:
        return "T3", "现象级"
    if r_value >= thresholds.t2_r and m_value >= thresholds.t2_m_multiple * thresholds.m_base:
        return "T2", "爆款"
    if r_value >= thresholds.t1_r and m_value >= thresholds.t1_m_multiple * thresholds.m_base:
        return "T1", "小爆"
    if r_value >= thresholds.t1_r:
        return "low_quality", "相对高但未破圈"
    return "ordinary", "普通"


def calculate_score(
    *,
    current_engagement: float,
    baseline_value: float,
    followers: int,
    views: int = 0,
    age_hours: float = 0.0,
    previous_engagement: float | None = None,
    previous_age_hours: float | None = None,
    thresholds: ScoreThresholds | None = None,
) -> ScoreResult:
    frozen_baseline = max(float(baseline_value), 1.0)
    current = max(float(current_engagement), 0.0)
    follower_count = max(int(followers), 0)
    active = thresholds or thresholds_for_followers(follower_count)
    r_value = current / frozen_baseline
    m_value = current / follower_count if follower_count else 0.0
    v_value = max(int(views), 0) / follower_count if follower_count else 0.0

    velocity = 0.0
    if previous_engagement is not None and previous_age_hours is not None:
        elapsed = max(float(age_hours) - float(previous_age_hours), 0.0)
        if elapsed > 0:
            velocity = max(current - float(previous_engagement), 0.0) / elapsed

    grade, label = grade_work(r_value, m_value, active)
    return ScoreResult(
        grade=grade,
        label=label,
        r_value=round(r_value, 4),
        m_value=round(m_value, 6),
        v_value=round(v_value, 6),
        velocity=round(velocity, 4),
        baseline_value=round(frozen_baseline, 4),
        thresholds=asdict(active),
    )
