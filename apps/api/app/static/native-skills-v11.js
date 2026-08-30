(() => {
  if (window.__x2redNativeSkillsV11) return;

  const state = {
    loading: false,
    status: null,
  };

  window.__x2redNativeSkillsV11 = state;

  const call = window.api || (async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    return response.json();
  });

  function create(tag, className = "", text = "") {
    const value = document.createElement(tag);
    if (className) value.className = className;
    if (text) value.textContent = text;
    return value;
  }

  function injectSettings() {
    const grid = document.querySelector("#settings-view .settings-grid");
    if (!grid || document.getElementById("native-skills-card")) return;
    const card = create("article", "surface settings-card native-skills-card");
    card.id = "native-skills-card";
    const heading = create("div", "panel-heading");
    const copy = create("div");
    copy.append(
      create("span", "section-kicker", "UPSTREAM NATIVE SKILLS"),
      create("h3", "", "原版 Skill 运行时"),
    );
    const refresh = create("button", "secondary-action", "刷新状态");
    refresh.type = "button";
    refresh.id = "native-skills-refresh";
    refresh.addEventListener("click", () => { void loadStatus(); });
    heading.append(copy, refresh);
    const list = create("div", "native-skill-list");
    list.id = "native-skill-list";
    list.appendChild(create("div", "helper-copy", "正在检查上游组件…"));
    const note = create(
      "div",
      "native-license-note",
      "Guizang 以独立、固定 commit 的 AGPL-3.0 上游 checkout 运行，保留 LICENSE、Git 历史和源码入口；Minimal Zine 以 MIT 上游 checkout 运行。",
    );
    card.append(heading, list, note);
    grid.appendChild(card);
    void loadStatus();
  }

  function skillRow(skill) {
    const okay = Boolean(skill.installed && skill.pinned_commit_match);
    const row = create("article", "native-skill-row");
    const copy = create("div");
    copy.append(create("h4", "", String(skill.name || "原版 Skill")), create("p", "", String(skill.description || "")));
    const meta = create("div", "native-skill-meta");
    meta.append(
      create("span", "", String(skill.license || "")),
      create("span", "", String(skill.commit || "").slice(0, 12)),
    );
    const stateLabel = skill.name === "guizang-social-card-skill" && !skill.validator_ready
      ? "缺少 validator"
      : okay
        ? "固定版本已安装"
        : "尚未安装";
    meta.appendChild(create("span", `native-skill-state ${okay && (skill.name !== "guizang-social-card-skill" || skill.validator_ready) ? "ok" : "warn"}`, stateLabel));
    if (skill.source_offer) {
      const link = create("a", "", "查看上游源码 ↗");
      link.href = String(skill.source_offer);
      link.target = "_blank";
      link.rel = "noreferrer";
      meta.appendChild(link);
    }
    copy.appendChild(meta);
    const install = create(
      "button",
      "native-install",
      okay && (skill.name !== "guizang-social-card-skill" || skill.validator_ready) ? "重新安装" : "安装原版",
    );
    install.type = "button";
    install.addEventListener("click", () => { void installSkill(String(skill.name || ""), install); });
    row.append(copy, install);
    return row;
  }

  function imageRow(image) {
    const row = create("article", "native-skill-row");
    const copy = create("div");
    copy.append(create("h4", "", "Minimal Zine 图片模型"));
    const message = image.configured
      ? `已配置 ${image.model || "图片模型"}，生成尺寸 ${image.size || "默认尺寸"}。`
      : "未配置。设置 X2RED_IMAGE_MODEL、X2RED_IMAGE_BASE_URL、X2RED_IMAGE_API_KEY 后才会调用真实图片模型；不会自动退回占位图。";
    copy.appendChild(create("p", "", message));
    row.append(copy, create("span", `native-skill-state ${image.configured ? "ok" : "warn"}`, image.configured ? "可生图" : "Prompt-only"));
    return row;
  }

  function renderStatus() {
    const list = document.getElementById("native-skill-list");
    if (!list || !state.status) return;
    list.replaceChildren();
    (Array.isArray(state.status.skills) ? state.status.skills : []).forEach((skill) => {
      list.appendChild(skillRow(skill));
    });
    list.appendChild(imageRow(state.status.image_generation || {}));
  }

  async function loadStatus() {
    try {
      state.status = await call("/api/native-skills");
      renderStatus();
    } catch (error) {
      const list = document.getElementById("native-skill-list");
      if (list) {
        list.replaceChildren(create("div", "inline-status error", error.message || String(error)));
      }
    }
  }

  async function installSkill(name, control) {
    if (!name || state.loading) return;
    state.loading = true;
    control.disabled = true;
    const label = control.textContent;
    control.textContent = "安装中…";
    try {
      await call("/api/native-skills/install", {
        method: "POST",
        body: JSON.stringify({ name, install_runtime: true }),
      });
      await loadStatus();
    } catch (error) {
      window.alert(error.message || String(error));
    } finally {
      state.loading = false;
      control.disabled = false;
      if (control.isConnected && control.textContent === "安装中…") control.textContent = label;
    }
  }

  function boot() {
    injectSettings();
    const observer = new MutationObserver(injectSettings);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
