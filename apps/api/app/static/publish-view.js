function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

const PLATFORM_LABELS = {
  xiaohongshu: "小红书",
  wechat_long: "公众号长文",
  wechat_light: "公众号轻内容",
};

/** Surface the current creative brief beside the human-controlled publish queue. */
export function initPublishView({ store }) {
  const view = document.getElementById("publish-view");
  const listSurface = view?.querySelector(".page-surface");
  if (!view || !listSurface || document.getElementById("publish-creative-context")) return;
  const context = element("section", "surface publish-creative-context");
  context.id = "publish-creative-context";
  context.setAttribute("aria-labelledby", "publish-creative-context-title");
  listSurface.before(context);

  function render() {
    const task = store.get();
    const copy = element("div");
    copy.append(
      element("span", "section-kicker", "CURRENT CREATIVE TASK"),
      element("h3", "", task.handoffState === "handed_off" ? "当前创作简报已交接" : "当前创作简报尚未交接"),
      element("p", "", `${PLATFORM_LABELS[task.platform] || task.platform} · ${task.materialRefs.length} 个材料 · 发布前仍需人工事实与版权复核。`),
    );
    copy.querySelector("h3").id = "publish-creative-context-title";
    const action = element("button", "secondary-action", "查看创作简报");
    action.type = "button";
    action.addEventListener("click", () => window.setView?.("creative-task-view"));
    context.replaceChildren(copy, action);
  }
  render();
  store.subscribe(render);
}
