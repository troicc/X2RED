(() => {
  const state = {
    pools: [],
    sources: [],
    pool: null,
    selected: new Set(),
    preview: null,
    busy: false,
  };

  const byId = (id) => document.getElementById(id);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }

  function html(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function compact(value, limit = 110) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
  }

  function sourceTitle(source) {
    const first = String(source.text_original || "")
      .split(/[。！？!?\n]/)[0]
      .replace(/^来源\s*[·:：-]?\s*/, "")
      .trim();
    return first.slice(0, 72) || source.author_name || source.author_handle || "未命名来源";
  }

  function dateText(value) {
    if (!value) return "尚未使用";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "已记录";
    return new Intl.DateTimeFormat("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function setStatus(text, type = "") {
    const node = byId("corpus-status");
    if (!node) return;
    node.textContent = text;
    node.className = `corpus-status ${type}`.trim();
  }

  function injectStyles() {
    if (byId("corpus-pools-v13-style")) return;
    const style = document.createElement("style");
    style.id = "corpus-pools-v13-style";
    style.textContent = `
.corpus-shell{display:grid;grid-template-columns:minmax(300px,340px) minmax(250px,300px) minmax(420px,1fr);gap:16px;align-items:start}.corpus-panel{border:1px solid #e2e6ee;border-radius:20px;background:#fff;box-shadow:0 16px 40px #1720330a;overflow:hidden;min-height:640px}.corpus-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px;border-bottom:1px solid #edf0f5}.corpus-head h3{margin:3px 0 0}.corpus-body{padding:16px}.corpus-form{display:grid;gap:10px}.corpus-field{display:grid;gap:6px;font-size:11px;font-weight:760;color:#566174}.corpus-field input,.corpus-field textarea,.corpus-field select,.corpus-filter input{width:100%;border:1px solid #dce1ea;border-radius:10px;background:#fbfcff;padding:10px 11px;font:inherit;color:#252d3a}.corpus-actions{display:flex;gap:8px;flex-wrap:wrap}.corpus-actions button,.corpus-filter button{border:1px solid #dce1ea;border-radius:10px;background:#fff;min-height:38px;padding:0 12px;font-size:10px;font-weight:820;color:#3d485b;cursor:pointer}.corpus-actions .primary{background:#4057eb;border-color:#4057eb;color:#fff}.corpus-actions .danger{color:#b42318}.corpus-actions button:disabled{opacity:.45}.corpus-filter{display:flex;gap:8px;margin-bottom:10px}.corpus-filter input{flex:1}.corpus-source-list,.corpus-pool-list,.corpus-member-list,.corpus-batch-list{display:grid;gap:8px;max-height:420px;overflow:auto;padding-right:3px}.corpus-source-row{display:grid;grid-template-columns:auto 1fr;gap:9px;padding:10px;border:1px solid #e5e8ef;border-radius:12px;background:#fafbfe;cursor:pointer}.corpus-source-row input{margin-top:3px}.corpus-source-copy{min-width:0}.corpus-source-copy strong{display:block;font-size:11px;line-height:1.35}.corpus-source-copy p{margin:4px 0 0;color:#7a8393;font-size:9px;line-height:1.45}.corpus-source-meta,.corpus-pool-stats{display:flex;gap:6px;flex-wrap:wrap;margin-top:5px;color:#9299a6;font-size:8px}.corpus-pool-card{width:100%;text-align:left;border:1px solid #e3e7ef;border-radius:14px;background:#fafbfe;padding:12px;cursor:pointer}.corpus-pool-card.active{border-color:#7080ee;background:#f0f2ff}.corpus-pool-card strong{display:block;font-size:12px}.corpus-pool-card p{margin:5px 0;color:#747d8e;font-size:9px;line-height:1.45}.corpus-empty{display:grid;place-items:center;min-height:260px;padding:30px;text-align:center;color:#7d8696;font-size:11px;line-height:1.7}.corpus-detail-top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.corpus-detail-top h2{margin:3px 0 5px;font-size:22px}.corpus-detail-top p{margin:0;color:#707a8b;font-size:10px}.corpus-stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}.corpus-stat{padding:10px;border-radius:12px;background:#f5f7fb}.corpus-stat strong{display:block;font-size:16px}.corpus-stat span{font-size:8px;color:#828b9a}.corpus-keywords{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.corpus-keyword{padding:4px 8px;border-radius:999px;background:#eef0ff;color:#4657d6;font-size:9px;font-weight:780}.corpus-memory{max-height:280px;overflow:auto;white-space:pre-wrap;margin:10px 0 16px;padding:13px;border-radius:12px;background:#f7f8fb;color:#4d586b;font-size:9px;line-height:1.65}.corpus-section{margin-top:16px;padding-top:16px;border-top:1px solid #edf0f5}.corpus-section-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px}.corpus-section-title h4{margin:0;font-size:12px}.corpus-member{display:grid;grid-template-columns:1fr auto;gap:9px;padding:10px;border:1px solid #e5e8ef;border-radius:12px}.corpus-member strong{display:block;font-size:10px}.corpus-member p{margin:4px 0;color:#747d8e;font-size:9px;line-height:1.45}.corpus-member small{font-size:8px;color:#9299a6}.corpus-member button{border:0;background:transparent;color:#b42318;cursor:pointer}.corpus-preview{margin-top:10px;padding:11px;border-radius:12px;background:#fff8e7;color:#72551a;font-size:9px;line-height:1.55}.corpus-preview ol{padding-left:18px;margin:7px 0}.corpus-result{margin-top:10px;padding:13px;border-radius:12px;background:#eaf8f0;color:#176446}.corpus-result h4{margin:0 0 6px}.corpus-result p{white-space:pre-wrap;margin:0;font-size:9px;line-height:1.55;max-height:190px;overflow:auto}.corpus-batch{padding:10px;border:1px solid #e5e8ef;border-radius:12px}.corpus-batch strong{font-size:10px}.corpus-batch p{margin:4px 0;color:#747d8e;font-size:9px}.corpus-batch button{margin-top:6px;border:1px solid #dce1ea;border-radius:8px;background:#fff;padding:6px 9px;font-size:9px;cursor:pointer}.corpus-status{margin-top:10px;min-height:36px;padding:9px 11px;border-radius:10px;background:#f4f6fa;color:#667184;font-size:9px;line-height:1.5}.corpus-status.ok{background:#eaf8f0;color:#19724c}.corpus-status.error{background:#fff0f0;color:#b42318}@media(max-width:1280px){.corpus-shell{grid-template-columns:310px 1fr}.corpus-detail-panel{grid-column:1/-1}}@media(max-width:760px){.corpus-shell{grid-template-columns:1fr}.corpus-stat-grid{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);
  }

  function injectNav() {
    if (document.querySelector('[data-view="corpus-pools-view"]')) return;
    const nav = document.querySelector(".primary-nav");
    if (!nav) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "nav-item";
    button.dataset.view = "corpus-pools-view";
    button.innerHTML = '<span class="nav-icon">▦</span><span>语料池</span>';
    button.addEventListener("click", openView);
    nav.insertBefore(button, nav.querySelector('[data-view="publish-view"]'));
  }

  function injectView() {
    if (byId("corpus-pools-view")) return;
    const stack = document.querySelector(".view-stack");
    if (!stack) return;
    const view = document.createElement("section");
    view.id = "corpus-pools-view";
    view.className = "app-view";
    view.innerHTML = `
<section class="page-intro"><span class="section-kicker">CORPUS MEMORY + ROTATING BATCHES</span><h2>可复用语料池</h2><p>来源先完成清洗、摘要、自动命名与全池记忆；生成时只展开一个小批次的详细原文，但每批都能看见整个池子的主题版图。</p></section>
<section class="corpus-shell">
  <aside class="corpus-panel"><div class="corpus-head"><div><span class="section-kicker">SOURCE PICKER</span><h3>批量选择来源</h3></div><span id="corpus-selected-count" class="count-badge">0 条</span></div><div class="corpus-body">
    <div class="corpus-filter"><input id="corpus-source-search" type="search" placeholder="搜索作者、平台或正文"><button id="corpus-select-visible" type="button">全选当前</button></div><div id="corpus-source-list" class="corpus-source-list"></div>
    <div class="corpus-section"><form id="corpus-create-form" class="corpus-form"><label class="corpus-field">池名称（留空自动命名）<input id="corpus-create-name" maxlength="160"></label><label class="corpus-field">工作区说明<textarea id="corpus-create-description" rows="3" maxlength="4000"></textarea></label><label class="corpus-field">默认 batch size<select id="corpus-create-batch-size"><option>3</option><option>4</option><option selected>6</option><option>8</option><option>10</option><option>12</option></select></label><div class="corpus-actions"><button type="submit" class="primary">把所选来源建成语料池</button><button id="corpus-clear-selection" type="button">清空选择</button></div></form></div>
    <div id="corpus-status" class="corpus-status">选择多条来之不易的来源，建立可持续复用的内容资产。</div>
  </div></aside>
  <section class="corpus-panel"><div class="corpus-head"><div><span class="section-kicker">POOLS</span><h3>语料池工作区</h3></div><button id="corpus-refresh" type="button" class="secondary-action">刷新</button></div><div class="corpus-body"><div id="corpus-pool-list" class="corpus-pool-list"></div></div></section>
  <section class="corpus-panel corpus-detail-panel"><div id="corpus-detail" class="corpus-body"><div class="corpus-empty">选择一个语料池。<br>这里会显示全池主题记忆、成员语料化结果和每日批次。</div></div></section>
</section>`;
    stack.appendChild(view);
    bindWorkspaceEvents();
  }

  function openView() {
    document.querySelectorAll(".app-view").forEach((view) => {
      view.classList.toggle("active", view.id === "corpus-pools-view");
    });
    document.querySelectorAll(".nav-item").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === "corpus-pools-view");
    });
    if (byId("page-title")) byId("page-title").textContent = "语料池";
    loadWorkspace().catch((error) => setStatus(error.message, "error"));
  }

  async function loadWorkspace() {
    const [sources, pools] = await Promise.all([
      api("/api/sources?workspace_state=all"),
      api("/api/corpus-pools?state=all"),
    ]);
    state.sources = sources || [];
    state.pools = pools || [];
    renderSources();
    renderPools();
    if (state.pool?.id) await selectPool(state.pool.id, false);
  }

  function filteredSources() {
    const query = byId("corpus-source-search")?.value.trim().toLowerCase() || "";
    if (!query) return state.sources;
    return state.sources.filter((source) => [
      source.author_name,
      source.author_handle,
      source.platform,
      source.provider,
      source.text_original,
    ].filter(Boolean).some((value) => String(value).toLowerCase().includes(query)));
  }

  function renderSources() {
    const list = byId("corpus-source-list");
    if (!list) return;
    byId("corpus-selected-count").textContent = `${state.selected.size} 条`;
    const sources = filteredSources();
    list.innerHTML = sources.length ? sources.map((source) => `
<label class="corpus-source-row"><input type="checkbox" data-source-id="${html(source.id)}" ${state.selected.has(source.id) ? "checked" : ""}><span class="corpus-source-copy"><strong>${html(sourceTitle(source))}</strong><p>${html(compact(source.text_original, 105))}</p><span class="corpus-source-meta"><span>${html(source.platform || source.provider)}</span><span>${html(source.author_name || source.author_handle || "未知作者")}</span><span>${html(source.workspace_state)}</span></span></span></label>`).join("") : '<div class="corpus-empty">没有匹配的来源</div>';
    list.querySelectorAll("[data-source-id]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selected.add(checkbox.dataset.sourceId);
        else state.selected.delete(checkbox.dataset.sourceId);
        byId("corpus-selected-count").textContent = `${state.selected.size} 条`;
      });
    });
  }

  function renderPools() {
    const list = byId("corpus-pool-list");
    if (!list) return;
    list.innerHTML = state.pools.length ? state.pools.map((pool) => `
<button type="button" class="corpus-pool-card ${pool.id === state.pool?.id ? "active" : ""}" data-pool-id="${html(pool.id)}"><strong>${html(pool.name)}</strong><p>${html(pool.description || compact(pool.profile_text, 90))}</p><span class="corpus-pool-stats"><span>${pool.source_count} 条来源</span><span>${Number(pool.total_chars).toLocaleString()} 字符</span><span>${pool.batch_size}/批</span><span>v${pool.revision}</span></span></button>`).join("") : '<div class="corpus-empty">还没有语料池。<br>从左侧勾选来源创建第一个池。</div>';
    list.querySelectorAll("[data-pool-id]").forEach((button) => {
      button.addEventListener("click", () => selectPool(button.dataset.poolId));
    });
  }

  async function selectPool(poolId, announce = true) {
    state.pool = await api(`/api/corpus-pools/${encodeURIComponent(poolId)}`);
    state.preview = null;
    renderPools();
    renderDetail();
    if (announce) setStatus(`已打开“${state.pool.name}”。`, "ok");
  }

  function previewMarkup() {
    if (!state.preview) return "";
    return `<div class="corpus-preview"><strong>第 ${state.preview.sequence} 批预览：${state.preview.sources.length} 条详细来源</strong><ol>${state.preview.sources.map((source) => `<li>${html(sourceTitle(source))} · ${html(source.platform || source.provider)}</li>`).join("")}</ol><div>其余成员通过全池语义记忆参与主题关联，不在本批重复展开全文。</div></div>`;
  }

  function resultMarkup(batch) {
    if (!batch?.draft) return "";
    return `<div class="corpus-result"><h4>${html(batch.draft.title)}</h4><p>${html(batch.draft.body)}</p><div class="corpus-actions"><button type="button" data-open-anchor="${html(batch.anchor_source_id || "")}">进入完整编辑/制图/审核</button></div></div>`;
  }

  function renderDetail() {
    const node = byId("corpus-detail");
    const pool = state.pool;
    if (!node) return;
    if (!pool) {
      node.innerHTML = '<div class="corpus-empty">选择一个语料池</div>';
      return;
    }
    const latest = (pool.batches || []).find((batch) => batch.draft);
    node.innerHTML = `
<div class="corpus-detail-top"><div><span class="section-kicker">GLOBAL CORPUS MEMORY</span><h2>${html(pool.name)}</h2><p>${html(pool.description || "自动维护的跨来源语义工作区")}</p></div><div class="corpus-actions"><button id="corpus-recompile" type="button">重新语料化</button><button id="corpus-delete" type="button" class="danger">删除池</button></div></div>
<div class="corpus-stat-grid"><div class="corpus-stat"><strong>${pool.source_count}</strong><span>来源</span></div><div class="corpus-stat"><strong>${Number(pool.total_chars).toLocaleString()}</strong><span>语料字符</span></div><div class="corpus-stat"><strong>${pool.batch_size}</strong><span>默认批量</span></div><div class="corpus-stat"><strong>v${pool.revision}</strong><span>全池记忆</span></div></div>
<div class="corpus-keywords">${(pool.topic_keywords || []).map((item) => `<span class="corpus-keyword">${html(item)}</span>`).join("")}</div><pre class="corpus-memory">${html(pool.profile_text)}</pre>
<form id="corpus-settings-form" class="corpus-form"><label class="corpus-field">名称<input id="corpus-name" maxlength="160" value="${html(pool.name)}"></label><label class="corpus-field">说明<textarea id="corpus-description" rows="2" maxlength="4000">${html(pool.description)}</textarea></label><label class="corpus-field">默认 batch size<select id="corpus-batch-size">${sizeOptions(pool.batch_size)}</select></label><div class="corpus-actions"><button type="submit" class="primary">保存工作区</button><button id="corpus-auto-name" type="button">恢复自动命名</button><button id="corpus-add-selected" type="button">加入左侧所选来源</button></div></form>
<div class="corpus-section"><div class="corpus-section-title"><h4>成员语料化结果</h4><span class="count-badge">${pool.members.length} 条</span></div><div class="corpus-member-list">${pool.members.length ? pool.members.map((member) => `<article class="corpus-member"><div><strong>${html(sourceTitle(member.source))}</strong><p>${html(member.summary)}</p><small>${html((member.keywords || []).join(" · "))}｜使用 ${member.used_count} 次｜${html(dateText(member.last_used_at))}</small></div><button type="button" data-remove-source="${html(member.source_id)}">移除</button></article>`).join("") : '<div class="corpus-empty">当前池为空</div>'}</div></div>
<div class="corpus-section"><div class="corpus-section-title"><h4>下一批内容</h4><span class="count-badge">轮换抽样</span></div><div class="corpus-form"><label class="corpus-field">本批聚焦（可留空）<input id="corpus-focus" maxlength="500" placeholder="例如：高压职场里如何识别慢性焦虑"></label><label class="corpus-field">本批详细来源数<select id="corpus-generate-size">${sizeOptions(pool.batch_size)}</select></label><label class="corpus-field">写作类型<select id="corpus-style"><option value="explain">解释拆解</option><option value="news">资讯速览</option><option value="opinion">编辑观察</option></select></label><div class="corpus-actions"><button id="corpus-preview-batch" type="button">预览下一批</button><button id="corpus-generate" type="button" class="primary">从下一批生成</button></div></div><div id="corpus-preview-box">${previewMarkup()}</div><div id="corpus-result-box">${latest ? resultMarkup(latest) : ""}</div></div>
<div class="corpus-section"><div class="corpus-section-title"><h4>批次历史</h4><span class="count-badge">${pool.batches.length} 批</span></div><div class="corpus-batch-list">${pool.batches.length ? pool.batches.map((batch) => `<article class="corpus-batch"><strong>第 ${batch.sequence} 批 · ${batch.sources.length} 条详细来源</strong><p>${html(batch.focus || "自动寻找新角度")}｜全池记忆 v${batch.profile_revision}｜${html(dateText(batch.created_at))}</p>${batch.draft ? `<p><b>${html(batch.draft.title)}</b></p><button type="button" data-open-anchor="${html(batch.anchor_source_id || "")}">在创作工作台打开</button>` : ""}</article>`).join("") : '<div class="corpus-empty">还没有生成批次</div>'}</div></div>`;
    bindDetailEvents();
  }

  function sizeOptions(selected) {
    return [2, 3, 4, 5, 6, 8, 10, 12]
      .map((value) => `<option value="${value}" ${Number(selected) === value ? "selected" : ""}>${value}</option>`)
      .join("");
  }

  function bindWorkspaceEvents() {
    byId("corpus-source-search")?.addEventListener("input", renderSources);
    byId("corpus-refresh")?.addEventListener("click", () => loadWorkspace().catch((error) => setStatus(error.message, "error")));
    byId("corpus-select-visible")?.addEventListener("click", () => {
      filteredSources().forEach((source) => state.selected.add(source.id));
      renderSources();
    });
    byId("corpus-clear-selection")?.addEventListener("click", () => {
      state.selected.clear();
      renderSources();
    });
    byId("corpus-create-form")?.addEventListener("submit", createPool);
  }

  function bindDetailEvents() {
    byId("corpus-settings-form")?.addEventListener("submit", savePool);
    byId("corpus-auto-name")?.addEventListener("click", autoName);
    byId("corpus-add-selected")?.addEventListener("click", addSelected);
    byId("corpus-recompile")?.addEventListener("click", recompile);
    byId("corpus-delete")?.addEventListener("click", removePool);
    byId("corpus-preview-batch")?.addEventListener("click", previewBatch);
    byId("corpus-generate")?.addEventListener("click", generateBatch);
    document.querySelectorAll("[data-remove-source]").forEach((button) => {
      button.addEventListener("click", () => removeSource(button.dataset.removeSource));
    });
    document.querySelectorAll("[data-open-anchor]").forEach((button) => {
      button.addEventListener("click", () => openInWorkbench(button.dataset.openAnchor));
    });
  }

  async function createPool(event) {
    event.preventDefault();
    if (state.busy || !state.selected.size) {
      if (!state.selected.size) setStatus("先在左侧至少选择一条来源。", "error");
      return;
    }
    state.busy = true;
    setStatus(`正在把 ${state.selected.size} 条来源清洗、摘要并编译成全池记忆……`);
    try {
      const pool = await api("/api/corpus-pools", {
        method: "POST",
        body: JSON.stringify({
          source_ids: [...state.selected],
          name: byId("corpus-create-name")?.value || "",
          description: byId("corpus-create-description")?.value || "",
          batch_size: Number(byId("corpus-create-batch-size")?.value || 6),
        }),
      });
      state.pool = pool;
      state.selected.clear();
      await loadWorkspace();
      await selectPool(pool.id, false);
      setStatus(`已创建“${pool.name}”，${pool.source_count} 条来源已转为可复用语料。`, "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      state.busy = false;
    }
  }

  async function savePool(event) {
    event.preventDefault();
    await mutatePool("工作区已保存。", {
      method: "PUT",
      body: JSON.stringify({
        name: byId("corpus-name")?.value || "",
        description: byId("corpus-description")?.value || "",
        batch_size: Number(byId("corpus-batch-size")?.value || state.pool.batch_size),
      }),
    });
  }

  async function autoName() {
    await mutatePool("已按当前语料恢复自动命名。", {
      method: "PUT",
      body: JSON.stringify({ name: "", unlock_name: true }),
    });
  }

  async function addSelected() {
    if (!state.selected.size) {
      setStatus("先在左侧选择要加入的来源。", "error");
      return;
    }
    await mutatePool("所选来源已加入，全池记忆已重新编译。", {
      suffix: "/sources",
      method: "POST",
      body: JSON.stringify({ source_ids: [...state.selected] }),
    });
    state.selected.clear();
    renderSources();
  }

  async function recompile() {
    setStatus("正在重新清洗来源、提取主题并编译全池记忆……");
    await mutatePool("全池记忆已更新。", { suffix: "/compile", method: "POST" });
  }

  async function removeSource(sourceId) {
    await mutatePool("来源已移出，全池记忆已重新编译。", {
      suffix: `/sources/${encodeURIComponent(sourceId)}`,
      method: "DELETE",
    });
  }

  async function mutatePool(successText, options) {
    if (!state.pool || state.busy) return;
    state.busy = true;
    try {
      state.pool = await api(
        `/api/corpus-pools/${encodeURIComponent(state.pool.id)}${options.suffix || ""}`,
        options,
      );
      state.pools = await api("/api/corpus-pools?state=all") || [];
      renderPools();
      renderDetail();
      setStatus(`${successText} 当前为“${state.pool.name}” v${state.pool.revision}。`, "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      state.busy = false;
    }
  }

  async function previewBatch() {
    if (!state.pool || state.busy) return;
    state.busy = true;
    try {
      state.preview = await api(`/api/corpus-pools/${encodeURIComponent(state.pool.id)}/preview-batch`, {
        method: "POST",
        body: JSON.stringify({
          batch_size: Number(byId("corpus-generate-size")?.value || state.pool.batch_size),
          focus: byId("corpus-focus")?.value || "",
        }),
      });
      byId("corpus-preview-box").innerHTML = previewMarkup();
      setStatus("预览按未使用优先、平台和主题多样性计算，不会消耗批次。", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      state.busy = false;
    }
  }

  async function generateBatch() {
    if (!state.pool || state.busy) return;
    state.busy = true;
    const poolId = state.pool.id;
    const button = byId("corpus-generate");
    if (button) {
      button.disabled = true;
      button.textContent = "正在生成批次…";
    }
    setStatus("模型正在读取全池压缩记忆，并只展开本批的详细来源……");
    try {
      const result = await api(`/api/corpus-pools/${encodeURIComponent(poolId)}/drafts`, {
        method: "POST",
        body: JSON.stringify({
          style: byId("corpus-style")?.value || "explain",
          batch_size: Number(byId("corpus-generate-size")?.value || state.pool.batch_size),
          focus: byId("corpus-focus")?.value || "",
        }),
      });
      state.pool = await api(`/api/corpus-pools/${encodeURIComponent(poolId)}`);
      state.pools = await api("/api/corpus-pools?state=all") || [];
      state.preview = null;
      renderPools();
      renderDetail();
      setStatus(`第 ${result.batch.sequence} 批已生成；下次会优先轮换到使用次数更少的来源。`, "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      state.busy = false;
    }
  }

  async function removePool() {
    if (!state.pool || state.busy) return;
    if (!window.confirm(`删除语料池“${state.pool.name}”及批次锚点？原始来源不会删除。`)) return;
    state.busy = true;
    try {
      await api(`/api/corpus-pools/${encodeURIComponent(state.pool.id)}`, { method: "DELETE" });
      state.pool = null;
      await loadWorkspace();
      renderDetail();
      setStatus("语料池已删除，原始来源仍保留在来源箱。", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      state.busy = false;
    }
  }

  async function openInWorkbench(anchorId) {
    if (!anchorId) return;
    document.querySelector('[data-view="workbench-view"]')?.click();
    try {
      if (typeof selectSource === "function") await selectSource(anchorId);
    } catch (error) {
      window.alert(error.message);
    }
  }

  function boot() {
    injectStyles();
    injectNav();
    injectView();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
