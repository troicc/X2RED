from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.schemas import CardGenerateRequest
from app.services.guizang_native_full import FullGuizangNativeService
from app.services.material_harvester import MaterialHarvester, MaterialHarvesterError
from app.services.minimal_zine_native import MinimalZineNativeService
from app.services.native_deck_renderer import NativeDeckRenderer
from app.services.native_skill_manager import NATIVE_SKILLS, NativeSkillManager


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "native-skills",
        scheduler_enabled=False,
    )


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
        '<!-- X2RED_UPSTREAM_THEME:forest-ink -->'
        '<section class="poster xhs" id="xhs-01"></section>'
        '<section class="poster xhs" id="xhs-02"></section>'
    )
    document = FullGuizangNativeService._assemble_document(seed, posters, max_cards=6)
    assert "placeholder" not in document
    assert NativeDeckRenderer.poster_count(document) == 2
    assert 'data-theme="forest-ink"' in document


def test_card_schema_accepts_full_guizang_modes() -> None:
    assert CardGenerateRequest(visual_style="guizang_editorial").visual_style == "guizang_editorial"
    assert CardGenerateRequest(visual_style="guizang_swiss").visual_style == "guizang_swiss"


def test_minimal_zine_requires_explicit_image_model(tmp_path: Path) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    assert service.image_configured is False
