import { apiClient } from "./api-client.js?v=18";
import { createCreativeStore } from "./creative-store.js?v=18";
import { initPublishView } from "./publish-view.js?v=18";
import { initVisualView } from "./visual-view.js?v=18";
import { initWritingView } from "./writing-view.js?v=18";

const workflow = {
  version: 18,
  store: createCreativeStore(),
  api: apiClient,
  ready: false,
};

window.__x2redCreativeWorkflowV18 = workflow;

async function boot() {
  if (workflow.ready) return;
  workflow.ready = true;
  try {
    await Promise.all([
      initWritingView(workflow),
      initVisualView(workflow),
    ]);
    initPublishView(workflow);
    document.dispatchEvent(new CustomEvent("x2red:creative-workflow-ready", {
      detail: { version: workflow.version },
    }));
  } catch (error) {
    workflow.ready = false;
    const target = document.querySelector(".topbar-status");
    if (target) {
      const status = document.createElement("span");
      status.className = "status-chip error";
      status.setAttribute("role", "alert");
      status.textContent = `统一创作流程加载失败：${error.message || error}`;
      target.appendChild(status);
    }
    throw error;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { void boot(); }, { once: true });
} else {
  void boot();
}
