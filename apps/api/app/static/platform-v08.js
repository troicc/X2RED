(() => {
  const platformState = {
    catalog: null,
    sources: [],
    drafts: [],
    variants: [],
    currentVariant: null,
    currentWritingProject: null,
    busy: false,
  };

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

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function dateText(value) {
    if (!value) return "";
    try { return new Date(value).toLocaleString("zh-CN", { hour12: false }); }
    catch { return String(value); }
  }

  function injectNavigation() {
    const nav = document.querySelector(".primary-nav");
    if (!nav || nav.querySelector('[data-view="wechat-view"]')) return;
    const publish = nav.querySelector('[data-view="publish-view"]');
    const button = el("button", "nav-item");
    button.dataset.view = "wechat-view";
    button.innerHTML = '<span class="nav-icon">公</span><span>公众号工作台</span>';
    nav.insertBefore(button, publish);
    button.addEventListener("click", () => window.setView?.("wechat-view"));
  }

  function injectView() {
    const stack = document.querySelector(".view-stack");
    if (!stack || document.getElementById("wechat-view")) return;
    const publish = document.getElementById("publish-view");
    const view = el("section", "app-view");
    view.id = "wechat-view";
    view.innerHTML = `
      <section class="page-intro studio-intro">
        <span class="section-kicker">ONE SOURCE · MULTI-PLATFORM</span>
        <h2>公众号工作台</h2>
        <p>复用来源、证据包和多 Agent 终稿，重新组织为公众号长文；输出内联 HTML、21:9 + 1:1 封面对和发布包。</p>
      </section>
      <section class="platform-studio-layout">
        <article class="surface platform-panel">
          <div class="panel-heading"><div><span class="section-kicker">WECHAT ARTICLE</span><h3>建立平台版本</h3></div><button id="wechat-refresh" class="secondary-action" type="button">刷新</button></div>
          <form id="wechat-create-form" class="platform-form">
            <label>来源<select id="wechat-source" required></select></label>
            <label>基础终稿<select id="wechat-draft"><option value="">直接使用来源</option></select></label>
            <div class="platform-form-row">
              <label>处理模式<select id="wechat-mode"><option value="adapt">公众号重构 · 推荐</option><option value="preserve">保留现有终稿结构</option></select></label>
              <label>排版主题<select id="wechat-theme"><option value="auto">自动选择</option></select></label>
            </div>
            <label>作者署名<input id="wechat-author" maxlength="80" placeholder="可选" /></label>
            <div class="platform-checks">
              <label class="platform-check"><input id="wechat-citations" type="checkbox" checked /><span>整理文末来源</span></label>
              <label class="platform-check"><input id="wechat-illustrations" type="checkbox" checked /><span>生成配图规划</span></label>
            </div>
            <p class="platform-helper">公众号版本是独立版本，不会覆盖小红书文案。没有 GLM 时仍可用结构化回退生成。</p>
            <button class="primary-action" type="submit">生成公众号版本</button>
          </form>
          <div class="wechat-theme-gallery" id="wechat-theme-gallery"></div>
          <div class="panel-heading" style="margin-top:22px"><div><span class="section-kicker">VERSIONS</span><h3>公众号版本</h3></div></div>
          <div id="wechat-variant-list" class="platform-variant-list"></div>
        </article>

        <article class="surface platform-panel">
          <div id="wechat-editor-empty" class="platform-empty"><div><div class="empty-orbit small">公</div><h3>先生成或选择一个公众号版本</h3><p>平台稿、排版结果和封面对都会独立保存版本。</p></div></div>
          <form id="wechat-editor" class="platform-editor" hidden>
            <div class="panel-heading"><div><span class="section-kicker">WECHAT EDITOR</span><h3>公众号文章编辑器</h3></div><span id="wechat-version-state" class="status-chip neutral"></span></div>
            <label>标题<input id="wechat-title" class="platform-title-input" maxlength="160" /></label>
            <label>封面副标题<input id="wechat-subtitle" maxlength="240" /></label>
            <label>摘要<textarea id="wechat-summary" rows="4" maxlength="1000"></textarea></label>
            <label>Markdown 正文<textarea id="wechat-body" maxlength="50000"></textarea></label>
            <label>内部标签<input id="wechat-tags" maxlength="1000" /></label>
            <div class="platform-editor-actions">
              <span id="wechat-status" class="inline-status"></span>
              <div><button id="wechat-memory" class="secondary-action" type="button">加入池子记忆</button><button id="wechat-save" class="secondary-action" type="submit">保存新版本</button><button id="wechat-render" class="primary-action" type="button">排版并生成发布包</button></div>
            </div>
          </form>
        </article>

        <article class="surface platform-preview-panel">
          <div class="platform-preview-head"><div><span class="section-kicker">WECHAT PREVIEW</span><h3>真实粘贴预览</h3></div><a id="wechat-open-preview" class="tool-button" target="_blank" rel="noreferrer" hidden>打开预览 ↗</a></div>
          <div id="wechat-preview-empty" class="platform-empty"><p>排版后在这里预览公众号正文与封面对。</p></div>
          <iframe id="wechat-preview-frame" class="platform-preview-frame" title="公众号文章预览" hidden></iframe>
          <div id="wechat-validation" class="platform-validation" hidden></div>
          <div id="wechat-cover-pair" class="platform-cover-pair" hidden><figure><img id="wechat-cover-wide" alt="公众号 21:9 主封面" /></figure><figure><img id="wechat-cover-square" alt="公众号 1:1 分享封面" /></figure></div>
          <div id="wechat-downloads" class="platform-downloads"></div>
        </article>
      </section>`;
    stack.insertBefore(view, publish);
  }

  const baseSetView = window.setView;
  window.setView = function setPlatformView(viewId) {
    baseSetView?.(viewId);
    if (viewId === "wechat-view") {
      const title = document.getElementById("page-title");
      if (title) title.textContent = "公众号工作台";
      loadWechat().catch((error) => showStatus(error.message, "error"));
    }
  };

  async function loadCatalog() {
    if (platformState.catalog) return platformState.catalog;
    platformState.catalog = await apiCall("/api/platforms/catalog");
    const themeSelect = document.getElementById("wechat-theme");
    const gallery = document.getElementById("wechat-theme-gallery");
    platformState.catalog.wechat_themes.forEach((theme) => {
      const option = document.createElement("option");
      option.value = theme.id;
      option.textContent = theme.label;
      themeSelect.appendChild(option);
      const card = el("article", "wechat-theme-chip");
      card.style.borderTop = `4px solid ${theme.palette.accent}`;
      card.innerHTML = `<strong>${theme.label}</strong><small>${theme.description}</small>`;
      card.addEventListener("click", () => { themeSelect.value = theme.id; });
      gallery.appendChild(card);
    });
    return platformState.catalog;
  }

  async function loadWechat(preferredSourceId = "") {
    await loadCatalog();
    const [sources, variants] = await Promise.all([
      apiCall("/api/sources?workspace_state=active"),
      apiCall("/api/platforms/variants?platform=wechat"),
    ]);
    platformState.sources = sources;
    platformState.variants = variants;
    fillSources(preferredSourceId);
    await loadDraftsForSource();
    renderVariants();
    if (platformState.currentVariant) {
      const fresh = variants.find((item) => item.id === platformState.currentVariant.id);
      if (fresh) selectVariant(fresh.id);
    }
  }

  function fillSources(preferredSourceId = "") {
    const select = document.getElementById("wechat-source");
    const current = preferredSourceId || select.value;
    select.replaceChildren();
    platformState.sources.forEach((source) => {
      const option = document.createElement("option");
      option.value = source.id;
      const label = source.author_handle ? `@${source.author_handle}` : source.author_name || "未知作者";
      option.textContent = `${label} · ${(source.text_original || "X Article").replace(/\s+/g, " ").slice(0, 52)}`;
      select.appendChild(option);
    });
    if (current && platformState.sources.some((item) => item.id === current)) select.value = current;
  }

  async function loadDraftsForSource(preferredDraftId = "") {
    const sourceId = document.getElementById("wechat-source")?.value;
    const select = document.getElementById("wechat-draft");
    select.replaceChildren(new Option("直接使用来源", ""));
    platformState.drafts = sourceId ? await apiCall(`/api/sources/${encodeURIComponent(sourceId)}/drafts`) : [];
    platformState.drafts.forEach((draft) => {
      const option = document.createElement("option");
      option.value = draft.id;
      option.textContent = `v${draft.version} · ${draft.title || "未命名终稿"} · ${draft.created_by}`;
      select.appendChild(option);
    });
    if (preferredDraftId && platformState.drafts.some((item) => item.id === preferredDraftId)) {
      select.value = preferredDraftId;
    } else if (platformState.drafts.length) {
      select.value = platformState.drafts[0].id;
    }
  }

  function renderVariants() {
    const box = document.getElementById("wechat-variant-list");
    box.replaceChildren();
    const sourceId = document.getElementById("wechat-source")?.value;
    const values = platformState.variants.filter((item) => !sourceId || item.source_id === sourceId);
    if (!values.length) {
      box.appendChild(el("div", "card-empty", "这个来源还没有公众号版本。"));
      return;
    }
    values.forEach((variant) => {
      const button = el("button", `platform-variant-item${platformState.currentVariant?.id === variant.id ? " active" : ""}`);
      button.type = "button";
      button.dataset.variantId = variant.id;
      button.innerHTML = `<strong>${variant.title || "未命名公众号版本"}</strong><span>v${variant.version} · ${variant.theme} · ${variant.status}</span><small>${dateText(variant.updated_at)}</small>`;
      button.addEventListener("click", () => selectVariant(variant.id));
      box.appendChild(button);
    });
  }

  function selectVariant(variantId) {
    const variant = platformState.variants.find((item) => item.id === variantId);
    if (!variant) return;
    platformState.currentVariant = variant;
    document.getElementById("wechat-editor-empty").hidden = true;
    const form = document.getElementById("wechat-editor");
    form.hidden = false;
    form.dataset.currentVariantId = variant.id;
    document.getElementById("wechat-title").value = variant.title;
    document.getElementById("wechat-subtitle").value = variant.subtitle;
    document.getElementById("wechat-summary").value = variant.summary;
    document.getElementById("wechat-body").value = variant.body_markdown;
    document.getElementById("wechat-tags").value = variant.tags;
    document.getElementById("wechat-theme").value = variant.theme || "auto";
    const state = document.getElementById("wechat-version-state");
    state.textContent = `v${variant.version} · ${variant.status}`;
    state.className = `status-chip ${variant.status === "failed" ? "error" : variant.status === "packaged" ? "ok" : "neutral"}`;
    renderVariants();
    renderOutputs(variant);
  }

  function renderOutputs(variant) {
    let files = {};
    let metadata = {};
    try { files = JSON.parse(variant.output_paths_json || "{}"); } catch {}
    try { metadata = JSON.parse(variant.metadata_json || "{}"); } catch {}
    const hasPreview = Boolean(files.preview);
    document.getElementById("wechat-preview-empty").hidden = hasPreview;
    const frame = document.getElementById("wechat-preview-frame");
    frame.hidden = !hasPreview;
    const open = document.getElementById("wechat-open-preview");
    open.hidden = !hasPreview;
    if (hasPreview) {
      const previewUrl = `/api/platforms/variants/${encodeURIComponent(variant.id)}/preview?v=${Date.now()}`;
      frame.src = previewUrl;
      open.href = previewUrl;
    }
    const coverPair = document.getElementById("wechat-cover-pair");
    const hasCovers = Boolean(files.wide && files.square);
    coverPair.hidden = !hasCovers;
    if (hasCovers) {
      document.getElementById("wechat-cover-wide").src = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/wide?v=${Date.now()}`;
      document.getElementById("wechat-cover-square").src = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/square?v=${Date.now()}`;
    }
    const validation = document.getElementById("wechat-validation");
    const warnings = metadata.validation?.warnings || [];
    validation.hidden = !hasPreview;
    validation.className = `platform-validation${warnings.length ? " warning" : ""}`;
    validation.textContent = warnings.length ? `排版通过，仍有 ${warnings.length} 条建议：${warnings.join("；")}` : "公众号 HTML 确定性校验已通过。";
    const downloads = document.getElementById("wechat-downloads");
    downloads.replaceChildren();
    const labels = { markdown: "Markdown", html: "干净 HTML", preview: "预览页", wide: "21:9 封面", square: "1:1 封面", manifest: "清单", package: "下载发布包 ZIP" };
    Object.keys(files).forEach((key) => {
      const link = el("a", "", labels[key] || key);
      link.href = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/${encodeURIComponent(key)}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      downloads.appendChild(link);
    });
  }

  function showStatus(text, kind = "") {
    const target = document.getElementById("wechat-status");
    if (!target) return;
    target.textContent = text;
    target.className = `inline-status${kind ? ` ${kind}` : ""}`;
  }

  function setBusy(value, text = "") {
    platformState.busy = value;
    document.getElementById("wechat-view")?.classList.toggle("platform-busy", value);
    if (text) showStatus(text);
  }

  async function createVariant(event) {
    event.preventDefault();
    if (platformState.busy) return;
    setBusy(true, "正在调用平台适配 Skill，生成公众号版本…");
    try {
      const variant = await apiCall("/api/platforms/wechat/variants", {
        method: "POST",
        body: JSON.stringify({
          source_id: document.getElementById("wechat-source").value,
          draft_id: document.getElementById("wechat-draft").value || null,
          theme: document.getElementById("wechat-theme").value,
          mode: document.getElementById("wechat-mode").value,
          include_citations: document.getElementById("wechat-citations").checked,
          include_illustration_plan: document.getElementById("wechat-illustrations").checked,
          author: document.getElementById("wechat-author").value,
        }),
      });
      platformState.variants.unshift(variant);
      selectVariant(variant.id);
      showStatus("公众号版本已生成。检查正文后再排版。", "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveVariant(event) {
    event.preventDefault();
    if (!platformState.currentVariant || platformState.busy) return;
    setBusy(true, "正在保存新的公众号版本…");
    try {
      const revised = await apiCall(`/api/platforms/variants/${encodeURIComponent(platformState.currentVariant.id)}`, {
        method: "PUT",
        body: JSON.stringify({
          title: document.getElementById("wechat-title").value,
          subtitle: document.getElementById("wechat-subtitle").value,
          summary: document.getElementById("wechat-summary").value,
          body_markdown: document.getElementById("wechat-body").value,
          tags: document.getElementById("wechat-tags").value,
          theme: document.getElementById("wechat-theme").value,
        }),
      });
      platformState.variants.unshift(revised);
      selectVariant(revised.id);
      showStatus(`已保存为公众号 v${revised.version}。`, "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function editorValues() {
    return {
      title: document.getElementById("wechat-title").value,
      subtitle: document.getElementById("wechat-subtitle").value,
      summary: document.getElementById("wechat-summary").value,
      body_markdown: document.getElementById("wechat-body").value,
      tags: document.getElementById("wechat-tags").value,
      theme: document.getElementById("wechat-theme").value,
    };
  }

  async function openMemoryCandidate() {
    if (!platformState.currentVariant || platformState.busy) return;
    setBusy(true, "正在先冻结当前编辑框内容…");
    try {
      let variant = platformState.currentVariant;
      const payload = editorValues();
      const changed = ["title", "subtitle", "summary", "body_markdown", "tags", "theme"]
        .some((key) => String(variant[key] || "") !== String(payload[key] || ""));
      if (changed) {
        variant = await apiCall(`/api/platforms/variants/${encodeURIComponent(variant.id)}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        platformState.variants.unshift(variant);
        selectVariant(variant.id);
      }
      document.dispatchEvent(new CustomEvent("x2red:memory-source", {
        detail: { kind: "platform_variant", id: variant.id },
      }));
      showStatus(`已冻结为公众号 v${variant.version}，请检查记忆候选。`, "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function renderVariant() {
    if (!platformState.currentVariant || platformState.busy) return;
    setBusy(true, "正在生成内联 HTML、封面对和 ZIP 发布包…");
    try {
      const result = await apiCall(`/api/platforms/variants/${encodeURIComponent(platformState.currentVariant.id)}/render`, {
        method: "POST",
        body: JSON.stringify({ package: true }),
      });
      const index = platformState.variants.findIndex((item) => item.id === result.variant.id);
      if (index >= 0) platformState.variants[index] = result.variant;
      else platformState.variants.unshift(result.variant);
      selectVariant(result.variant.id);
      showStatus(result.validation.warnings.length ? "发布包已生成，请查看排版建议。" : "发布包已生成并通过校验。", "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function openWechatForSource(sourceId, draftId = "") {
    window.setView?.("wechat-view");
    await loadWechat(sourceId);
    const source = document.getElementById("wechat-source");
    if (sourceId && [...source.options].some((option) => option.value === sourceId)) source.value = sourceId;
    await loadDraftsForSource(draftId);
    renderVariants();
    document.getElementById("wechat-create-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function bindEvents() {
    document.getElementById("wechat-create-form").addEventListener("submit", createVariant);
    document.getElementById("wechat-editor").addEventListener("submit", saveVariant);
    document.getElementById("wechat-memory").addEventListener("click", openMemoryCandidate);
    document.getElementById("wechat-render").addEventListener("click", renderVariant);
    document.getElementById("wechat-refresh").addEventListener("click", () => loadWechat());
    document.getElementById("wechat-source").addEventListener("change", async () => {
      await loadDraftsForSource();
      renderVariants();
      const first = platformState.variants.find((item) => item.source_id === document.getElementById("wechat-source").value);
      if (first) selectVariant(first.id);
    });
  }

  function injectSkillPacks() {
    const settingsGrid = document.querySelector("#settings-view .settings-grid");
    if (!settingsGrid || document.getElementById("skill-pack-list")) return;
    const card = el("article", "surface settings-card wide");
    card.innerHTML = `<div class="panel-heading"><div><span class="section-kicker">CURATED SKILL PACKS</span><h3>平台能力包</h3><p class="helper-copy">每个能力包控制一组实际 Skill。AGPL 来源只做独立重写或外置检测，不复制第三方模板和资产。</p></div><button id="refresh-skill-packs" class="secondary-action" type="button">刷新</button></div><div id="skill-pack-list" class="skill-pack-grid"></div>`;
    settingsGrid.appendChild(card);
    document.getElementById("refresh-skill-packs").addEventListener("click", loadSkillPacks);
  }

  async function loadSkillPacks() {
    const box = document.getElementById("skill-pack-list");
    if (!box) return;
    box.textContent = "正在读取能力包…";
    try {
      const packs = await apiCall("/api/settings/skill-packs");
      box.replaceChildren();
      packs.forEach((pack) => {
        const card = el("article", `skill-pack-card${pack.enabled ? " enabled" : ""}`);
        const top = el("div", "skill-pack-top");
        const copy = el("div");
        copy.innerHTML = `<h4>${pack.label}</h4><small>${pack.platform} · ${pack.integration_mode}</small>`;
        const toggle = document.createElement("input");
        toggle.type = "checkbox";
        toggle.className = "skill-pack-toggle";
        toggle.checked = pack.enabled;
        toggle.title = "启用或关闭整套能力";
        toggle.addEventListener("change", async () => {
          toggle.disabled = true;
          try {
            const updated = await apiCall(`/api/settings/skill-packs/${encodeURIComponent(pack.id)}`, {
              method: "PUT",
              body: JSON.stringify({ enabled: toggle.checked }),
            });
            card.classList.toggle("enabled", updated.enabled);
          } catch (error) {
            toggle.checked = !toggle.checked;
            window.alert(error.message);
          } finally { toggle.disabled = false; }
        });
        top.append(copy, toggle);
        const description = el("p", "skill-pack-copy", pack.description);
        const meta = el("div", "skill-pack-meta");
        [...pack.licenses, ...pack.skills.slice(0, 4)].forEach((value) => meta.appendChild(el("span", "", value)));
        const sources = el("div", "skill-pack-sources");
        pack.source_repositories.forEach((repo) => {
          const link = el("a", "", repo);
          link.href = `https://github.com/${repo}`;
          link.target = "_blank";
          link.rel = "noreferrer";
          sources.appendChild(link);
        });
        const note = el("small", "platform-helper", `${pack.notes}${pack.installed_paths.length ? ` · 已检测到：${pack.installed_paths.join(", ")}` : ""}`);
        card.append(top, description, meta, sources, note);
        box.appendChild(card);
      });
    } catch (error) {
      box.textContent = error.message;
    }
  }

  const previousFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await previousFetch(...args);
    try {
      const url = new URL(typeof args[0] === "string" ? args[0] : args[0]?.url || "", window.location.href);
      const method = args[1]?.method || "GET";
      if (response.ok && method.toUpperCase() === "GET" && /^\/api\/writing\/projects\/[^/]+$/.test(url.pathname)) {
        response.clone().json().then((project) => {
          platformState.currentWritingProject = project;
          window.requestAnimationFrame(enhanceWritingCompletion);
        }).catch(() => {});
      }
    } catch {}
    return response;
  };

  function enhanceWritingCompletion() {
    const project = platformState.currentWritingProject;
    const actions = document.querySelector(".writing-action-dock .writing-dock-actions");
    if (!project || project.state !== "completed" || !actions || actions.querySelector(".writing-wechat-action")) return;
    const button = el("button", "secondary-action writing-wechat-action", "去公众号");
    button.type = "button";
    button.addEventListener("click", () => openWechatForSource(project.source_id));
    actions.appendChild(button);
  }

  function observeWritingDock() {
    const observer = new MutationObserver(enhanceWritingCompletion);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function boot() {
    injectNavigation();
    injectView();
    injectSkillPacks();
    bindEvents();
    observeWritingDock();
    document.querySelector('[data-view="settings-view"]')?.addEventListener("click", loadSkillPacks);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
