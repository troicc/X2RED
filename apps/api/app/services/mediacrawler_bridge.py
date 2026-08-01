from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import Asset, RawSnapshot, RightsStatus, SourceItem


class MediaCrawlerError(RuntimeError):
    pass


PLATFORMS: dict[str, dict[str, Any]] = {
    "xhs": {
        "label": "小红书",
        "domains": ("xiaohongshu.com", "rednote.com"),
        "id": ("note_id", "id"),
        "title": ("title",),
        "text": ("desc", "content"),
        "url": ("note_url", "url"),
        "author": ("nickname", "author_name"),
        "time": ("time", "create_time"),
        "images": ("image_list", "images"),
    },
    "dy": {
        "label": "抖音",
        "domains": ("douyin.com",),
        "id": ("aweme_id", "video_id", "id"),
        "title": ("title", "desc"),
        "text": ("desc", "content"),
        "url": ("aweme_url", "video_url", "url"),
        "author": ("nickname", "author_name"),
        "time": ("create_time", "time"),
        "images": ("cover_url", "image_list", "images"),
    },
    "ks": {
        "label": "快手",
        "domains": ("kuaishou.com",),
        "id": ("video_id", "photo_id", "id"),
        "title": ("title", "caption"),
        "text": ("desc", "caption", "content"),
        "url": ("video_url", "note_url", "url"),
        "author": ("nickname", "author_name"),
        "time": ("create_time", "time"),
        "images": ("cover_url", "image_list", "images"),
    },
    "bili": {
        "label": "哔哩哔哩",
        "domains": ("bilibili.com", "b23.tv"),
        "id": ("video_id", "bvid", "aid", "id"),
        "title": ("title",),
        "text": ("desc", "description", "content"),
        "url": ("video_url", "note_url", "url"),
        "author": ("nickname", "author_name", "up_name"),
        "time": ("create_time", "pubtime", "time"),
        "images": ("cover_url", "image_list", "images"),
    },
    "wb": {
        "label": "微博",
        "domains": ("weibo.com", "weibo.cn"),
        "id": ("note_id", "mblog_id", "id"),
        "title": ("title",),
        "text": ("content", "text", "desc"),
        "url": ("note_url", "mblog_url", "url"),
        "author": ("nickname", "author_name"),
        "time": ("create_time", "created_at", "time"),
        "images": ("image_list", "pic_urls", "images"),
    },
    "tieba": {
        "label": "百度贴吧",
        "domains": ("tieba.baidu.com",),
        "id": ("note_id", "thread_id", "id"),
        "title": ("title",),
        "text": ("desc", "content", "text"),
        "url": ("note_url", "thread_url", "url"),
        "author": ("nickname", "user_nickname", "author_name"),
        "time": ("create_time", "time"),
        "images": ("image_list", "images"),
    },
    "zhihu": {
        "label": "知乎",
        "domains": ("zhihu.com",),
        "id": ("content_id", "answer_id", "question_id", "id"),
        "title": ("title", "question_title"),
        "text": ("content_text", "content", "excerpt", "desc"),
        "url": ("content_url", "answer_url", "url"),
        "author": ("author_name", "nickname"),
        "time": ("created_time", "create_time", "time"),
        "images": ("image_list", "images"),
    },
}


def _first(data: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = data.get(name)
        if value not in (None, "", [], {}):
            return value
    return ""


def _text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.replace("\x00", " ").split())
    if value is None:
        return ""
    return str(value)


def _image_urls(value: Any) -> list[str]:
    values: list[Any]
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                values = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                values = stripped.split(",")
        else:
            values = stripped.split(",")
    elif isinstance(value, dict):
        values = list(value.values())
    else:
        values = []

    urls: list[str] = []
    for item in values:
        if isinstance(item, dict):
            candidate = (
                item.get("url")
                or item.get("url_default")
                or item.get("master_url")
                or item.get("src")
            )
        else:
            candidate = item
        url = _text(candidate)
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    return urls[:10]


def _as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)) or str(value).isdigit():
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


