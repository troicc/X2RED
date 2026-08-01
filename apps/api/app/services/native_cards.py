from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision
from app.services.guizang_native_full import FullGuizangNativeService
from app.services.rich_cards import RichCardService


class NativeAwareCardService(RichCardService):
    """Keep the existing fast renderer and expose the full upstream engine."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.guizang = FullGuizangNativeService(settings)

    def render(
        self,
        db: Session,
        draft: DraftRevision,
        *,
        template: str,
        visual_style: str,
        layout: str,
        palette: str,
        material_strategy: str,
        max_cards: int,
    ) -> CardRender:
        if visual_style in {"guizang_editorial", "guizang_swiss"}:
            return self.guizang.render(
                db,
                draft,
                style_mode="editorial" if visual_style.endswith("editorial") else "swiss",
                palette=palette,
                material_strategy=material_strategy,
                max_cards=max_cards,
            )
        return super().render(
            db,
            draft,
            template=template,
            visual_style=visual_style,
            layout=layout,
            palette=palette,
            material_strategy=material_strategy,
            max_cards=max_cards,
        )
