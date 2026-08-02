(() => {
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
  const LABELS = Object.fromEntries(GROUPS);
  const ORDER = Object.fromEntries(GROUPS.map(([id], index) => [id, index]));
  const PLATFORM_NAMES = {
    x: "X",
    xhs: "小红书",
    dy: "抖音",
    ks: "快手",
    bili: "B站",
    wb: "微博",
    tieba: "贴吧",
    zhihu: "知乎",
    web: "网页",
    local: "本地",
  };

  let sources = [];
  let sourceMap = new Map();
  let sourceGroupFilter = "all";
  let corpusGroupFilter = "all";
  let sourceRefreshPromise = null;
  let sourceRenderPatched = false;
  let scheduling = false;

  function groupOf(source) {
    if (!source) return "web";
    if (source.provider === "corpus_pool" || source.content_kind === "corpus_batch") return "pool";
    if (source.platform === "x" || source.provider === "fxtwitter" || source.provider === "signal-studio") return "x";
    if (["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"].includes(source.platform)) return source.platform;
    return "web";
  }

  function sourceName(source) {
    const author = source.author_handle
      ? `@${source.author_handle}`
      : source.author_name || LABELS[groupOf(source)] || "来源";
    const text = String(source.text_original || "").replace(/\s+/g, " ").slice(0, 52);
    return `${author} · ${text || source.content_kind || "无正文"}`;
  }

  async function refreshSources() {
    if (sourceRefreshPromise) return sourceRefreshPromise;
    sourceRefreshPromise = call("/api/sources?workspace_state=active&include_pool_batches=true&limit=2000")
      .then((items) => {
        sources = items || [];
        sourceMap = new Map(sources.map((item) => [item.id, item]));
        return sources;
      })
      .finally(() => { sourceRefreshPromise = null; });
    return sourceRefreshPromise;
  }

  function injectStyles() {
    if (document.getElementById("information-architecture-v14-style")) return;
    const style = document.createElement("style");
    style.id = "information-architecture-v14-style";
    style.textContent = `
.primary-nav{display:grid!important;gap:12px}.architecture-nav-section{display:grid;gap:5px}.architecture-nav-label{padding:0 12px;color:#8a92a2;font-size:9px;font-weight:850;letter-spacing:.15em}.architecture-nav-section .nav-item{width:100%}.source-platform-tabs{display:flex;gap:6px;overflow-x:auto;padding:0 0 10px}.source-platform-tab{flex:0 0 auto;border:1px solid #dfe3eb;border-radius:999px;background:#fff;padding:6px 9px;color:#677083;font-size:9px;font-weight:800;cursor:pointer}.source-platform-tab.active{border-color:#344bdb;background:#344bdb;color:#fff}.source-platform-badge{margin-left:auto;padding:3px 7px;border-radius:999px;background:#eef0f5;color:#657084;font-size:8px;font-weight:850}.source-item[data-source-group='pool']{border-color:#9087ea;background:#f5f3ff}.source-item[data-source-group='x'] .source-platform-badge{background:#16181d;color:#fff}.corpus-platform-filter{min-width:110px;border:1px solid #dce1ea;border-radius:10px;background:#fff;padding:9px;font-size:10px}.corpus-source-row[data-source-group]{position:relative}.corpus-source-row[data-source-group]::after{content:attr(data-source-label);position:absolute;right:8px;top:7px;padding:2px 6px;border-radius:999px;background:#eceff5;color:#687284;font-size:8px;font-weight:800}.pool-workspace-actions{display:flex;flex-wrap:wrap;gap:7px;width:100%;margin-top:3px}.pool-workspace-actions button{border:1px solid #d9deea;border-radius:9px;background:#fff;padding:8px 10px;color:#3d475a;font-size:9px;font-weight:850;cursor:pointer}.pool-workspace-actions button:first-child{border-color:#ee3159;color:#c61f43}.pool-workspace-actions button:nth-child(2),.pool-workspace-actions button:nth-child(3){border-color:#16824f;color:#126b42}.signal-to-library{border:1px solid #4d5fe5!important;background:#eef0ff!important;color:#3448cf!important}.architecture-toast{position:fixed;right:24px;bottom:24px;z-index:9999;max-width:420px;padding:12px 15px;border-radius:12px;background:#1f2532;color:#fff;box-shadow:0 16px 44px #0004;font-size:11px;line-height:1.55}.architecture-toast.error{background:#a82a2a}`;
    document.head.appendChild(style);
  }

  function toast(text, error = false) {
    document.querySelector(".architecture-toast")?.remove();
    const value = document.createElement("div");
    value.className = `architecture-toast${error ? " error" : ""}`;
    value.textContent = text;
    document.body.appendChild(value);
    setTimeout(() => value.remove(), 4200);
  }

  function navGroup(view) {
    if (["signals-view", "materials-view", "corpus-pools-view"].includes(view)) return "library";
    if (["settings-view", "style-view", "native-skills-view"].includes(view)) return "models";
    return "workspace";
  }

  function reorganizeNavigation() {
    const nav = document.querySelector(".primary-nav");
    if (!nav) return;
    const ungrouped = [...nav.children].filter((item) => item.classList?.contains("nav-item"));
    if (nav.dataset.architectureV14 === "true" && !ungrouped.length) return;
    const buttons = [...nav.querySelectorAll(".nav-item")];
    if (!buttons.length) return;
    const definitions = [
      ["library", "01 · 语料素材库"],
      ["workspace", "02 · 内容工作台"],
      ["models", "03 · 模型与 Skill"],
    ];
    const containers = {};
    definitions.forEach(([id, label]) => {
      let section = nav.querySelector(`[data-architecture-section='${id}']`);
      if (!section) {
        section = document.createElement("section");
        section.className = "architecture-nav-section";
        section.dataset.architectureSection = id;
        const title = document.createElement("div");
        title.className = "architecture-nav-label";
        title.textContent = label;
        section.appendChild(title);
      }
      containers[id] = section;
    });
    buttons.forEach((button) => {
      const view = button.dataset.view || "";
      const label = button.querySelector("span:last-child");
      if (label) {
        if (view === "workbench-view") label.textContent = "小红书工作台";
        if (view === "signals-view") label.textContent = "X 信号发现";
        if (view === "materials-view") label.textContent = "简中原料发现";
        if (view === "corpus-pools-view") label.textContent = "语料素材库";
      }
      containers[navGroup(view)].appendChild(button);
    });
    nav.replaceChildren(...definitions.map(([id]) => containers[id]));
    nav.dataset.architectureV14 = "true";
  }

  function appState() {
    try {
      if (typeof state !== "undefined") return state;
    } catch {}
    return null;
  }

  function matchesSearch(item) {
    const query = document.getElementById("source-search")?.value.trim().toLowerCase() || "";
    if (!query) return true;
    return [item.author_name, item.author_handle, item.text_original, item.platform, item.provider]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  }

  function decorateSourceList(displayed) {
    const buttons = [...document.querySelectorAll("#source-list .source-item")];
    buttons.forEach((button, index) => {
      const source = displayed[index];
      if (!source) return;
      const group = groupOf(source);
      button.dataset.sourceGroup = group;
      const bottom = button.querySelector(".source-item-bottom");
      if (bottom && !bottom.querySelector(".source-platform-badge")) {
        const badge = document.createElement("span");
        badge.className = "source-platform-badge";
        badge.textContent = LABELS[group] || PLATFORM_NAMES[source.platform] || source.platform;
        bottom.appendChild(badge);
      }
    });
  }

  function patchSourceRail() {
    if (sourceRenderPatched) return;
    const root = appState();
    if (!root || typeof renderSourceList !== "function") return;
    sourceRenderPatched = true;
    root.sourcePlatformGroup = root.sourcePlatformGroup || "all";
    const original = renderSourceList;
    renderSourceList = function renderCategorizedSourceList() {
      const all = root.sourceItems || [];
      const filtered = all.filter((item) => (
        sourceGroupFilter === "all" || groupOf(item) === sourceGroupFilter
      ));
      root.sourceItems = filtered;
      original();
      root.sourceItems = all;
      decorateSourceList(filtered.filter(matchesSearch));
    };
    const search = document.querySelector(".source-rail .source-filter");
    if (search && !document.getElementById("source-platform-tabs")) {
      const tabs = document.createElement("div");
      tabs.id = "source-platform-tabs";
      tabs.className = "source-platform-tabs";
      [["all", "全部"], ...GROUPS].forEach(([id, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `source-platform-tab${id === "all" ? " active" : ""}`;
        button.textContent = label;
        button.dataset.sourceGroup = id;
        button.addEventListener("click", () => {
          sourceGroupFilter = id;
          tabs.querySelectorAll("button").forEach((item) => {
            item.classList.toggle("active", item === button);
          });
          renderSourceList();
        });
        tabs.appendChild(button);
      });
      search.before(tabs);
    }
    renderSourceList();
  }

  function regroupSelect(select) {
    if (!select || !sources.length) return;
    const current = select.value;
    const signature = `${sources.map((item) => item.id).join("|")}:${current}`;
    if (select.dataset.architectureSignature === signature && select.querySelector("optgroup")) return;
    const existingLabels = new Map(
      [...select.querySelectorAll("option")]
        .filter((option) => option.value)
        .map((option) => [option.value, option.textContent]),
    );
    const groups = new Map(GROUPS.map(([id, label]) => {
      const group = document.createElement("optgroup");
      group.label = label;
      return [id, group];
    }));
    sources
      .slice()
      .sort((a, b) => ORDER[groupOf(a)] - ORDER[groupOf(b)])
      .forEach((source) => {
        const option = new Option(existingLabels.get(source.id) || sourceName(source), source.id);
        groups.get(groupOf(source)).appendChild(option);
      });
    select.replaceChildren(...[...groups.values()].filter((group) => group.children.length));
    if (current && sourceMap.has(current)) select.value = current;
    select.dataset.architectureSignature = signature;
  }

  function regroupWorkspaceSelects() {
    ["writing-source", "wechat-source", "light-source"].forEach((id) => {
      regroupSelect(document.getElementById(id));
    });
  }

  function patchCorpusPicker() {
    const filter = document.querySelector("#corpus-pools-view .corpus-filter");
    const list = document.getElementById("corpus-source-list");
    if (!filter || !list) return;
    let select = document.getElementById("corpus-platform-filter");
    if (!select) {
      select = document.createElement("select");
      select.id = "corpus-platform-filter";
      select.className = "corpus-platform-filter";
      select.appendChild(new Option("全部平台", "all"));
      GROUPS.filter(([id]) => id !== "pool").forEach(([id, label]) => {
        select.appendChild(new Option(label, id));
      });
      select.addEventListener("change", () => {
        corpusGroupFilter = select.value;
        patchCorpusPicker();
      });
      filter.appendChild(select);
    }
    const rows = [...list.querySelectorAll(".corpus-source-row")];
    rows.forEach((row) => {
      const id = row.querySelector("[data-source-id]")?.dataset.sourceId;
      const source = sourceMap.get(id);
      const group = groupOf(source);
      row.dataset.sourceGroup = group;
      row.dataset.sourceLabel = LABELS[group] || "其他";
      row.hidden = group === "pool" || (corpusGroupFilter !== "all" && group !== corpusGroupFilter);
    });
    const sorted = rows.slice().sort((a, b) => ORDER[a.dataset.sourceGroup] - ORDER[b.dataset.sourceGroup]);
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
    await new Promise((resolve) => setTimeout(resolve, 300));
    regroupWorkspaceSelects();
    if (target === "light") {
      document.dispatchEvent(new CustomEvent("x2red:open-wechat-light", {
        detail: { sourceId },
      }));
      await new Promise((resolve) => setTimeout(resolve, 450));
    }
    const select = document.getElementById(target === "light" ? "light-source" : "wechat-source");
    if (select && [...select.options].some((option) => option.value === sourceId)) {
      select.value = sourceId;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  async function materializePool(target, button) {
    const active = document.querySelector(".corpus-pool-card.active[data-pool-id]");
    const poolId = active?.dataset.poolId;
    if (!poolId) return toast("请先选择一个语料池。", true);
    button.disabled = true;
    const old = button.textContent;
    button.textContent = "正在冻结批次…";
    try {
      const batch = await call(`/api/corpus-pools/${encodeURIComponent(poolId)}/materialize`, {
        method: "POST",
        body: JSON.stringify({
          batch_size: Number(document.getElementById("corpus-generate-size")?.value || 6),
          focus: document.getElementById("corpus-focus")?.value || "",
        }),
      });
      if (!batch.anchor_source_id) throw new Error("批次来源创建失败");
      await openWorkspace(target, batch.anchor_source_id);
      toast(`第 ${batch.sequence} 批已冻结并送入${target === "xhs" ? "小红书" : target === "light" ? "公众号轻内容" : "公众号长文"}工作台。`);
    } catch (error) {
      toast(error.message || String(error), true);
    } finally {
      button.disabled = false;
      button.textContent = old;
    }
  }

  function patchPoolActions() {
    const generate = document.getElementById("corpus-generate");
    const parent = generate?.parentElement;
    if (!parent || parent.querySelector(".pool-workspace-actions")) return;
    const actions = document.createElement("div");
    actions.className = "pool-workspace-actions";
    [
      ["xhs", "送到小红书工作台"],
      ["wechat", "送到公众号长文"],
      ["light", "送到公众号轻内容"],
    ].forEach(([target, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", () => materializePool(target, button));
      actions.appendChild(button);
    });
    parent.appendChild(actions);
  }

  async function patchSignalCards() {
    if (!document.getElementById("signals-view")?.classList.contains("active")) return;
    const cards = [...document.querySelectorAll("#signal-feed .signal-item")];
    if (!cards.length || cards.every((card) => card.dataset.libraryPatched === "true")) return;
    const grade = document.getElementById("signal-grade")?.value || "";
    const feed = await call(`/api/signals/feed?grade=${encodeURIComponent(grade)}&limit=200`);
    cards.forEach((card, index) => {
      const item = feed[index];
      if (!item || card.dataset.libraryPatched === "true") return;
      card.dataset.libraryPatched = "true";
      const actions = card.querySelector(".signal-actions");
      if (!actions) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tool-button signal-to-library";
      button.textContent = item.promoted_source_id ? "已进入素材库" : "加入语料素材库";
      button.disabled = Boolean(item.promoted_source_id);
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "正在合并 X 来源…";
        try {
          const source = await call(`/api/sources/from-signal/${encodeURIComponent(item.candidate_id)}`, { method: "POST" });
          await refreshSources();
          button.textContent = "已进入素材库";
          toast(`X 来源已合并：${source.author_handle ? `@${source.author_handle}` : source.author_name || "未知作者"}`);
        } catch (error) {
          button.disabled = false;
          button.textContent = "加入语料素材库";
          toast(error.message || String(error), true);
        }
      });
      actions.insertBefore(button, actions.lastElementChild);
    });
  }

  function schedule() {
    if (scheduling) return;
    scheduling = true;
    requestAnimationFrame(async () => {
      scheduling = false;
      reorganizeNavigation();
      patchSourceRail();
      regroupWorkspaceSelects();
      patchCorpusPicker();
      patchPoolActions();
      await patchSignalCards().catch(() => {});
    });
  }

  async function boot() {
    injectStyles();
    await refreshSources().catch(() => []);
    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("click", (event) => {
      if (event.target.closest("#refresh, #light-refresh, #wechat-refresh, #refresh-writing")) {
        setTimeout(() => refreshSources().then(schedule).catch(() => {}), 300);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
