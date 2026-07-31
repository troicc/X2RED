from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def fill_first(page, selectors: tuple[str, ...], text: str) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            locator.fill(text, timeout=5000)
            return True
        except Exception:
            continue
    return False


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m app.services.xhs_preview_worker PACKAGE_JSON PROFILE_DIR")
        return 2

    package_path = Path(sys.argv[1]).resolve()
    profile_dir = Path(sys.argv[2]).resolve()
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright 未安装。请执行: pip install -e '.[publisher]'", file=sys.stderr)
        return 3

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(
            "https://creator.xiaohongshu.com/publish/publish?source=official",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        print("X2RED 已打开小红书创作中心。首次使用请先登录。")

        files = [path for path in payload.get("assets", []) if Path(path).is_file()]
        if files:
            video_suffixes = {".mp4", ".mov", ".m4v", ".webm"}
            is_video = Path(files[0]).suffix.lower() in video_suffixes
            tab_selectors = (
                ("text=上传视频", "text=视频")
                if is_video
                else ("text=上传图文", "text=图文")
            )
            for selector in tab_selectors:
                try:
                    page.locator(selector).first.click(timeout=3000)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(1000)
            try:
                upload_files = files[:1] if is_video else files[:18]
                page.locator('input[type="file"]').first.set_input_files(
                    upload_files, timeout=20_000
                )
                page.wait_for_timeout(6000 if is_video else 3500)
            except Exception as exc:
                print(f"素材上传未完成: {exc}", file=sys.stderr)

        fill_first(
            page,
            ('input[placeholder*="标题"]', 'input.c-input_inner'),
            str(payload.get("title") or "")[:20],
        )
        caption = str(payload.get("body") or "")
        tags = payload.get("tags") or []
        if tags:
            caption += "\n\n" + " ".join(f"#{tag}" for tag in tags)
        fill_first(page, ('[contenteditable="true"]', '.ql-editor', 'textarea'), caption[:1000])

        print("内容已尽量填入。X2RED 不会点击最终发布，请在浏览器中检查并手动发布。")
        print("关闭浏览器窗口后本进程退出。")
        try:
            while context.pages:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
