from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from app.services.native_skill_manager import NativeSkillError


class NativeDeckRenderer:
    """Render the actual upstream seed-template poster elements.

    This renderer does not redraw the design in X2RED. It opens the generated
    single-file HTML and screenshots each upstream `.poster.xhs` element.
    """

    def available(self) -> bool:
        return importlib.util.find_spec("playwright") is not None

    def render(self, html_path: Path, output_dir: Path) -> list[str]:
        if not self.available():
            raise NativeSkillError("未安装 Playwright，无法运行 Guizang 原生渲染链")
        from playwright.sync_api import sync_playwright

        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
            )
            page = browser.new_page(
                viewport={"width": 2400, "height": 2000},
                device_scale_factor=1,
            )
            page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=90_000)
            try:
                page.evaluate("document.fonts && document.fonts.ready")
            except Exception:
                pass
            page.wait_for_timeout(1200)
            posters = page.locator(".poster.xhs")
            if posters.count() == 0:
                posters = page.locator(".poster")
            count = posters.count()
            if count == 0:
                browser.close()
                raise NativeSkillError("Guizang HTML 中没有找到 .poster 元素")
            for index in range(count):
                element = posters.nth(index)
                path = output_dir / f"{index + 1:02d}.png"
                element.screenshot(path=str(path), animations="disabled")
                paths.append(str(path.resolve()))
            browser.close()
        return paths

    @staticmethod
    def poster_count(html: str) -> int:
        return len(
            re.findall(
                r"<section\b[^>]*class=[\"'][^\"']*\bposter\b[^\"']*[\"']",
                html,
                flags=re.I,
            )
        )

    @staticmethod
    def run_upstream_validator(skill_dir: Path, task_dir: Path) -> dict[str, Any]:
        script = skill_dir / "validate-social-deck.mjs"
        node_module = skill_dir / "node_modules" / "playwright"
        if not script.is_file() or not node_module.is_dir():
            return {
                "ran": False,
                "passed": False,
                "returncode": None,
                "output": "上游 validator 运行时尚未安装",
            }
        try:
            completed = subprocess.run(
                ["node", str(script), str(task_dir)],
                cwd=str(skill_dir),
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "ran": False,
                "passed": False,
                "returncode": None,
                "output": str(exc)[:2000],
            }
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        report = {
            "ran": True,
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "output": output[-8000:],
        }
        (task_dir / "validator-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report
