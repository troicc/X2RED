from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.schemas import CardGenerateRequest
from app.services.guizang_native_full import FullGuizangNativeService
from app.services.market_material_harvester import MarketMaterialHarvester
from app.services.material_extraction_providers import MaterialExtractionProviders
from app.services.material_harvester import MaterialHarvester, MaterialHarvesterError
from app.services.material_search_providers import (
    MaterialSearchEngine,
    MaterialSearchError,
    SearchCandidate,
)
from app.services.minimal_zine_native import MinimalZineNativeService
from app.services.native_deck_renderer import NativeDeckRenderer
from app.services.native_skill_manager import NATIVE_SKILLS, NativeSkillManager
from app.services.resilient_material_search import ResilientMaterialSearchEngine


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


def test_search_provider_status_and_auto_failover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = ResilientMaterialSearchEngine(
        settings(
            tmp_path,
            firecrawl_api_key="fc-test",
            tavily_api_key="tvly-test",
        )
    )
    statuses = {item["id"]: item for item in engine.statuses()}
    assert statuses["firecrawl"]["configured"] is True
    assert statuses["jina"]["configured"] is True
    assert statuses["tavily"]["configured"] is True
    assert statuses["serpapi_baidu"]["configured"] is False
    assert statuses["gdelt"]["configured"] is True

    calls: list[str] = []

    def fake_search_one(provider: str, **_: Any) -> list[SearchCandidate]:
        calls.append(provider)
        if provider == "firecrawl":
            raise AttributeError("malformed provider response")
        if provider == "tavily":
            return [
                SearchCandidate(
                    url="https://example.com/life",
                    title="社区食堂里的晚饭",
                    discovery_source="tavily-china",
                )
            ]
        return []

    monkeypatch.setattr(engine, "_search_one", fake_search_one)
    result = engine.search(provider="auto", query="退休 社区", max_results=10)
    assert result["provider"] == "tavily"
    assert calls == ["firecrawl", "jina", "tavily"]
    assert any(item["status"] == "failed" for item in result["attempts"])


def test_explicit_unconfigured_provider_fails_cleanly(tmp_path: Path) -> None:
    engine = MaterialSearchEngine(settings(tmp_path))
    with pytest.raises(MaterialSearchError, match="所有搜索供应商"):
        engine.search(provider="serpapi_baidu", query="退休生活")


def test_market_extractors_prefer_vendor_services(tmp_path: Path) -> None:
    service = MarketMaterialHarvester(
        settings(tmp_path, firecrawl_api_key="fc-test")
    )
    statuses = {item["id"]: item for item in service.extractor_statuses()}
    assert statuses["firecrawl"]["configured"] is True
    assert statuses["jina"]["configured"] is True
    assert statuses["direct"]["configured"] is True
    assert statuses["playwright"]["configured"] is False


def test_jina_plain_text_and_markdown_cleanup() -> None:
    metadata, markdown = MaterialExtractionProviders.parse_jina_text(
        "Title: 社区晚饭\n"
        "URL Source: https://example.com/a\n"
        "Published Time: 2026-08-01\n"
        "Markdown Content:\n"
        "# 社区晚饭\n\n"
        "- 老人们每天傍晚来吃饭\n"
        "[原文](https://example.com/source)"
    )
    assert metadata["Title"] == "社区晚饭"
    assert metadata["URL Source"] == "https://example.com/a"
    cleaned = MaterialExtractionProviders.markdown_to_text(markdown)
    assert "# " not in cleaned
    assert "老人们每天傍晚来吃饭" in cleaned
    assert "原文" in cleaned
    assert "https://example.com/source" not in cleaned


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
