(() => {
  const state = { currentLightVariantId: "", status: null, loading: false };

  async function api(url, options = {}) {
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
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  function injectStyles() {
    if (document.getElementById("native-skills-v11-style")) return;
    const style = document.createElement("style");
    style.id = "native-skills-v11-style";
    style.textContent = `
.native-skills-card{grid-column:1/-1}.native-skill-list{display:grid;gap:12px;margin-top:16px}.native-skill-row{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:14px;border:1px solid #e1e5ed;border-radius:14px;background:#fafbfe}.native-skill-row h4{margin:0 0 5px;font-size:13px}.native-skill-row p{margin:0;color:#717a8b;font-size:10px;line-height:1.55}.native-skill-meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px;color:#8a92a1;font-size:9px}.native-skill-state{font-weight:850}.native-skill-state.ok{color:#1e7650}.native-skill-state.warn{color:#a15c13}.native-install{min-height:36px;padding:0 12px;border:1px solid #dce1eb;border-radius:10px;background:#fff;color:#364155;font-size:10px;font-weight:820;cursor:pointer}.native-install:disabled{opacity:.5}.native-license-note{margin-top:14px;padding:12px;border-radius:12px;background:#f4f6fa;color:#656f81;font-size:10px;line-height:1.65}.native-zine-action{border-color:#252a38!important;background:#252a38!important;color:#fff!important}.native-zine-config{margin-top:8px;color:#7c8493;font-size:9px;line-height:1.45}
`;
    document.head.appendChild(style);
  }

  function injectCardOptions() {
    const select = document.getElementById("card-visual-style");
    if (!select || select.querySelector('option[value="guizang_editorial"]')) return;
    select.add(new Option("Guizang Editorial · 原生完整链", "guizang_editorial"), 1);
    select.add(new Option("Guizang Swiss · 原生完整链", "guizang_swiss"), 2);
  }

  function injectSettings() {
    const grid = document.querySelector("#settings-view .settings-grid");
    if (!grid || document.getElementById("native-skills-card")) return;
    const card = document.createElement("article");
    card.id = "native-skills-card";
    card.className = "surface settings-card native-skills-card";
    card.innerHTML = `
      <div class="panel-heading"><div><span class="section-kicker">UPSTREAM NATIVE SKILLS</span><h3>原版 Skill 运行时</h3></div><button id="native-skills-refresh" class="secondary-action" type="button">刷新状态</button></div>
      <div id="native-skill-list" class="native-skill-list"><div class="helper-copy">正在检查上游组件……</div></div>
      <div class="native-license-note">Guizang 以独立、固定 commit 的 AGPL-3.0 上游 checkout 运行，保留 LICENSE、Git 历史和源码入口；Minimal Zine 以 MIT 上游 checkout 运行。X2RED 不再复制一小部分 CSS 冒充原版能力。</div>`;
    grid.appendChild(card);
    document.getElementById("native-skills-refresh")?.addEventListener("click", loadStatus);
    loadStatus();
  }

  function renderStatus() {
    const list = document.getElementById("native-skill-list");
    if (!list || !state.status) return;
    const image = state.status.image_generation || {};
    list.innerHTML = (state.status.skills || []).map((skill) => {
      const okay = skill.installed && skill.pinned_commit_match;
      const runtime = skill.name === "guizang-social-card-skill" ? ` · validator ${skill.validator_ready ? "就绪" : "未安装"}` : "";
      return `<div class="native-skill-row">
        <div><h4>${escapeHtml(skill.name)}</h4><p>${escapeHtml(skill.description)}</p><div class="native-skill-meta"><span>${escapeHtml(skill.license)}</span><span>${escapeHtml(String(skill.commit).slice(0, 12))}</span><span class="native-skill-state ${okay ? "ok" : "warn"}">${okay ? "固定版本已安装" : "尚未安装"}${runtime}</span><a href="${escapeHtml(skill.source_offer)}" target="_blank" rel="noreferrer">查看上游源码 ↗</a></div></div>
        <button class="native-install" type="button" data-skill="${escapeHtml(skill.name)}">${okay && (skill.name !== "guizang-social-card-skill" || skill.validator_ready) ? "重新安装" : "安装原版"}</button>
      </div>`;
    }).join("") + `<div class="native-skill-row"><div><h4>Minimal Zine 图片模型</h4><p>${image.configured ? `已配置 ${escapeHtml(image.model)}，生成尺寸 ${escapeHtml(image.size)}` : "未配置。设置 X2RED_IMAGE_MODEL、X2RED_IMAGE_BASE_URL、X2RED_IMAGE_API_KEY 后才会调用真实图片模型；不再自动退回占位图。"}</p></div><span class="native-skill-state ${image.configured ? "ok" : "warn"}">${image.configured ? "可生图" : "Prompt-only"}</span></div>`;
    list.querySelectorAll(".native-install").forEach((button) => button.addEventListener("click", () => installSkill(button.dataset.skill, button)));
  }

  async function loadStatus() {
    try { state.status = await api("/api/native-skills"); renderStatus(); injectZineAction(); }
    catch (error) {
      const list = document.getElementById("native-skill-list");
      if (list) list.innerHTML = `<div class="inline-status error">${escapeHtml(error.message)}</div>`;
    }
  }

  async function installSkill(name, button) {
    if (!name || state.loading) return;
    state.loading = true; button.disabled = true; button.textContent = "安装中…";
    try {
      await api("/api/native-skills/install", { method: "POST", body: JSON.stringify({ name, install_runtime: true }) });
      await loadStatus();
    } catch (error) { alert(error.message); }
    finally { state.loading = false; button.disabled = false; }
  }

  function captureVariant(payload) {
    if (!payload || typeof payload !== "object") return;
    const candidates = Array.isArray(payload) ? payload : [payload, payload.variant].filter(Boolean);
    candidates.forEach((item) => {
      if (item && item.format === "light_series" && item.platform === "wechat" && item.id) state.currentLightVariantId = item.id;
      if (item && item.variant_id && String(item.variant_id).startsWith("variant_")) state.currentLightVariantId = item.variant_id;
    });
    injectZineAction();
  }

  function observeFetch() {
    if (window.__x2redNativeFetchObserved) return;
    window.__x2redNativeFetchObserved = true;
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await original(...args);
      try {
        const url = new URL(typeof args[0] === "string" ? args[0] : args[0]?.url || "", location.href);
        if (url.pathname.startsWith("/api/platforms/") || url.pathname.startsWith("/api/native-skills/")) {
          response.clone().json().then(captureVariant).catch(() => {});
        }
      } catch {}
      return response;
    };
  }

  function injectZineAction() {
    const actions = document.querySelector(".light-preview-actions");
    if (!actions || document.getElementById("native-zine-render")) return;
    const button = document.createElement("button");
    button.id = "native-zine-render";
    button.className = "native-zine-action";
    button.type = "button";
    button.textContent = "用原版 Minimal Zine 生图";
    button.addEventListener("click", renderMinimalZine);
    actions.appendChild(button);
    const note = document.createElement("div");
    note.id = "native-zine-config";
    note.className = "native-zine-config";
    note.textContent = state.status?.image_generation?.configured ? "完整上游 Prompt Compiler + 已配置图片模型" : "需要先在“模型与 Skill”配置图片模型";
    actions.parentElement?.insertBefore(note, actions.nextSibling);
  }

  async function renderMinimalZine() {
    if (!state.currentLightVariantId) { alert("请先选择或生成一个轻内容版本。刷新页面后重新点选当前版本也可以。"); return; }
    if (!state.status?.image_generation?.configured) { alert("图片模型尚未配置。请到“模型与 Skill”查看所需环境变量。"); return; }
    const button = document.getElementById("native-zine-render");
    button.disabled = true; button.textContent = "原版 Skill 生图中…";
    try {
      const result = await api(`/api/native-skills/minimal-zine/variants/${state.currentLightVariantId}/render`, { method: "POST", body: JSON.stringify({ regenerate: true }) });
      captureVariant(result);
      const gallery = document.querySelector(".light-gallery");
      if (gallery) gallery.innerHTML = (result.pages || []).map((page) => `<figure class="light-poster"><img src="/api/platforms/variants/${encodeURIComponent(result.variant_id)}/files/poster_${String(page.page).padStart(2, "0")}?t=${Date.now()}" alt="Minimal Zine poster"><figcaption><span>原版 Minimal Zine</span><span>${String(page.page).padStart(2, "0")}</span></figcaption></figure>`).join("");
      button.textContent = "已用原版 Skill 生图";
    } catch (error) { alert(error.message); button.textContent = "重试原版 Minimal Zine"; }
    finally { button.disabled = false; }
  }

  function boot() {
    injectStyles(); observeFetch(); injectCardOptions(); injectSettings(); injectZineAction();
    const observer = new MutationObserver(() => { injectCardOptions(); injectSettings(); injectZineAction(); });
    observer.observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();