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


def test_completed_project_has_direct_workbench_actions() -> None:
    script = (STATIC / "studio-ux-v072.js").read_text(encoding="utf-8")
    assert "查看完成文章" in script
    assert "去制图" in script
    assert 'openCompletedDraft(project, "draft-pane")' in script
    assert 'openCompletedDraft(project, "cards-pane")' in script
    assert "multi Agent" not in script


def test_current_action_bar_is_sticky_and_legacy_controls_are_hidden() -> None:
    stylesheet = (STATIC / "studio-ux-v072.css").read_text(encoding="utf-8")
    assert ".writing-action-dock{position:sticky;bottom:0" in stylesheet
    assert ".legacy-project-actions,.legacy-artifact-actions{display:none!important}" in stylesheet
    assert ".artifact-card.collapsed .artifact-content{display:none}" in stylesheet
