from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_INTERNAL_EXACT = {
    "x2red",
    "wechat / x2red",
    "x source",
    "x2pdf",
    "x2red editorial",
    "x2red creator studio",
    "x2red 本地创作工作台",
    "从一份来源，生成不同平台的表达",
    "从来源到判断 · x2red",
}
_INTERNAL_PATTERNS = (
    re.compile(r"\bWECHAT\s*/\s*X2RED\b", re.I),
    re.compile(r"\bX2RED(?:\s+(?:EDITORIAL|CREATOR\s+STUDIO))?\b", re.I),
    re.compile(r"\bX\s+SOURCE\b", re.I),
    re.compile(r"\bX2PDF\b", re.I),
    re.compile(r"从一份来源[，,]\s*生成不同平台的表达"),
    re.compile(r"从来源到判断\s*[·•]\s*X2RED", re.I),
)


def strip_internal_markers(value: str) -> str:
    """Remove product/workflow markers from publishable metadata.

    This function is deliberately used for labels, kickers and footers only.
    It must not silently rewrite article facts or a title that genuinely talks
    about X2RED itself.
    """

    text = str(value or "").strip()
    if not text:
        return ""
    if text.casefold() in _INTERNAL_EXACT:
        return ""
    for pattern in _INTERNAL_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\s*[|/·•—–-]\s*$", "", text).strip()
    text = re.sub(r"\s{2,}", " ", text)
    return text


def public_card_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return a publish-safe card specification.

    Reader-facing content remains intact. Internal metadata is blanked, source
    attribution is opt-in, and a stable public visibility flag is stored for
    reproducibility and regression tests.
    """

    output = dict(spec)
    output["visibility_mode"] = "public"
    output["branding"] = ""
    output["source"] = ""
    output["footer"] = ""
    output["content_type"] = ""
    output["kicker"] = strip_internal_markers(str(output.get("kicker") or ""))
    return output


def contains_internal_marker(value: str) -> bool:
    text = str(value or "")
    if not text:
        return False
    lowered = text.casefold()
    if any(marker in lowered for marker in _INTERNAL_EXACT if marker):
        return True
    return any(pattern.search(text) for pattern in _INTERNAL_PATTERNS)
