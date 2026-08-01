from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from app.domain.models import DraftRevision
from app.services.cards import CardRenderError
from app.services.guizang_native import GuizangNativeService
from app.services.native_deck_renderer import NativeDeckRenderer
from app.services.native_skill_manager import NativeSkillError


class FullGuizangNativeService(GuizangNativeService):
    """Complete the upstream seed runtime without modifying the pinned checkout."""

    def _copy_input_assets(self, draft: DraftRevision, task_dir: Path) -> list[dict[str, str]]:
        skill_dir = self.manager.path_for(self.skill_name)
        source_assets = skill_dir / "assets"
        if not source_assets.is_dir():
            raise NativeSkillError("Guizang 上游 assets 目录不完整")
        shutil.copytree(source_assets, task_dir / "assets", dirs_exist_ok=True)
        return super()._copy_input_assets(draft, task_dir)

    def _compose_posters(
        self,
        *,
        draft: DraftRevision,
        source_brief: str,
        references: str,
        plan: dict[str, Any],
        style_mode: str,
        max_cards: int,
    ) -> str:
        posters = super()._compose_posters(
            draft=draft,
            source_brief=source_brief,
            references=references,
            plan=plan,
            style_mode=style_mode,
            max_cards=max_cards,
        )
        return self._with_theme_marker(posters, plan)

    def _repair_posters(
        self,
        *,
        draft: DraftRevision,
        source_brief: str,
        references: str,
        plan: dict[str, Any],
        posters_html: str,
        validator_output: str,
        max_cards: int,
    ) -> str:
        repaired = super()._repair_posters(
            draft=draft,
            source_brief=source_brief,
            references=references,
            plan=plan,
            posters_html=self._without_theme_marker(posters_html),
            validator_output=validator_output,
            max_cards=max_cards,
        )
        return self._with_theme_marker(repaired, plan)

    @staticmethod
    def _with_theme_marker(posters_html: str, plan: dict[str, Any]) -> str:
        theme = re.sub(r"[^a-z0-9-]", "", str(plan.get("theme") or "").lower())
        return f"<!-- X2RED_UPSTREAM_THEME:{theme} -->\n{posters_html}"

    @staticmethod
    def _without_theme_marker(posters_html: str) -> str:
        return re.sub(
            r"<!--\s*X2RED_UPSTREAM_THEME:[a-z0-9-]+\s*-->\s*",
            "",
            posters_html,
            count=1,
        )

    @staticmethod
    def _assemble_document(seed: str, posters_html: str, *, max_cards: int) -> str:
        theme_match = re.search(r"X2RED_UPSTREAM_THEME:([a-z0-9-]+)", posters_html)
        theme = theme_match.group(1) if theme_match else ""
        posters_html = FullGuizangNativeService._without_theme_marker(posters_html)
        sheet = re.compile(r'<main class="sheet">.*?</main>', re.S)
        if not sheet.search(seed):
            raise CardRenderError("Guizang 种子模板缺少 sheet 主体")
        document = sheet.sub(
            f'<main class="sheet">\n{posters_html}\n</main>',
            seed,
            count=1,
        )
        editorial_themes = {
            "ink-classic",
            "indigo-porcelain",
            "forest-ink",
            "kraft-paper",
            "dune",
            "midnight-ink",
        }
        swiss_accents = {"ikb", "lemon-yellow", "lemon-green", "safety-orange"}
        if theme in editorial_themes and "data-theme=" in document:
            document = re.sub(
                r'data-theme="[^"]+"',
                f'data-theme="{theme}"',
                document,
                count=1,
            )
        elif theme in swiss_accents and "data-accent=" in document:
            document = re.sub(
                r'data-accent="[^"]+"',
                f'data-accent="{theme}"',
                document,
                count=1,
            )
        count = NativeDeckRenderer.poster_count(document)
        if count < 2 or count > max_cards:
            raise CardRenderError(f"组装后的 Guizang 页面数量异常：{count}")
        return document
