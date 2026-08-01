from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.schemas import CardGenerateRequest
from app.services.guizang_native_full import FullGuizangNativeService
from app.services.market_material_harvester import MarketMaterialHarvester
from app.services.material_harvester import MaterialHarvester, MaterialHarvesterError
from app.services.mediacrawler_bridge import MediaCrawlerBridge, MediaCrawlerError
from app.services.minimal_zine_native import MinimalZineNativeService
from app.services.native_deck_renderer import NativeDeckRenderer
from app.services.native_skill_manager import NATIVE_SKILLS, NativeSkillManager


def settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "media_dir": tmp_path / "assets",
        "raw_dir": tmp_path / "raw",
        "export_dir": tmp_path / "exports",
        "browser_profile_dir": tmp_path / "profile",
        "native_skill_dir": tmp_path / "native-skills",
        "scheduler_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_material_fit_and_private_network_gate(tmp_path: Path) -> None:
    service = MaterialHarvester(settings(tmp_path))
    mature = service.fit_score(
        category="mature_life",
        text="退休以后，她在社区食堂和老朋友一起吃饭，也开始照顾自己的睡眠。",
    )
    technical = service.fit_score(
        category="mature_life",
        text="CUDA kernel benchmark and GPU inference throughput",
    )
    assert mature > technical
    assert mature >= 0.8

    for url in (
        "http://127.0.0.1/admin",
        "http://localhost:8787/health",
        "http://10.0.0.8/private",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
    ):
        with pytest.raises(MaterialHarvesterError):
            service.validate_public_url(url, resolve_dns=False)


def test_market_discovery_query_defaults_to_chinese_terms(tmp_path: Path) -> None:
    service = MarketMaterialHarvester(settings(tmp_path))
    query = service.discovery_query(category="mature_life")
    assert "退休" in query
    assert "社区" in query
    assert (
        service.discovery_query(
            category="mature_life",
            query="  社区食堂 老朋友  ",
        )
        == "社区食堂 老朋友"
    )


def test_mediacrawler_status_and_xhs_normalization(tmp_path: Path) -> None:
    root = tmp_path / "MediaCrawler"
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / "main.py").write_text("", encoding="utf-8")
    (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    bridge = MediaCrawlerBridge(
        settings(
            tmp_path,
            mediacrawler_root=root,
            mediacrawler_connect_existing=False,
        )
    )
    statuses = {item["id"]: item for item in bridge.statuses()}
    assert statuses["xhs"]["configured"] is True
    assert statuses["xhs"]["ready"] is True
    assert statuses["zhihu"]["configured"] is True

    normalized = bridge.normalize_item(
        platform="xhs",
        query="退休生活",
        item={
            "note_id": "abc123",
            "title": "退休后的社区晚饭",
            "desc": "每天傍晚和老朋友一起吃饭。",
            "note_url": "https://www.xiaohongshu.com/explore/abc123",
            "nickname": "张阿姨",
            "time": 1_700_000_000_000,
            "image_list": "https://example.com/a.jpg,https://example.com/b.jpg",
            "liked_count": "88",
            "xsec_token": "secret",
        },
    )
    assert normalized["provider"] == "mediacrawler"
    assert normalized["platform"] == "xhs"
    assert normalized["external_id"] == "abc123"
    assert normalized["title"] == "退休后的社区晚饭"
    assert normalized["image_urls"] == [
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",
    ]
    assert "xsec_token" not in normalized["crawler_payload"]


def test_mediacrawler_rejects_cross_platform_url(tmp_path: Path) -> None:
    bridge = MediaCrawlerBridge(settings(tmp_path))
    with pytest.raises(MediaCrawlerError, match=r"不属于\s*小红书"):
        bridge._validate_platform_url("xhs", "https://www.zhihu.com/question/1")


def test_mediacrawler_setup_uses_uv_without_editable_build() -> None:
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "setup-mediacrawler.sh"
    ).read_text(encoding="utf-8")
    assert "uv.lock" in script
    assert "--frozen" in script
    assert "--no-install-project" in script
    assert 'pip install -e "$MEDIACRAWLER_ROOT"' not in script


def test_native_skill_definitions_are_pinned_and_licensed(tmp_path: Path) -> None:
    manager = NativeSkillManager(settings(tmp_path))
    guizang = NATIVE_SKILLS["guizang-social-card-skill"]
    zine = NATIVE_SKILLS["gc-minimal-zine-poster-v0-1"]
    assert guizang.license == "AGPL-3.0"
    assert len(guizang.commit) == 40
    assert zine.license == "MIT"
    assert len(zine.commit) == 40
    statuses = manager.statuses()
    assert {item["name"] for item in statuses} == set(NATIVE_SKILLS)
    assert all(item["installed"] is False for item in statuses)


def test_guizang_seed_replacement_removes_placeholder_demo() -> None:
    seed = """<!doctype html><html data-theme="ink-classic"><body><main class="sheet">
<!-- POSTERS_HERE --><section class="poster xhs" id="placeholder"></section>
</main><script></script></body></html>"""
    posters = (
        "<!-- X2RED_UPSTREAM_THEME:forest-ink -->"
        '<section class="poster xhs" id="xhs-01"></section>'
        '<section class="poster xhs" id="xhs-02"></section>'
    )
    document = FullGuizangNativeService._assemble_document(seed, posters, max_cards=6)
    assert "placeholder" not in document
    assert NativeDeckRenderer.poster_count(document) == 2
    assert 'data-theme="forest-ink"' in document


def test_card_schema_accepts_full_guizang_modes() -> None:
    assert (
        CardGenerateRequest(visual_style="guizang_editorial").visual_style
        == "guizang_editorial"
    )
    assert (
        CardGenerateRequest(visual_style="guizang_swiss").visual_style
        == "guizang_swiss"
    )


def test_minimal_zine_requires_explicit_image_model(tmp_path: Path) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    assert service.image_configured is False
