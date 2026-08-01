(() => {
  const apiCall = window.api || (async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let message = `请求失败：${response.status}`;
      try { message = (await response.json()).detail || message; } catch {}
      throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
  });

  let enhancing = false;
  let scheduled = 0;

  function injectStyles() {
    if (document.getElementById("signal-to-studio-v10-style")) return;
    const style = document.createElement("style");
    style.id = "signal-to-studio-v10-style";
    style.textContent = `
.signal-l2-panel{margin-top:14px;padding:14px;border:1px solid #d9def0;border-radius:14px;background:#f7f8ff}.signal-l2-panel h4{margin:0 0 7px;font-size:14px}.signal-l2-panel p{margin:0;color:#586174;font-size:13px;line-height:1.65}.signal-l2-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:12px}.signal-l2-block{padding:10px 11px;border-radius:10px;background:#fff}.signal-l2-block strong{display:block;margin-bottom:5px;color:#40506b;font-size:11px}.signal-l2-block span{color:#333c4c;font-size:12px;line-height:1.55}.signal-l2-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px}.signal-l2-state{color:#687386;font-size:11px}.signal-promote{border:0;border-radius:10px;padding:10px 13px;background:#315efb;color:#fff;font-weight:800;cursor:pointer}.signal-promote:disabled{opacity:.5;cursor:not-allowed}.signal-analysis-running{margin-top:11px;padding:10px 12px;border-radius:10px;background:#fff6df;color:#8a5b00;font-size:12px}.signal-analysis-empty{margin-top:11px;color:#7b8495;font-size:12px}@media(max-width:760px){.signal-l2-grid{grid-template-columns:1fr}.signal-l2-actions{align-items:stretch;flex-direction:column}.signal-promote{width:100%}}
`;
    document.head.appendChild(style);
  }

  function listText(value) {
    if (!Array.isArray(value)) return [];
    return value.map((item) => {
      if (item && typeof item === "object") {
        return String(item.angle || item.name || item.description || item.trigger || item.statement || "").trim();
      }
      return String(item || "").trim();
    }).filter(Boolean);
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
  }

  async function enhanceSignalCards() {
    if (enhancing) return;
    const box = document.getElementById("signal-feed");
    if (!box || !box.children.length) return;
    enhancing = true;
    try {
      const grade = document.getElementById("signal-grade")?.value || "";
      const feed = await apiCall(`/api/signals/feed?grade=${encodeURIComponent(grade)}`);
      const cards = [...box.querySelectorAll(".signal-item")];
      cards.forEach((card, index) => {
        const item = feed[index];
        if (!item) return;
        card.dataset.candidateId = item.candidate_id;
        card.querySelector(".signal-l2-panel")?.remove();
        card.querySelector(".signal-analysis-empty")?.remove();
        if (!item.l2_analysis) {
          const empty = document.createElement("div");
          empty.className = "signal-analysis-empty";
          empty.textContent = "深度拆解完成后，会在这里显示钩子、受众触发点、写作角度与事实风险，并可直接加入创作台。";
          card.appendChild(empty);
          return;
        }
        card.appendChild(renderL2(item));
      });
    } catch {
      // Keep the original Signal UI usable when enhancement fails.
    } finally {
      enhancing = false;
    }
  }

  function renderL2(item) {
    const l2 = item.l2_analysis || {};
    const panel = document.createElement("section");
    panel.className = "signal-l2-panel";
    const hook = String(l2.hook || "已完成深度拆解");
    const triggers = listText(l2.audience_triggers);
    const angles = listText(l2.writing_angles);
    const risks = listText(l2.fact_risks);
    const replicable = listText(l2.replicable_elements);
    panel.innerHTML = `
      <h4>深度拆解结果</h4>
      <p>${escapeHtml(hook)}</p>
      <div class="signal-l2-grid">
        <div class="signal-l2-block"><strong>受众触发点</strong><span>${escapeHtml(triggers.slice(0, 3).join("；") || "未识别")}</span></div>
        <div class="signal-l2-block"><strong>可写角度</strong><span>${escapeHtml(angles.slice(0, 3).join("；") || "需要人工补充")}</span></div>
        <div class="signal-l2-block"><strong>可复用表达</strong><span>${escapeHtml(replicable.slice(0, 3).join("；") || "暂无")}</span></div>
        <div class="signal-l2-block"><strong>事实风险</strong><span>${escapeHtml(risks.slice(0, 3).join("；") || "仍需人工核对来源")}</span></div>
      </div>`;
    const actions = document.createElement("div");
    actions.className = "signal-l2-actions";
    const state = document.createElement("span");
    state.className = "signal-l2-state";
    state.textContent = item.promoted_source_id ? "已进入来源箱，可继续建立新项目" : "尚未进入创作台";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "signal-promote";
    button.textContent = item.promoted_source_id ? "再建一个创作项目" : "加入创作台";
    button.addEventListener("click", () => promote(item, button, state));
    actions.append(state, button);
    panel.appendChild(actions);
    return panel;
  }

  async function promote(item, button, state) {
    button.disabled = true;
    state.textContent = "正在把来源、L2 结论和写作角度送入创作台…";
    try {
      const result = await apiCall(`/api/signals/candidates/${encodeURIComponent(item.candidate_id)}/promote`, {
        method: "POST",
        body: JSON.stringify({ mode: "studio" }),
      });
      state.textContent = "已建立写作项目，正在打开创作台。";
      window.setView?.("writing-view");
      await new Promise((resolve) => setTimeout(resolve, 900));
      document.getElementById("refresh-writing")?.click();
      await new Promise((resolve) => setTimeout(resolve, 900));
      const projects = await apiCall("/api/writing/projects?limit=100");
      const project = projects.find((value) => value.id === result.project_id);
      const buttons = [...document.querySelectorAll(".writing-project-item")];
      const target = project
        ? buttons.find((value) => value.textContent.includes(project.promise || project.main_thesis || ""))
        : null;
      (target || buttons[0])?.click();
    } catch (error) {
      state.textContent = error.message || String(error);
      button.disabled = false;
    }
  }

  function scheduleEnhance(delay = 120) {
    window.clearTimeout(scheduled);
    scheduled = window.setTimeout(() => enhanceSignalCards(), delay);
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("button");
    if (!button || !button.textContent.includes("深度拆解")) return;
    const card = button.closest(".signal-item");
    if (card && !card.querySelector(".signal-analysis-running")) {
      const running = document.createElement("div");
      running.className = "signal-analysis-running";
      running.textContent = "深度拆解正在运行。完成后会自动显示结果与“加入创作台”入口。";
      card.appendChild(running);
    }
    [1200, 2800, 5200, 9000, 15000].forEach((delay) => window.setTimeout(enhanceSignalCards, delay));
  }, true);

  function boot() {
    injectStyles();
    const observer = new MutationObserver(() => scheduleEnhance());
    observer.observe(document.body, { childList: true, subtree: true });
    scheduleEnhance(500);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
