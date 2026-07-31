from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/extension", tags=["extension"])


class ExtensionPing(BaseModel):
    url: str
    selected_text: str = ""
    note: str = ""


@router.post("/capture")
def capture_from_extension(body: ExtensionPing) -> dict:
    # The extension submits into the normal URL intake screen rather than importing silently.
    return {
        "ok": True,
        "open": f"/?url={body.url}",
        "message": "已接收链接，请在 X2RED 页面确认导入模式",
    }
