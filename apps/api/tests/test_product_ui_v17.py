from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "apps" / "api" / "app" / "static"


def test_product_ui_v17_is_the_final_visual_layer() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    main_py = (ROOT / "apps" / "api" / "app" / "main.py").read_text(encoding="utf-8")

    assert 'id="product-ui-v17-styles"' in html
    assert html.index("product-shell-v15.css") < html.index("product-ui-v17.css")
    assert html.index("light-content-v15.css") < html.index("product-ui-v17.css")
    assert html.index("pool-memory-v16.css") < html.index("product-ui-v17.css")
    assert html.count('src="/static/product-ui-v17.js"') == 1
    assert main_py.count('src="/static/product-ui-v17.js"') == 0
    assert html.index('src="/static/studio-ux-v072.js"') < html.index(
        'src="/static/product-ui-v17.js"'
    )


def test_product_ui_v17_uses_one_warm_token_system_without_gradients() -> None:
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")

    for token in (
        "--ui-bg: #f7f6f2",
        "--ui-sidebar: #f0eee7",
        "--ui-surface: #fffefb",
        "--ui-text: #2b2926",
        "--ui-border: #dedad2",
        "--ui-accent: #b65d3c",
        "--ui-accent-hover: #9f4b2d",
    ):
        assert token in stylesheet
    assert "linear-gradient" not in stylesheet
    assert "radial-gradient" not in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "@media (max-width: 860px)" in stylesheet
    assert "@media (max-width: 420px)" in stylesheet


def test_product_ui_v17_preserves_the_core_workspace_with_collapsible_regions() -> None:
    script = (STATIC / "product-ui-v17.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")

    for region in ("source", "signals", "materials", "corpus", "writing", "wechat", "memory", "style"):
        assert f'key: "{region}"' in script
    assert "setRegionCollapsed(region, true, true)" in script
    assert "shouldAutoCollapseRegion" in script
    assert 'key === "wechat"' in script
    assert 'classList.contains("is-wechat-preflight")' in script
    assert ".ui-region-collapsible.is-collapsed" in stylesheet
    assert "grid-template-columns: 64px minmax(0, 1fr)" in stylesheet
    assert "height: calc(100dvh - 94px)" in stylesheet
    assert "overscroll-behavior: contain" in stylesheet


def test_global_sidebar_is_viewport_fixed_scrollable_and_reopenable() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "product-ui-v17.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")

    sidebar_rule = stylesheet.split(".app-sidebar {", 1)[1].split("}", 1)[0]
    assert "position: fixed" in sidebar_rule
    assert "height: 100dvh" in sidebar_rule
    assert "overflow: hidden" in sidebar_rule
    assert "flex: 1 1 auto" in stylesheet
    assert "scrollbar-gutter: stable" in stylesheet
    assert ".app-shell.is-sidebar-collapsed .sidebar-toggle" in stylesheet
    assert "display: inline-grid" in stylesheet
    assert 'desktopToggle.title = expanded ? "收起主导航" : "展开主导航"' in script
    assert 'if (opening) shell.classList.remove("is-sidebar-collapsed")' in script
    assert 'id="app-sidebar"' in html
    assert 'id="sidebar-toggle"' in html
    assert 'aria-label="收起主导航"' in html
    assert 'desktopToggle.dataset.uiBound = "true"' in script
    assert '(min-width: 861px) and (max-width: 1360px)' in script


def test_xhs_reader_prioritizes_content_and_moves_judgment_into_a_drawer() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "product-ui-v17.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")

    assert 'id="source-inspector-toggle"' in html
    assert 'id="source-inspector"' in html
    assert 'role="dialog"' in html
    assert 'id="source-inspector-backdrop"' in html
    assert "function setSourceInspectorOpen" in script
    assert "function ensureSourceInspector" in script
    assert 'event.key !== "Tab"' in script
    assert 'key === "source"' in script
    assert "active-workbench" in script
    assert ".source-reader-grid" in stylesheet
    assert "grid-template-columns: minmax(0, 1fr)" in stylesheet
    assert ".source-side-stack[hidden]" in stylesheet
    assert "body.source-inspector-open .app-main" in stylesheet


def test_xhs_source_rail_has_unambiguous_types_and_workbench_archive_actions() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    app_script = (STATIC / "app.js").read_text(encoding="utf-8")
    shell_script = (STATIC / "product-shell-v15.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")

    assert "这里的归档只影响小红书工作台" in html
    assert "归档此来源" in html
    assert 'id="source-reader-kicker"' in html
    assert 'id="source-reader-title"' in html
    assert 'workbench: "xhs"' in app_script
    assert "/workbenches/xhs/${path}" in app_script
    assert 'corpus_batch: "冻结批次"' in app_script
    assert '["CORPUS BATCH READER", "冻结批次与来源"]' in app_script
    assert 'origin.textContent = "𝕏"' in app_script
    assert 'origin.textContent = sourcePlatformLabel(item)' in app_script
    assert '"X SOURCE"' not in app_script
    assert 'field.id = "source-platform-filter"' in shell_script
    assert 'className = "source-row-archive"' in app_script
    assert "selectButton.dataset.sourceId = item.id" in app_script
    assert ".source-item-top" in stylesheet
    assert "grid-template-columns: 36px minmax(0, 1fr) auto 8px" in stylesheet
    assert ".source-row-archive" in stylesheet
    assert "min-height: 44px" in stylesheet


