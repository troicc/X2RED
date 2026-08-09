(() => {
  if (window.__x2redProductShellV15) return;

  const GROUPS = [
    ["pool", "语料池批次"],
    ["x", "X / 信号台"],
    ["xhs", "小红书"],
    ["dy", "抖音"],
    ["ks", "快手"],
    ["bili", "B站"],
    ["wb", "微博"],
    ["tieba", "贴吧"],
    ["zhihu", "知乎"],
    ["web", "网页与文档"],
  ];

  const NAVIGATION = [
    {
      group: "library",
      layer: "01 · 语料素材库",
      view: "signals-view",
      label: "X 信号发现",
    },
    {
      group: "library",
      layer: "01 · 语料素材库",
      view: "materials-view",
      label: "简中原料发现",
    },
    {
      group: "library",
      layer: "01 · 语料素材库",
      view: "corpus-pools-view",
      label: "语料素材库",
    },
    {
      group: "workspace",
      layer: "02 · 内容工作台",
      view: "workbench-view",
      label: "小红书工作台",
    },
    {
      group: "workspace",
      layer: "02 · 内容工作台",
      view: "wechat-view",
      label: "公众号工作台",
    },
    {
      group: "workspace",
      layer: "02 · 内容工作台",
      view: "publish-view",
      label: "发布任务",
    },
    {
      group: "models",
      layer: "03 · 模型与 Skill",
      view: "pool-memory-view",
      label: "写作偏好",
    },
    {
      group: "models",
      layer: "03 · 模型与 Skill",
      view: "style-lab-view",
      label: "风格配置",
    },
    {
      group: "models",
      layer: "03 · 模型与 Skill",
      view: "settings-view",
      label: "模型与 Skill",
    },
  ];

  const GROUP_ORDER = ["library", "workspace", "models"];
  const GROUP_LABELS = new Map(NAVIGATION.map((item) => [item.group, item.layer]));
  const BY_VIEW = new Map(NAVIGATION.map((item) => [item.view, item]));
  const SOURCE_LABELS = Object.fromEntries(GROUPS);
  const SOURCE_ORDER = Object.fromEntries(GROUPS.map(([id], index) => [id, index]));

  const shellState = {
    activeView: "workbench-view",
    sources: [],
    sourceMap: new Map(),
    sourceGroupFilter: "all",
    corpusGroupFilter: "all",
    sourceRefreshPromise: null,
    sourceRailPatched: false,
    scheduled: false,
    booted: false,
  };

  window.__x2redProductShellV15 = shellState;

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

  const node = (id) => document.getElementById(id);

  function create(tag, className = "", text = "") {
    const value = document.createElement(tag);
    if (className) value.className = className;
    if (text) value.textContent = text;
    return value;
  }

  function appState() {
    try {
      return typeof state !== "undefined" ? state : null;
    } catch {
      return null;
    }
  }

  function groupOf(source) {
    if (!source) return "web";
    if (source.provider === "corpus_pool" || source.content_kind === "corpus_batch") return "pool";
    if (source.platform === "x" || source.provider === "fxtwitter" || source.provider === "signal-studio") return "x";
    if (["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"].includes(source.platform)) {
      return source.platform;
    }
    return "web";
  }

  function sourceName(source) {
    const author = source.author_handle
      ? `@${source.author_handle}`
      : source.author_name || SOURCE_LABELS[groupOf(source)] || "来源";
    const text = String(source.text_original || "").replace(/\s+/g, " ").slice(0, 52);
    return `${author} · ${text || source.content_kind || "无正文"}`;
  }

  function showToast(text, error = false) {
    document.querySelector(".product-shell-toast")?.remove();
    const toast = create("div", `product-shell-toast${error ? " error" : ""}`, text);
    toast.setAttribute("role", "status");
    document.body.appendChild(toast);
    window.setTimeout(() => toast.remove(), 4600);
  }

  function navButtonLabel(button, label) {
    let copy = button.querySelector(".product-nav-copy");
    if (!copy) {
      const spans = [...button.querySelectorAll("span")];
      copy = spans.find((item) => !item.classList.contains("nav-icon")) || create("span", "product-nav-copy");
      if (!copy.parentElement) button.appendChild(copy);
      copy.classList.add("product-nav-copy");
    }
    copy.textContent = label;
    button.setAttribute("aria-label", label);
  }

  function contentTitle(viewId, label) {
    const view = node(viewId);
    const title = view?.querySelector(".page-intro h2");
    if (title) title.textContent = label;
  }

  function navigationNeedsLayout(nav, sections, buttonsByView) {
    if (!GROUP_ORDER.every((group) => nav.contains(sections[group]))) return true;
    if ([...nav.children].length !== GROUP_ORDER.length) return true;
    return NAVIGATION.some((item) => {
      const button = buttonsByView.get(item.view);
      return !button || button.parentElement !== sections[item.group];
    });
  }

  function reorganizeNavigation() {
    const nav = document.querySelector(".primary-nav");
    if (!nav) return;
    // Dynamic base modules still insert against direct nav children.  Do not nest
    // anything until every declared view has appeared; otherwise their late
    // insertBefore calls would receive a descendant instead of a direct child.
    const buttonsByView = new Map(NAVIGATION.map((item) => {
      const button = item.view === "materials-view"
        ? node("materials-nav")
        : nav.querySelector(`[data-view="${item.view}"]`);
      if (button && !button.dataset.view) button.dataset.view = item.view;
      return [item.view, button];
    }));
    if ([...buttonsByView.values()].some((button) => !button)) return;
    const sections = {};
    GROUP_ORDER.forEach((group) => {
      let section = nav.querySelector(`[data-product-nav-group="${group}"]`);
      if (!section) {
        section = create("section", "product-nav-section");
        section.dataset.productNavGroup = group;
        const heading = create("div", "product-nav-label", GROUP_LABELS.get(group));
        section.appendChild(heading);
      }
      sections[group] = section;
    });

    NAVIGATION.forEach((item) => {
      const button = buttonsByView.get(item.view);
      if (!button) return;
      navButtonLabel(button, item.label);
      contentTitle(item.view, item.label);
      if (button.type !== "button") button.type = "button";
    });

    if (!navigationNeedsLayout(nav, sections, buttonsByView)) return;
    NAVIGATION.forEach((item) => {
      const button = buttonsByView.get(item.view);
      if (button) sections[item.group].appendChild(button);
    });
    nav.replaceChildren(...GROUP_ORDER.map((group) => sections[group]));
  }

  function updateIdentity(requestedView = "") {
    const active = requestedView || document.querySelector(".app-view.active")?.id || shellState.activeView;
    const item = BY_VIEW.get(active);
    if (!item && active === "writing-view") {
      shellState.activeView = active;
      const context = node("global-context");
      if (context) context.textContent = "02 · 内容工作台 / 公众号工作台 / 深度写作";
      const legacyTitle = node("page-title");
      if (legacyTitle) legacyTitle.textContent = "公众号深度写作";
      contentTitle(active, "公众号深度写作");
      return;
    }
    if (!item) return;
    shellState.activeView = active;
    const context = node("global-context");
    if (context) context.textContent = `${item.layer} / ${item.label}`;
    const legacyTitle = node("page-title");
    if (legacyTitle) legacyTitle.textContent = item.label;
    contentTitle(active, item.label);
  }

  function wrapSetView() {
    if (window.__x2redProductSetViewV15) return;
    window.__x2redProductSetViewV15 = true;
    const previous = window.setView;
    window.setView = function setProductView(viewId, ...args) {
      const changed = shellState.activeView !== viewId;
      const result = previous?.call(this, viewId, ...args);
      updateIdentity(viewId);
      if (changed) {
        const main = document.querySelector(".app-main");
        if (main) main.scrollTop = 0;
      }
      schedule();
      return result;
    };
  }

  function sourceMatchesSearch(item) {
    const query = node("source-search")?.value.trim().toLowerCase() || "";
    if (!query) return true;
    return [item.author_name, item.author_handle, item.text_original]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  }

  function decorateSourceList(displayed) {
    const rows = [...document.querySelectorAll("#source-list .source-item")];
    rows.forEach((row, index) => {
      const source = displayed[index];
      if (!source) return;
      const group = groupOf(source);
      row.dataset.sourceGroup = group;
    });
  }

  function addSourcePlatformTabs() {
    const rail = document.querySelector(".source-rail");
    const search = rail?.querySelector(".source-filter");
    if (!rail || !search || node("source-platform-filter")) return;
    const field = create("label", "source-platform-filter");
    field.id = "source-platform-filter";
    const caption = create("span", "source-platform-filter-label", "来源类型");
    const select = document.createElement("select");
    select.setAttribute("aria-label", "按来源类型筛选");
    [["all", "全部"], ...GROUPS].forEach(([id, label]) => {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = label;
      select.appendChild(option);
    });
    select.value = shellState.sourceGroupFilter;
    select.addEventListener("change", () => {
      shellState.sourceGroupFilter = select.value;
      try {
        if (typeof renderSourceList === "function") renderSourceList();
      } catch {
        // The base source list can be absent while its view is rebuilding.
      }
    });
    field.append(caption, select);
    search.before(field);
  }

  function patchSourceRail() {
    if (shellState.sourceRailPatched) return;
    const root = appState();
    try {
      if (!root || typeof renderSourceList !== "function") return;
      const original = renderSourceList;
      renderSourceList = function renderCategorizedSourceList() {
        const all = root.sourceItems || [];
        const filtered = all.filter((item) => (
          shellState.sourceGroupFilter === "all" || groupOf(item) === shellState.sourceGroupFilter
        ));
        root.sourceItems = filtered;
        try {
          original();
        } finally {
          root.sourceItems = all;
        }
        decorateSourceList(filtered.filter(sourceMatchesSearch));
      };
      shellState.sourceRailPatched = true;
      addSourcePlatformTabs();
      renderSourceList();
    } catch {
      // The base source controller is not ready yet; the next scheduled pass retries.
    }
  }

  async function refreshSources() {
    if (shellState.sourceRefreshPromise) return shellState.sourceRefreshPromise;
    shellState.sourceRefreshPromise = call(
      "/api/sources?workspace_state=active&include_pool_batches=true&limit=2000",
    )
      .then((items) => {
        shellState.sources = Array.isArray(items) ? items : [];
        shellState.sourceMap = new Map(shellState.sources.map((item) => [item.id, item]));
        document.dispatchEvent(new CustomEvent("x2red:sources-refreshed", {
          detail: { sources: shellState.sources },
        }));
        return shellState.sources;
      })
      .finally(() => { shellState.sourceRefreshPromise = null; });
    return shellState.sourceRefreshPromise;
  }

  function regroupSelect(select) {
    if (!select || !shellState.sources.length) return;
    const sourceSignature = shellState.sources.map((item) => item.id).join("|");
    if (select.dataset.productSourceSignature === sourceSignature && select.querySelector("optgroup")) return;
    const current = select.value;
    const labels = new Map(
      [...select.querySelectorAll("option")]
        .filter((option) => option.value)
        .map((option) => [option.value, option.textContent]),
    );
    const groups = new Map(GROUPS.map(([id, label]) => {
      const group = document.createElement("optgroup");
      group.label = label;
      return [id, group];
    }));
    shellState.sources
      .slice()
      .sort((left, right) => SOURCE_ORDER[groupOf(left)] - SOURCE_ORDER[groupOf(right)])
      .forEach((source) => {
        const option = new Option(labels.get(source.id) || sourceName(source), source.id);
        groups.get(groupOf(source)).appendChild(option);
      });
    select.replaceChildren(...[...groups.values()].filter((group) => group.children.length));
    if (current && shellState.sourceMap.has(current)) select.value = current;
    select.dataset.productSourceSignature = sourceSignature;
  }

  function regroupWorkspaceSelects() {
    ["writing-source", "wechat-source", "light-source"].forEach((id) => regroupSelect(node(id)));
  }

  function ensureNativeCardOptions() {
    const select = node("card-visual-style");
    if (!select) return;
    if (!select.querySelector('option[value="guizang_editorial"]')) {
      select.add(new Option("Guizang Editorial · 原生完整链", "guizang_editorial"));
    }
    if (!select.querySelector('option[value="guizang_swiss"]')) {
      select.add(new Option("Guizang Swiss · 原生完整链", "guizang_swiss"));
    }
  }

  function patchCorpusPicker() {
    const filter = document.querySelector("#corpus-pools-view .corpus-filter");
    const list = node("corpus-source-list");
    if (!filter || !list) return;
    let select = node("corpus-platform-filter");
    if (!select) {
      select = document.createElement("select");
      select.id = "corpus-platform-filter";
      select.className = "corpus-platform-filter";
      select.appendChild(new Option("全部平台", "all"));
      GROUPS.filter(([id]) => id !== "pool").forEach(([id, label]) => {
        select.appendChild(new Option(label, id));
      });
      select.addEventListener("change", () => {
        shellState.corpusGroupFilter = select.value;
        patchCorpusPicker();
      });
      filter.appendChild(select);
    }
    const rows = [...list.querySelectorAll(".corpus-source-row")];
    rows.forEach((row) => {
      const sourceId = row.querySelector("[data-source-id]")?.dataset.sourceId;
      const group = groupOf(shellState.sourceMap.get(sourceId));
      row.dataset.sourceGroup = group;
      row.dataset.sourceLabel = SOURCE_LABELS[group] || "其他";
      row.hidden = group === "pool" || (shellState.corpusGroupFilter !== "all" && group !== shellState.corpusGroupFilter);
    });
    const sorted = rows.slice().sort((left, right) => (
      SOURCE_ORDER[left.dataset.sourceGroup] - SOURCE_ORDER[right.dataset.sourceGroup]
    ));
    if (sorted.some((row, index) => row !== rows[index])) {
      sorted.forEach((row) => list.appendChild(row));
    }
  }

  async function openWorkspace(target, sourceId) {
    await refreshSources();
    regroupWorkspaceSelects();
    if (target === "xhs") {
      window.setView?.("workbench-view");
      if (typeof loadSources === "function") await loadSources(sourceId);
      else if (typeof selectSource === "function") await selectSource(sourceId);
      return;
    }
    window.setView?.("wechat-view");
    if (target === "light") {
      document.dispatchEvent(new CustomEvent("x2red:open-wechat-light", { detail: { sourceId } }));
      return;
    }
    const select = node("wechat-source");
    if (select && [...select.options].some((option) => option.value === sourceId)) {
      select.value = sourceId;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  async function materializePool(target, button) {
    const active = document.querySelector(".corpus-pool-card.active[data-pool-id]");
    const poolId = active?.dataset.poolId;
    if (!poolId) {
      showToast("请先选择一个语料池。", true);
      return;
    }
    button.disabled = true;
    const label = button.textContent;
    button.textContent = "正在冻结批次…";
    try {
      const batch = await call(`/api/corpus-pools/${encodeURIComponent(poolId)}/materialize`, {
        method: "POST",
        body: JSON.stringify({
          batch_size: Number(node("corpus-generate-size")?.value || 6),
          focus: node("corpus-focus")?.value || "",
        }),
      });
      if (!batch?.anchor_source_id) throw new Error("批次来源创建失败");
      await openWorkspace(target, batch.anchor_source_id);
      const targetLabel = target === "xhs" ? "小红书工作台" : target === "light" ? "公众号轻内容" : "公众号长文";
      showToast(`第 ${batch.sequence} 批已冻结并送入${targetLabel}。`);
    } catch (error) {
      showToast(error.message || String(error), true);
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }

  function patchPoolActions() {
    const generate = node("corpus-generate");
    const parent = generate?.parentElement;
    if (!parent || parent.querySelector(".pool-workspace-actions")) return;
    const actions = create("div", "pool-workspace-actions");
    [
      ["xhs", "送到小红书工作台"],
      ["wechat", "送到公众号长文"],
      ["light", "送到公众号轻内容"],
    ].forEach(([target, label]) => {
      const button = create("button", "", label);
      button.type = "button";
      button.addEventListener("click", () => { void materializePool(target, button); });
      actions.appendChild(button);
    });
    parent.appendChild(actions);
  }

  async function patchSignalCards() {
    if (!node("signals-view")?.classList.contains("active")) return;
    const cards = [...document.querySelectorAll("#signal-feed .signal-item")];
    if (!cards.length || cards.every((card) => card.dataset.libraryPatched === "true")) return;
    const grade = node("signal-grade")?.value || "";
    const feed = await call(`/api/signals/feed?grade=${encodeURIComponent(grade)}&limit=200`);
    cards.forEach((card, index) => {
      const item = feed?.[index];
      if (!item || card.dataset.libraryPatched === "true") return;
      card.dataset.libraryPatched = "true";
      const actions = card.querySelector(".signal-actions");
      if (!actions) return;
      const button = create("button", "tool-button signal-to-library", item.promoted_source_id ? "已进入素材库" : "加入语料素材库");
      button.type = "button";
      button.disabled = Boolean(item.promoted_source_id);
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "正在合并 X 来源…";
        try {
          const source = await call(`/api/sources/from-signal/${encodeURIComponent(item.candidate_id)}`, { method: "POST" });
          await refreshSources();
          button.textContent = "已进入素材库";
          showToast(`X 来源已合并：${source.author_handle ? `@${source.author_handle}` : source.author_name || "未知作者"}`);
        } catch (error) {
          button.disabled = false;
          button.textContent = "加入语料素材库";
          showToast(error.message || String(error), true);
        }
      });
      actions.insertBefore(button, actions.firstElementChild || null);
    });
  }

  function restoreWritingProject() {
    const match = (window.location.hash || "").match(/^#writing-project=([^&]+)$/);
    if (!match) return;
    const expectedId = decodeURIComponent(match[1]);
    window.setView?.("writing-view");
    const selectExpectedProject = () => {
      const list = node("writing-project-list");
      const target = [...(list?.querySelectorAll("button.writing-project-item") || [])]
        .find((button) => button.dataset.projectId === expectedId);
      if (!target) return false;
      target.click();
      history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      node("writing-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return true;
    };
    if (selectExpectedProject()) return;
    const observer = new MutationObserver(() => {
      if (!selectExpectedProject()) return;
      observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    window.setTimeout(() => observer.disconnect(), 15000);
    node("writing-project-list")?.setAttribute("data-restore-project-id", expectedId);
  }

  function schedule() {
    if (shellState.scheduled) return;
    shellState.scheduled = true;
    window.requestAnimationFrame(() => {
      shellState.scheduled = false;
      reorganizeNavigation();
      updateIdentity();
      addSourcePlatformTabs();
      patchSourceRail();
      regroupWorkspaceSelects();
      ensureNativeCardOptions();
      patchCorpusPicker();
      patchPoolActions();
      void patchSignalCards().catch(() => {});
    });
  }

  function boot() {
    if (shellState.booted) return;
    shellState.booted = true;
    wrapSetView();
    refreshSources().then(schedule).catch(schedule);
    schedule();
    restoreWritingProject();
    document.addEventListener("click", (event) => {
      const button = event.target.closest(".nav-item[data-view]");
      if (button) window.requestAnimationFrame(() => updateIdentity(button.dataset.view));
      if (event.target.closest("#refresh, #light-refresh, #wechat-refresh, #refresh-writing, #corpus-refresh")) {
        window.setTimeout(() => { void refreshSources().then(schedule).catch(() => {}); }, 250);
      }
    });
    document.addEventListener("x2red:sources-changed", () => {
      void refreshSources().then(schedule).catch(() => {});
    });
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
      childList: true,
      subtree: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
