from __future__ import annotations

import re
from urllib.parse import urlparse

_POST_ID_RE = re.compile(r"/status(?:es)?/(\d{2,20})(?:/|$)")
_ALLOWED_HOSTS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
    "fxtwitter.com",
    "www.fxtwitter.com",
    "fixupx.com",
    "www.fixupx.com",
}


def extract_x_post_id(value: str) -> str:
    value = value.strip()
    if value.isdigit() and 2 <= len(value) <= 20:
        return value

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError("不是受支持的 X/FxTwitter 地址")
    match = _POST_ID_RE.search(parsed.path)
    if not match:
        raise ValueError("地址中没有找到 Post ID")
    return match.group(1)