class MediaCrawlerBridge:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def root(self) -> Path:
        return Path(self.settings.mediacrawler_root).expanduser().resolve()

    @property
    def runner(self) -> Path:
        return Path(__file__).resolve().parents[4] / "scripts" / "run-mediacrawler.py"

    @property
    def python(self) -> Path:
        override = str(self.settings.mediacrawler_python or "").strip()
        if override:
            return Path(override).expanduser().resolve()
        windows = self.root / ".venv" / "Scripts" / "python.exe"
        if windows.exists():
            return windows
        return self.root / ".venv" / "bin" / "python"

    def cdp_reachable(self) -> bool:
        if not self.settings.mediacrawler_connect_existing:
            return True
        try:
            with socket.create_connection(
                ("127.0.0.1", self.settings.mediacrawler_cdp_port),
                timeout=0.35,
            ):
                return True
        except OSError:
            return False

    def installed(self) -> bool:
        return (self.root / "main.py").is_file() and self.python.is_file()

    def statuses(self) -> list[dict[str, Any]]:
        installed = self.installed()
        cdp_ready = self.cdp_reachable()
        return [
            {
                "id": platform,
                "label": meta["label"],
                "configured": installed,
                "ready": installed and cdp_ready,
                "description": (
                    "MediaCrawler 已安装；CDP 已连接"
                    if installed and cdp_ready
                    else "MediaCrawler 已安装；请开启 Chrome 远程调试"
                    if installed
                    else "MediaCrawler 尚未安装；重新运行 scripts/start.sh"
                ),
            }
            for platform, meta in PLATFORMS.items()
        ]

    def search(
        self,
        *,
        platform: str,
        query: str,
        max_results: int,
        login_type: str | None = None,
    ) -> dict[str, Any]:
        if platform not in PLATFORMS:
            raise MediaCrawlerError(f"不支持的平台：{platform}")
        query = query.strip()
        if not query:
            raise MediaCrawlerError("搜索关键词不能为空")
        if not self.installed():
            raise MediaCrawlerError(
                "MediaCrawler 尚未安装。重新执行 ./scripts/start.sh，"
                "或运行 sh scripts/setup-mediacrawler.sh .venv/bin/python。"
            )
        if not self.runner.is_file():
            raise MediaCrawlerError(f"缺少 MediaCrawler 运行器：{self.runner}")
        if not self.cdp_reachable():
            raise MediaCrawlerError(
                "无法连接 Chrome CDP。请在 Chrome 打开 "
                "chrome://inspect/#remote-debugging，启用远程调试，"
                f"确认 127.0.0.1:{self.settings.mediacrawler_cdp_port} 正在监听后重试。"
            )

        limit = max(1, min(int(max_results), self.settings.mediacrawler_max_results))
        run_id = uuid.uuid4().hex
        output_dir = (
            Path(self.settings.raw_dir).resolve() / "mediacrawler" / "runs" / run_id
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        effective_login = login_type or self.settings.mediacrawler_login_type
        command = [
            str(self.python),
            str(self.runner),
            "--root",
            str(self.root),
            "--output",
            str(output_dir),
            "--platform",
            platform,
            "--login-type",
            effective_login,
            "--keywords",
            query,
            "--max-results",
            str(limit),
            "--cdp-port",
            str(self.settings.mediacrawler_cdp_port),
            "--connect-existing",
            "true" if self.settings.mediacrawler_connect_existing else "false",
        ]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        try:
            completed = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[4],
                env=env,
                capture_output=True,
                text=True,
                timeout=self.settings.mediacrawler_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaCrawlerError(
                f"MediaCrawler 运行超过 {self.settings.mediacrawler_timeout_seconds} 秒"
            ) from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "未知错误").strip()
            raise MediaCrawlerError(f"MediaCrawler 执行失败：{detail[-1500:]}")

        records: list[dict[str, Any]] = []
        for path in sorted(
            output_dir.glob(f"{platform}/jsonl/search_contents_*.jsonl")
        ):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        records.append(item)

        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in records:
            normalized = self.normalize_item(
                platform=platform,
                item=record,
                query=query,
            )
            key = normalized["external_id"] or normalized["url"]
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(normalized)
            if len(items) >= limit:
                break

        return {
            "provider": "mediacrawler",
            "platform": platform,
            "query": query,
            "count": len(items),
            "items": items,
            "attempts": [
                {
                    "provider": f"mediacrawler:{platform}",
                    "status": "ok" if items else "empty",
                    "count": len(items),
                    "run_id": run_id,
                }
            ],
            "stdout": completed.stdout[-1200:],
        }

    @staticmethod
    def normalize_item(
        *,
        platform: str,
        item: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        meta = PLATFORMS[platform]
        external_id = _text(_first(item, meta["id"]))
        title = _text(_first(item, meta["title"]))
        body = _text(_first(item, meta["text"]))
        url = _text(_first(item, meta["url"]))
        author = _text(_first(item, meta["author"]))
        published = _as_datetime(_first(item, meta["time"]))
        images = _image_urls(_first(item, meta["images"]))
        if not title:
            title = body[:80] or f"{meta['label']}内容"
        metrics = {
            key: item.get(key)
            for key in (
                "liked_count",
                "collected_count",
                "comment_count",
                "share_count",
                "favorite_count",
                "view_count",
            )
            if item.get(key) not in (None, "")
        }
        safe_payload = {
            key: value
            for key, value in item.items()
            if key not in {"cookies", "cookie", "xsec_token", "sec_uid"}
        }
        return {
            "provider": "mediacrawler",
            "platform": platform,
            "external_id": external_id,
            "url": url,
            "title": title,
            "summary": body[:420],
            "text": body,
            "author_name": author,
            "author_handle": "",
            "published_at": published.isoformat() if published else "",
            "image_url": images[0] if images else "",
            "image_urls": images,
            "metrics": metrics,
            "site": meta["label"],
            "discovery_source": f"mediacrawler:{platform}",
            "discovery_keyword": query,
            "crawler_payload": safe_payload,
        }

    def import_candidate(
        self,
        db: Session,
        *,
        candidate: dict[str, Any],
        category: str,
        editor_note: str,
    ) -> SourceItem:
        platform = _text(candidate.get("platform"))
        if platform not in PLATFORMS:
            raise MediaCrawlerError("候选内容缺少有效的 MediaCrawler 平台")
        url = _text(candidate.get("url"))
        self._validate_platform_url(platform, url)
        external_id = _text(candidate.get("external_id"))
        if not external_id:
            external_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]
        external_id = external_id[:64]
        body = _text(candidate.get("text") or candidate.get("summary"))[:250_000]
        title = _text(candidate.get("title"))[:300]
        author_name = _text(candidate.get("author_name"))[:160]
        author_handle = _text(candidate.get("author_handle"))[:80]
        metrics = candidate.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        images = _image_urls(candidate.get("image_urls") or candidate.get("image_url"))
        created_at = _as_datetime(candidate.get("published_at"))

        source = db.scalar(
            select(SourceItem).where(
                SourceItem.platform == platform,
                SourceItem.external_id == external_id,
            )
        )
        structured = {
            "source": "mediacrawler",
            "platform": platform,
            "category": category,
            "title": title,
            "summary": _text(candidate.get("summary")),
            "discovery_keyword": _text(candidate.get("discovery_keyword")),
            "metrics": metrics,
            "image_urls": images,
            "crawler_payload": candidate.get("crawler_payload") or {},
        }
        note = editor_note.strip()
        rights_note = (
            "通过 MediaCrawler 使用本机浏览器登录态采集公开平台内容；"
            "仅限研究和有限引用，发布前必须人工复核平台条款、版权和隐私。"
        )
        if source is None:
            source = SourceItem(
                provider="mediacrawler",
                platform=platform,
                external_id=external_id,
                canonical_url=url,
                author_handle=author_handle,
                author_name=author_name,
                text_original=body,
                language="zh-CN",
                created_at=created_at,
                content_kind="post",
                structured_content_json=json.dumps(
                    structured,
                    ensure_ascii=False,
                    default=str,
                ),
                editor_note=note,
                metrics_json=json.dumps(metrics, ensure_ascii=False, default=str),
                rights_status=RightsStatus.limited_quote.value,
                rights_note=rights_note,
            )
            db.add(source)
            db.flush()
        else:
            source.canonical_url = url
            source.author_handle = author_handle
            source.author_name = author_name
            source.text_original = body
            source.created_at = created_at or source.created_at
            source.structured_content_json = json.dumps(
                structured,
                ensure_ascii=False,
                default=str,
            )
            source.editor_note = note or source.editor_note
            source.metrics_json = json.dumps(metrics, ensure_ascii=False, default=str)
            source.rights_status = RightsStatus.limited_quote.value
            source.rights_note = rights_note
            db.flush()

        existing_urls = {asset.remote_url for asset in source.assets}
        for image_url in images:
            if image_url in existing_urls:
                continue
            source.assets.append(
                Asset(
                    kind="image",
                    role="original",
                    remote_url=image_url,
                    rights_status=RightsStatus.limited_quote.value,
                    rights_note=rights_note,
                )
            )

        snapshot_payload = json.dumps(
            candidate,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        digest = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
        snapshot_dir = (
            Path(self.settings.raw_dir).resolve() / "mediacrawler" / "snapshots"
        )
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"{platform}-{external_id}-{digest[:12]}.json"
        snapshot_path.write_text(snapshot_payload, encoding="utf-8")
        db.add(
            RawSnapshot(
                provider="mediacrawler",
                endpoint=f"mediacrawler://search/{platform}",
                external_id=external_id,
                payload_path=str(snapshot_path),
                payload_sha256=digest,
            )
        )
        return source

    @staticmethod
    def _validate_platform_url(platform: str, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise MediaCrawlerError("候选内容 URL 无效")
        hostname = parsed.hostname.lower()
        domains = PLATFORMS[platform]["domains"]
        if not any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in domains
        ):
            raise MediaCrawlerError(
                f"URL 不属于 {PLATFORMS[platform]['label']}：{hostname}"
            )