def test_product_ui_v17_mobile_navigation_and_accessibility_contracts() -> None:
    script = (STATIC / "product-ui-v17.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")

    assert 'skip.href = "#main-content"' in script
    assert 'main.inert = true' in script
    assert 'main.inert = false' in script
    assert 'event.key === "Escape"' in script
    assert 'button.setAttribute("aria-current", "page")' in script
    assert 'node.setAttribute("aria-live", "polite")' in script
    assert "button:focus-visible" in stylesheet
    assert "min-width: 44px" in stylesheet
    assert "min-height: 44px" in stylesheet
    assert "document.querySelectorAll(\".url-field > span\")" in script
    assert 'holder.dataset.uiIconReady = "true"' in script


def test_wechat_pipeline_uses_progressive_disclosure_and_stage_actions() -> None:
    platform_script = (STATIC / "platform-v08.js").read_text(encoding="utf-8")
    studio_script = (STATIC / "studio-v07.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")
    page_rules = (
        ROOT / "design-system" / "x2red" / "pages" / "wechat-longform.md"
    ).read_text(encoding="utf-8")

    assert 'pipelineInspectionKey: ""' in platform_script
    assert 'button.setAttribute("aria-controls", "wechat-pipeline-guidance")' in platform_script
    assert "renderPipelineDetail(status, stage)" in platform_script
    assert "wechat-pipeline-detail-grid" in platform_script
    assert 'el("details", "wechat-pipeline-facts")' in platform_script
    assert 'window.matchMedia("(max-width: 860px)")' in platform_script
    assert 'id="wechat-pipeline-meter"' in platform_script
    assert 'id="wechat-pipeline-context"' in platform_script
    assert 'id="wechat-start-new-article"' in platform_script
    assert "已选成品 · 公众号 v" in platform_script
    assert "正在查看阶段" in platform_script
    assert "所有历史版本均已保留" in platform_script
    assert "function startNewArticle()" in platform_script
    assert "platformState.newArticleSession = true" in platform_script
    assert 'closest(".ui-region-collapsible.is-collapsed")' in platform_script
    assert 'id="wechat-create-actions"' in platform_script
    assert '<details id="wechat-paste-source-panel"' in platform_script
    assert "可选 · 按需展开" in platform_script
    assert "window.openX2redWritingProject" in studio_script
    assert "打开现有深度写作" in platform_script
    assert "button.append(top, title, io, skill, optimize)" not in platform_script

    assert ".wechat-pipeline-steps" in stylesheet
    assert "list-style: none" in stylesheet
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in stylesheet
    assert "min-height: 84px" in stylesheet
    assert ".wechat-pipeline-facts-summary" in stylesheet
    assert ".wechat-pipeline-context" in stylesheet
    assert ".wechat-start-new-article" in stylesheet
    assert ".wechat-paste-panel > summary" in stylesheet
    assert "#wechat-view.is-wechat-preflight #wechat-create-form" in stylesheet
    assert "点击阶段先查看详情" in page_rules
    assert "隐藏无意义的空编辑器和空预览" in page_rules


def test_wechat_light_mode_is_isolated_and_supports_manual_chatgpt_web_handoff() -> None:
    platform_script = (STATIC / "platform-v08.js").read_text(encoding="utf-8")
    light_script = (STATIC / "light-content-v15.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "product-ui-v17.css").read_text(encoding="utf-8")
    native_api = (ROOT / "apps" / "api" / "app" / "api" / "native_skills.py").read_text(
        encoding="utf-8"
    )

    assert 'id="wechat-view-description"' in platform_script
    assert 'longPipeline.hidden = mode === "light"' in light_script
    assert 'longLayout.hidden = mode === "light"' in light_script
    assert 'view?.classList.toggle("is-wechat-light-mode", mode === "light")' in light_script
    assert "#wechat-view.is-wechat-light-mode #wechat-production-pipeline" in stylesheet
    assert 'open.href = "https://chatgpt.com/images"' in light_script
    assert "1 · 生成并显示本页 Prompt" in light_script
    assert "2 · 复制完整 Prompt" in light_script
    assert "本页完整 Prompt" in light_script
    assert "这一步不会调用图片模型" in light_script
    assert "|| state.storyboardDirty" in light_script
    assert "旧 Prompt 已过期" in light_script
    assert "当前本地服务仍是旧进程" in light_script
    assert ".light-web-prompt-text" in (STATIC / "light-content-v15.css").read_text(
        encoding="utf-8"
    )
    assert "上传下载图" in light_script
    assert "/web-handoff" in native_api
    assert "/external-anchor" in native_api


def test_aggregate_stylesheet_hashes_the_actual_modular_css() -> None:
    main_py = (ROOT / "apps" / "api" / "app" / "main.py").read_text(
        encoding="utf-8"
    )

    assert "STYLESHEET_FILES = (" in main_py
    assert '"platform-v08.css",' in main_py
    assert "def build_stylesheet() -> str:" in main_py
    assert 'if name == "styles.css"' in main_py
    assert "digest = static_asset_digest" in main_py
    assert "build_stylesheet()," in main_py
    assert 'headers={"Cache-Control": "no-cache"}' in main_py
