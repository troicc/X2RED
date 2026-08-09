from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "apps" / "api" / "app" / "static"


def test_writing_studio_loads_continuous_interaction_assets() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '/static/studio-ux-v072.css' in html
    assert '/static/studio-ux-v072.js' in html
    assert html.index('/static/app.js') < html.index('/static/studio-ux-v072.js')


def test_writing_studio_confirmation_advances_without_second_click() -> None:
    script = (STATIC / "studio-ux-v072.js").read_text(encoding="utf-8")
    assert "确认并自动继续" in script
    assert "approveAndAdvance" in script
    assert 'body: JSON.stringify({ continuous: true })' in script
    assert "refreshSelectedProject" in script


def test_completed_project_hands_exact_output_to_wechat_pipeline() -> None:
    script = (STATIC / "studio-ux-v072.js").read_text(encoding="utf-8")
    assert "进入公众号成稿阶段" in script
    assert "打开公众号 v" in script
    assert "查看本页终稿" in script
    assert "window.openX2redWechatForProject(project)" in script
    assert "查看完成文章" not in script
    assert "去制图" not in script


def test_deep_writing_trace_names_inputs_outputs_routes_and_optimization_points() -> None:
    script = (STATIC / "studio-ux-v072.js").read_text(encoding="utf-8")
    assert "深度写作内部流程" in script
    assert "读取：${guide.reads}" in script
    assert "输出：${guide.writes}" in script
    assert "优化：${guide.optimize}" in script
    assert "模型：${labels.join" in script
    assert "Skill：${guide.skill}" in script
    assert "1800—4500 字、3—6 个 H2" in script


def test_current_action_bar_is_sticky_and_legacy_controls_are_hidden() -> None:
    stylesheet = (STATIC / "studio-ux-v072.css").read_text(encoding="utf-8")
    assert ".writing-action-dock{position:sticky;bottom:0" in stylesheet
    assert ".legacy-project-actions,.legacy-artifact-actions{display:none!important}" in stylesheet
    assert ".artifact-card.collapsed .artifact-content{display:none}" in stylesheet
    assert ".writing-stage-list" in stylesheet
    assert ".artifact-explainer" in stylesheet
    assert ":focus-visible" in stylesheet
