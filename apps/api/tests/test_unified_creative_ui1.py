from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "apps" / "api" / "app" / "static"


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_ui1_extracts_small_es_modules_and_keeps_product_ui_as_final_layer() -> None:
    module_names = (
        "api-client.js",
        "creative-store.js",
        "writing-view.js",
        "visual-view.js",
        "candidate-view.js",
        "prompt-view.js",
        "publish-view.js",
    )
    for name in module_names:
        path = STATIC / name
        assert path.is_file()
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000

    entry = source("creative-workflow-v18.js")
    for name in ("creative-store.js", "writing-view.js", "visual-view.js", "publish-view.js"):
        assert f'from "./{name}?v=18"' in entry
    assert len(entry.splitlines()) < 1000

    html = source("index.html")
    assert 'href="/static/creative-workflow-v18.css"' in html
    assert html.index("creative-workflow-v18.css") < html.index("product-ui-v17.css")
    assert 'type="module" src="/static/creative-workflow-v18.js"' in html


def test_ui1_navigation_has_six_groups_without_losing_existing_entries() -> None:
    shell = source("product-shell-v15.js")
    assert (
        'const GROUP_ORDER = ["collect", "create", "visual", "publish", "assets", '
        '"settings"]'
    ) in shell
    for label in ("收集", "创作", "视觉", "发布", "资产与偏好", "设置"):
        assert f'layer: "{label}"' in shell
    for view in (
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
    ):
        assert f'view: "{view}"' in shell
    assert 'new CustomEvent("x2red:view-changed"' in shell
    assert "shellState.viewFocus.set(previousView, focused)" in shell


def test_ui1_wizard_autosaves_and_hands_off_to_legacy_workbenches() -> None:
    writing = source("writing-view.js")
    store = source("creative-store.js")
    platform = source("platform-v08.js")
    studio = source("studio-v07.js")
    light = source("light-content-v15.js")

    for label in (
        "选择材料",
        "文章类型",
        "发布平台",
        "读者与承诺",
        "写作模式",
        "视觉路线",
    ):
        assert label in writing
    assert 'api.get("/api/writing/material-options?limit=500")' in writing
    assert 'role="tablist"' in writing
    assert '["ArrowLeft", "ArrowRight"]' in writing
    assert "x2red.creative-task.v18" in store
    assert 'new CustomEvent("x2red:creative-task-handoff"' in writing
    assert 'document.addEventListener("x2red:creative-task-handoff"' in platform
    assert 'document.addEventListener("x2red:creative-task-handoff"' in studio
    assert 'document.addEventListener("x2red:open-wechat-light"' in light

    # One-version compatibility: existing controller IDs stay intact and are seeded,
    # rather than being replaced by a parallel generation implementation.
    for legacy_id in ("wechat-source", "wechat-mode", "wechat-illustrations"):
        assert f'getElementById("{legacy_id}")' in platform
    for legacy_id in ("writing-mode", "writing-reader", "writing-promise"):
        assert f'getElementById("{legacy_id}")' in studio


def test_ui1_visual_workspace_consumes_real_prompt_and_candidate_contracts() -> None:
    visual = source("visual-view.js")
    prompt = source("prompt-view.js")
    candidate = source("candidate-view.js")

    for label in (
        "系列概览",
        "Prompt 溯源与差异",
        "批量上传",
        "Contact Sheet 与候选状态",
    ):
        assert label in visual or label in prompt or label in candidate
    assert "/web-handoff" in visual
    assert "/external-anchor?page=" in visual
    assert "/visuals/${encodeURIComponent(slotId)}" in visual
    assert "/candidates/${encodeURIComponent(candidate.page)}/review" in visual
    assert "/candidates/${encodeURIComponent(candidate.page)}/select" in visual
    assert "/candidates/${encodeURIComponent(candidate.page)}/repair" in visual
    assert "promptDuplicateWarnings" in prompt
    assert "prompt_diff" in prompt
    assert "duplicateImageWarnings" in candidate
    assert "overall_score" in candidate
    assert "contact_sheet_key" in candidate
    assert "未通过视觉审稿的候选" not in visual
    assert "最终发布仍需人工事实与版权复核" in visual


def test_ui1_responsive_accessibility_and_playwright_gate_are_explicit() -> None:
    css = source("creative-workflow-v18.css")
    playwright_gate = (ROOT / "scripts" / "ui1_playwright_e2e.py").read_text(
        encoding="utf-8"
    )
    assert "@media (max-width: 1360px)" in css
    assert "@media (max-width: 860px)" in css
    assert "@media (min-width: 1500px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "linear-gradient" not in css
    assert "radial-gradient" not in css
    assert "min-height: 44px" in css
    assert 'meter.setAttribute("role", "meter")' in source("candidate-view.js")
    assert "aria-valuenow" in source("candidate-view.js")
    assert "(860, 900), (1360, 960), (1800, 1100)" in playwright_gate
    assert 'page.emulate_media(reduced_motion="reduce")' in playwright_gate
    assert "document.activeElement?.id === 'creative-task-handoff'" in playwright_gate
    assert "LEGACY_IDS" in playwright_gate
