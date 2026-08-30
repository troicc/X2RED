"""Browser acceptance for UI1's unified creative and visual workflow."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GROUPS = ["收集", "创作", "视觉", "发布", "资产与偏好", "设置"]
EXPECTED_VIEWS = {
    "signals-view",
    "materials-view",
    "corpus-pools-view",
    "creative-task-view",
    "workbench-view",
    "wechat-view",
    "visual-workflow-view",
    "publish-view",
    "pool-memory-view",
    "style-lab-view",
    "settings-view",
}
LEGACY_IDS = {
    "intake-form",
    "source-list",
    "writing-project-form",
    "wechat-create-form",
    "wechat-source",
    "publish-list",
    "skill-list",
}


def free_port() -> int:
    with socket.socket() as value:
        value.bind(("127.0.0.1", 0))
        return int(value.getsockname()[1])


def isolated_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    data = root / "data"
    env.update(
        {
            "X2RED_DATABASE_URL": f"sqlite:///{data / 'ui1.db'}",
            "X2RED_MEDIA_DIR": str(data / "assets"),
            "X2RED_RAW_DIR": str(data / "raw"),
            "X2RED_EXPORT_DIR": str(data / "exports"),
            "X2RED_BROWSER_PROFILE_DIR": str(data / "profile"),
            "X2RED_NATIVE_SKILL_DIR": str(data / "native-skills"),
            "X2RED_SCHEDULER_ENABLED": "false",
            "X2RED_MODEL_BASE_URL": "",
            "X2RED_MODEL_API_KEY": "",
            "X2RED_MODEL_NAME": "",
            "X2RED_IMAGE_BASE_URL": "",
            "X2RED_IMAGE_API_KEY": "",
            "X2RED_IMAGE_MODEL": "",
        }
    )
    for key in (
        "ALL_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "http_proxy",
        "https_proxy",
    ):
        env.pop(key, None)
    return env


def wait_for_server(base_url: str, process: subprocess.Popen[bytes], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    with httpx.Client(trust_env=False, timeout=1) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"UI1 test server exited with code {process.returncode}")
            try:
                if client.get(f"{base_url}/health").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.15)
    raise RuntimeError("UI1 test server did not become ready")


@contextmanager
def managed_server(base_url: str = "") -> Iterator[str]:
    if base_url:
        yield base_url.rstrip("/")
        return
    with tempfile.TemporaryDirectory(prefix="x2red-ui1-") as directory:
        env = isolated_environment(Path(directory))
        subprocess.run(
            [sys.executable, "-m", "app.cli", "migrate"],
            cwd=ROOT,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        port = free_port()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app.cli",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--skip-migrate",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            wait_for_server(url, process)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def seed_visual_task(base_url: str) -> tuple[str, str]:
    with httpx.Client(base_url=base_url, trust_env=False, timeout=90) as client:
        response = client.post(
            "/api/sources/manual",
            json={
                "title": "UI1 统一创作验收材料",
                "author_name": "本地编辑",
                "canonical_url": "https://example.com/x2red-ui1",
                "text_original": (
                    "这是用于统一创作流程验收的本地材料。它包含清晰的读者问题、可追溯事实边界、"
                    "编辑判断和视觉线索，用来验证材料选择、工作台交接与旧入口不会丢失。"
                ),
            },
        )
        response.raise_for_status()
        source_id = response.json()["id"]
        response = client.post(
            "/api/platforms/wechat/variants",
            json={
                "source_id": source_id,
                "material_refs": [f"source:{source_id}"],
                "theme": "zen",
                "mode": "adapt",
                "include_citations": True,
                "include_illustration_plan": True,
                "author": "X2RED",
            },
        )
        response.raise_for_status()
        variant = response.json()
        metadata = json.loads(variant["metadata_json"] or "{}")
        if not metadata.get("visual_prompts"):
            raise AssertionError("seeded WeChat variant has no visual prompts")
        return source_id, variant["id"]


def assert_layout(page: Page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_timeout(180)
    metrics = page.evaluate(
        """() => {
          const active = document.querySelector('.app-view.active');
          const rect = active?.getBoundingClientRect();
          return {
            viewport: window.innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            activeLeft: rect?.left ?? 0,
            activeRight: rect?.right ?? 0,
          };
        }"""
    )
    if metrics["documentWidth"] > metrics["viewport"] + 2:
        raise AssertionError(f"document overflows at {width}px: {metrics}")
    if metrics["bodyWidth"] > metrics["viewport"] + 2:
        raise AssertionError(f"body overflows at {width}px: {metrics}")
    if metrics["activeLeft"] < -2 or metrics["activeRight"] > metrics["viewport"] + 2:
        raise AssertionError(f"active view escapes viewport at {width}px: {metrics}")


def run_browser_acceptance(
    base_url: str,
    source_id: str,
    variant_id: str,
    evidence_dir: Path | None = None,
) -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1360, "height": 960},
            reduced_motion="no-preference",
        )
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_function(
            """() => window.__x2redCreativeWorkflowV18?.ready
              && document.querySelectorAll('.product-nav-section').length === 6""",
            timeout=30_000,
        )

        groups = page.locator(".product-nav-section > .product-nav-label > span").all_text_contents()
        if groups != EXPECTED_GROUPS:
            raise AssertionError(f"unexpected navigation groups: {groups}")
        views = set(page.locator(".primary-nav .nav-item").evaluate_all("nodes => nodes.map(node => node.dataset.view)"))
        if views != EXPECTED_VIEWS:
            raise AssertionError(f"navigation entry mismatch: missing={EXPECTED_VIEWS - views}, extra={views - EXPECTED_VIEWS}")
        missing_legacy = [value for value in LEGACY_IDS if page.locator(f"#{value}").count() != 1]
        if missing_legacy:
            raise AssertionError(f"legacy DOM entries disappeared: {missing_legacy}")

        page.locator('[data-view="creative-task-view"]').click()
        page.locator("#creative-task-view.active").wait_for()
        material = page.locator(f'.creative-material-option input[value="source:{source_id}"]')
        material.wait_for()
        material.check()
        page.locator("#creative-step-next").click()
        page.locator('input[name="creative-articleType"][value="editorial_view"]').check()
        page.locator("#creative-step-next").click()
        page.locator('input[name="creative-platform"][value="wechat_long"]').check()
        page.locator("#creative-step-next").click()
        page.locator("#creative-reader").fill("需要判断 AI 内容工具适用边界的中文内容编辑")
        page.locator("#creative-promise").fill("读完后能根据证据、风险和成本选择合适的创作路线")
        page.locator("#creative-step-next").click()
        page.locator('input[name="creative-writingMode"][value="studio"]').check()
        page.locator("#creative-step-next").click()
        page.locator('input[name="creative-visualRoute"][value="wechat_inline"]').check()
        page.locator("#creative-task-summary").get_by_text("公众号长文", exact=True).wait_for()
        if evidence_dir is not None:
            page.screenshot(path=evidence_dir / "creative-task-1360.png", full_page=True)
        stored = page.evaluate("() => JSON.parse(localStorage.getItem('x2red.creative-task.v18'))")
        if stored["materialRefs"] != [f"source:{source_id}"] or stored["reader"] == "":
            raise AssertionError(f"creative brief did not persist: {stored}")

        page.locator("#creative-task-handoff").click()
        page.locator("#wechat-view.active").wait_for()
        page.wait_for_function(
            "sourceId => document.querySelector('#wechat-source')?.value === sourceId",
            arg=source_id,
            timeout=20_000,
        )
        page.locator('[data-view="creative-task-view"]').click()
        page.locator("#creative-task-view.active").wait_for()
        page.wait_for_function("() => document.activeElement?.id === 'creative-task-handoff'")

        current_tab = page.locator('#creative-wizard-steps [role="tab"][aria-selected="true"]')
        current_tab.focus()
        current_tab.press("ArrowLeft")
        if page.locator('.creative-step-panel[data-step="4"]').is_hidden():
            raise AssertionError("wizard ArrowLeft did not activate the previous step")
        page.locator('#creative-wizard-steps [role="tab"][aria-selected="true"]').press("ArrowRight")

        page.locator('[data-view="visual-workflow-view"]').click()
        page.locator("#visual-workflow-view.active").wait_for()
        page.locator(f'.visual-series-item[data-variant-id="{variant_id}"]').click()
        page.get_by_text("Prompt 溯源与差异", exact=True).wait_for()
        page.get_by_text("批量上传", exact=True).wait_for()
        page.get_by_text("Contact Sheet 与候选状态", exact=True).wait_for()
        visual_tab = page.locator('#visual-page-tabs [role="tab"][aria-selected="true"]')
        visual_tab.focus()
        visual_tab.press("ArrowRight")
        if page.evaluate("() => !document.activeElement?.matches('#visual-page-tabs [role=tab]')"):
            raise AssertionError("visual tab keyboard focus was not retained")

        for width, height in ((860, 900), (1360, 960), (1800, 1100)):
            assert_layout(page, width, height)
            if evidence_dir is not None:
                page.screenshot(path=evidence_dir / f"visual-{width}.png", full_page=True)

        page.emulate_media(reduced_motion="reduce")
        duration = page.locator(".visual-series-item").first.evaluate(
            "node => Math.max(...getComputedStyle(node).transitionDuration.split(',').map(value => parseFloat(value) || 0))"
        )
        if duration > 0.01:
            raise AssertionError(f"reduced-motion transition is too long: {duration}s")

        context.close()
        browser.close()

    if page_errors:
        raise AssertionError(f"browser page errors: {page_errors}")
    if console_errors:
        raise AssertionError(f"browser console errors: {console_errors}")
    if evidence_dir is not None:
        (evidence_dir / "report.json").write_text(
            json.dumps(
                {
                    "groups": EXPECTED_GROUPS,
                    "legacy_ids": sorted(LEGACY_IDS),
                    "viewports": [860, 1360, 1800],
                    "focus_restore": True,
                    "reduced_motion": True,
                    "console_errors": console_errors,
                    "page_errors": page_errors,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="", help="use an already-running isolated X2RED server")
    parser.add_argument("--evidence-dir", type=Path, default=None, help="write screenshots and a JSON report")
    args = parser.parse_args()
    with managed_server(args.base_url) as base_url:
        source_id, variant_id = seed_visual_task(base_url)
        run_browser_acceptance(base_url, source_id, variant_id, args.evidence_dir)
    print("UI1 Playwright acceptance passed: navigation, handoff, focus, visual workflow, 860/1360/wide, reduced motion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
