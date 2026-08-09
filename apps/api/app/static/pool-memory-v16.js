(() => {
  if (window.__x2redPoolMemoryV16) return;

  const memoryState = {
    items: [],
    candidates: [],
    sources: [],
    usages: [],
    activeCandidate: null,
    activeItem: null,
    pendingSource: null,
    supersedingId: "",
    busy: false,
  };
  window.__x2redPoolMemoryV16 = memoryState;

  const byId = (id) => document.getElementById(id);
  const DIMENSIONS = [
    ["identity", "作者身份"], ["reader_relationship", "读者关系"], ["tone", "语气"],
    ["sentence_rhythm", "句式节奏"], ["paragraph_rhythm", "段落节奏"], ["opening", "开头方式"],
    ["title", "标题方式"], ["structure", "论证结构"], ["transition", "转场"],
    ["judgment", "判断方式"], ["ending", "结尾方式"], ["forbidden_expression", "禁止表达"],
    ["positive_phrase", "正向短例"], ["visual_direction", "视觉方向"], ["layout_preference", "版式偏好"],
  ];
  const SCOPE_FIELDS = [
    ["platforms", "平台", "wechat, xhs"], ["formats", "内容格式", "article, light_series, caption"],
    ["article_types", "文章类型", "technical_explainer"], ["topics", "主题", "AI 工程, 本地部署"],
    ["audiences", "读者", "中文技术读者"], ["recipes", "轻内容配方", "comfort"],
    ["visual_routes", "视觉路线", "minimal_zine"], ["style_profile_ids", "风格档案 ID", "style_xxx"],
  ];

  async function call(path, options = {}) {
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

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function compact(value, limit = 120) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
  }

  function splitValues(value) {
    return [...new Set(String(value || "").split(/[,，\n]+/).map((item) => item.trim()).filter(Boolean))];
  }

  function lineValues(value) {
    return [...new Set(String(value || "").split(/\n+/).map((item) => item.trim()).filter(Boolean))];
  }

  function setStatus(text, type = "") {
    const node = byId("memory-status");
    if (!node) return;
    node.textContent = text;
    node.className = `memory-status ${type}`.trim();
  }

  function dimensionsMarkup(prefix, selected = ["opening", "sentence_rhythm", "structure", "judgment"]) {
    return DIMENSIONS.map(([id, label]) => `<label class="memory-check"><input type="checkbox" name="${prefix}-dimension" value="${id}" ${selected.includes(id) ? "checked" : ""}><span>${label}</span></label>`).join("");
  }

  function scopeMarkup(prefix) {
    return SCOPE_FIELDS.map(([id, label, placeholder]) => `<label class="memory-field">${label}<input id="${prefix}-${id}" placeholder="${placeholder}"><small>留空表示不限制该维度；多个值用逗号分隔。</small></label>`).join("");
  }

  function injectNav() {
    if (document.querySelector('[data-view="pool-memory-view"]')) return;
    const nav = document.querySelector(".primary-nav");
    if (!nav) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "nav-item";
    button.dataset.view = "pool-memory-view";
    button.innerHTML = '<span class="nav-icon">笔</span><span>写作偏好</span>';
    button.addEventListener("click", () => { void openView(); });
    const anchor = nav.querySelector('[data-view="style-lab-view"]') || nav.querySelector('[data-view="settings-view"]');
    nav.insertBefore(button, anchor || null);
  }

  function injectView() {
    if (byId("pool-memory-view")) return;
    const stack = document.querySelector(".view-stack");
    if (!stack) return;
    const view = document.createElement("section");
    view.id = "pool-memory-view";
    view.className = "app-view";
    view.innerHTML = `
<section class="page-intro"><span class="section-kicker">WRITING PREFERENCES · HUMAN GATED</span><h2>写作偏好</h2><p>这里只保存经你批准的表达经验：怎么开头、组织、判断和收束。它不提供事实，也不能代替任务里明确选择的来源。</p></section>
<section class="memory-shell">
  <div class="memory-principles"><article class="memory-principle"><strong>记忆决定“怎么写”，证据决定“能写什么”</strong><p>历史文章中的人名、数字、日期、结果与因果不能成为新文章事实。候选必须经过预览和人工批准。</p></article><article class="memory-stat"><strong id="memory-approved-count">0</strong><span>有效记忆</span></article><article class="memory-stat"><strong id="memory-candidate-count">0</strong><span>待批准候选</span></article><article class="memory-stat"><strong id="memory-usage-count">0</strong><span>角色使用记录</span></article></div>
  <div class="memory-grid">
    <section class="memory-panel"><div class="memory-panel-head"><div><span class="section-kicker">ADD MEMORY</span><h3>生成或手工建立记忆</h3></div><button id="memory-refresh" class="secondary-action" type="button">刷新</button></div><div class="memory-panel-body">
      <div class="memory-tabs"><button type="button" class="active" data-memory-tab="source">从内容提炼</button><button type="button" data-memory-tab="manual">手工规则</button></div>
      <section id="memory-source-pane" class="memory-tab-pane"><form id="memory-source-form" class="memory-form"><label class="memory-field">来源<select id="memory-source-select"><option value="">选择已生成文章、平台版本、反馈或模式卡</option></select><small id="memory-source-eligibility">候选不会自动进入正式池子。</small></label><label class="memory-field">候选标题<input id="memory-source-title" maxlength="160" placeholder="留空使用原内容标题"></label><div class="memory-field">学习维度<div class="memory-check-grid">${dimensionsMarkup("source")}</div></div><details><summary>适用范围</summary><div class="memory-form">${scopeMarkup("source-scope")}</div></details><label class="memory-field">提炼备注<textarea id="memory-source-note" rows="3" maxlength="3000" placeholder="希望长期学习什么；不要把本文事实变成通用规则"></textarea></label><label class="memory-field">使用策略<select id="memory-source-policy"><option value="style_and_structure_only">风格与结构</option><option value="abstract_pattern_only">只存抽象模式</option><option value="visual_only">只存视觉方向</option></select></label><div class="memory-actions"><button class="primary" type="submit">生成待批准候选</button></div></form></section>
      <section id="memory-manual-pane" class="memory-tab-pane" hidden><form id="memory-manual-form" class="memory-form"><label class="memory-field">记忆名称<input id="memory-manual-title" required maxlength="160"></label><div class="memory-field">学习维度<div class="memory-check-grid">${dimensionsMarkup("manual", ["tone", "opening", "judgment", "forbidden_expression"])}</div></div><label class="memory-field">规则（每行一条）<textarea id="memory-manual-rules" rows="4"></textarea></label><label class="memory-field">禁止表达（每行一条）<textarea id="memory-manual-avoid" rows="3"></textarea></label><label class="memory-field">偏好（每行一条）<textarea id="memory-manual-prefer" rows="3"></textarea></label><label class="memory-field">结构步骤（每行一条）<textarea id="memory-manual-structure" rows="3"></textarea></label><label class="memory-field">视觉方向（每行一条）<textarea id="memory-manual-visual" rows="3"></textarea></label><details><summary>适用范围</summary><div class="memory-form">${scopeMarkup("manual-scope")}</div></details><label class="memory-field">备注<textarea id="memory-manual-note" rows="2" maxlength="3000"></textarea></label><label class="memory-confirm"><input id="memory-manual-confirm" type="checkbox"><span>确认这条规则和短例由我原创、系统生成且已批准，或已获得用于风格参考的授权。</span></label><div class="memory-actions"><button id="memory-manual-submit" class="primary" type="submit">批准并加入池子</button><button id="memory-cancel-supersede" type="button" hidden>取消替代</button></div></form></section>
      <div id="memory-status" class="memory-status">所有正式记忆都需要明确的人类批准；模型提炼只生成候选。</div>
    </div></section>
    <section class="memory-panel"><div class="memory-panel-head"><div><span class="section-kicker">CANDIDATE REVIEW</span><h3>候选预览与批准</h3></div><span id="memory-candidate-badge" class="count-badge">0 条</span></div><div class="memory-panel-body"><div id="memory-candidate-list" class="memory-list"></div><div id="memory-candidate-detail" class="memory-detail"><div class="memory-detail-empty">选择一条候选。<br>可以修改规则、维度和适用范围，再决定是否进入正式池子。</div></div></div></section>
    <section class="memory-panel"><div class="memory-panel-head"><div><span class="section-kicker">APPROVED + TRACE</span><h3>有效记忆与影响链路</h3></div><label class="memory-confirm"><input id="memory-show-inactive" type="checkbox"><span>显示已替代/撤销</span></label></div><div class="memory-panel-body">
      <section class="memory-section"><div class="memory-subtitle"><h4>任务检索预览</h4><span class="count-badge">4—8 条</span></div><div class="memory-toolbar"><select id="memory-preview-platform"><option value="wechat">公众号</option><option value="xhs">小红书</option></select><select id="memory-preview-format"><option value="article">长文</option><option value="light_series">轻内容</option><option value="caption">短内容</option></select><input id="memory-preview-type" placeholder="文章类型"><input id="memory-preview-topic" placeholder="主题或来源摘要"><button id="memory-preview-run" type="button" class="secondary-action">预览</button></div><div id="memory-preview-results" class="memory-preview-results"></div></section>
      <section class="memory-section"><div class="memory-subtitle"><h4>已批准记忆</h4><span id="memory-item-badge" class="count-badge">0 条</span></div><div id="memory-item-list" class="memory-list"></div><div id="memory-item-detail" class="memory-detail"></div></section>
      <section class="memory-section"><div class="memory-subtitle"><h4>最近使用记录</h4><span class="count-badge">不可变快照</span></div><div id="memory-usage-list"></div></section>
    </div></section>
  </div>
</section>`;
    stack.appendChild(view);
    bindEvents();
  }

  async function openView() {
    if (window.setView) window.setView("pool-memory-view");
    else {
      document.querySelectorAll(".app-view").forEach((view) => view.classList.toggle("active", view.id === "pool-memory-view"));
      document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === "pool-memory-view"));
    }
    await loadWorkspace();
    applyPendingSource();
  }

  async function loadWorkspace() {
    const includeInactive = byId("memory-show-inactive")?.checked ? "true" : "false";
    const [items, candidates, sources, usages] = await Promise.all([
      call(`/api/pool-memory/items?include_inactive=${includeInactive}&limit=300`),
      call("/api/pool-memory/candidates?limit=200"),
      call("/api/pool-memory/source-options?limit=200"),
      call("/api/pool-memory/usages?limit=200"),
    ]);
    memoryState.items = items || [];
    memoryState.candidates = candidates || [];
    memoryState.sources = sources || [];
    memoryState.usages = usages || [];
    renderStats();
    renderSources();
    renderCandidates();
    renderItems();
    renderUsages();
  }

  function renderStats() {
    byId("memory-approved-count").textContent = String(memoryState.items.filter((item) => !item.revoked && !item.superseded).length);
    byId("memory-candidate-count").textContent = String(memoryState.candidates.length);
    byId("memory-usage-count").textContent = String(memoryState.usages.length);
    byId("memory-candidate-badge").textContent = `${memoryState.candidates.length} 条`;
    byId("memory-item-badge").textContent = `${memoryState.items.length} 条`;
  }

  function renderSources() {
    const select = byId("memory-source-select");
    if (!select) return;
    const current = select.value;
    select.innerHTML = '<option value="">选择已生成文章、平台版本、反馈或模式卡</option>';
    const groups = new Map();
    const labels = { draft_revision: "小红书草稿", platform_variant: "平台版本", writing_feedback: "真实改稿反馈", pattern_card: "模式卡", writing_artifact: "多 Agent 终稿" };
    memoryState.sources.forEach((item) => {
      if (!groups.has(item.kind)) {
        const group = document.createElement("optgroup");
        group.label = labels[item.kind] || item.kind;
        groups.set(item.kind, group);
        select.appendChild(group);
      }
      const option = new Option(`${item.eligible ? "✓" : "○"} ${item.label}`, `${item.kind}:${item.id}`);
      option.dataset.eligible = String(Boolean(item.eligible));
      option.dataset.reason = item.eligibility_reason || "";
      option.dataset.platform = item.platform || "";
      option.dataset.format = item.format || "";
      groups.get(item.kind).appendChild(option);
    });
    if ([...select.options].some((option) => option.value === current)) select.value = current;
    updateSourceHint();
  }

  function renderCandidates() {
    const list = byId("memory-candidate-list");
    if (!list) return;
    if (!memoryState.candidates.length) {
      list.innerHTML = '<div class="memory-detail-empty">还没有待批准候选。<br>从左侧选择一篇内容或一条真实反馈开始。</div>';
      renderCandidateDetail(null);
      return;
    }
    list.innerHTML = memoryState.candidates.map((item) => `<article class="memory-card ${memoryState.activeCandidate?.id === item.id ? "active" : ""}"><button type="button" class="memory-card-open" data-candidate-id="${escapeHtml(item.id)}"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(compact([...(item.memory.rules || []), ...(item.memory.avoid || [])].join("；"), 130))}</p><span class="memory-card-meta"><span class="memory-chip warn">待人工批准</span><span class="memory-chip">${escapeHtml(item.source.kind || "来源")}</span><span class="memory-chip">${escapeHtml(item.extraction_mode || "候选")}</span></span></button></article>`).join("");
    list.querySelectorAll("[data-candidate-id]").forEach((button) => button.addEventListener("click", () => {
      memoryState.activeCandidate = memoryState.candidates.find((item) => item.id === button.dataset.candidateId) || null;
      renderCandidates();
      renderCandidateDetail(memoryState.activeCandidate);
    }));
    if (memoryState.activeCandidate) renderCandidateDetail(memoryState.activeCandidate);
  }

  function scopeInputs(prefix, scope = {}) {
    SCOPE_FIELDS.forEach(([key]) => {
      const input = byId(`${prefix}-${key}`);
      if (input) input.value = (scope[key] || []).join(", ");
    });
  }

  function scopePayload(prefix) {
    return Object.fromEntries(SCOPE_FIELDS.map(([key]) => [key, splitValues(byId(`${prefix}-${key}`)?.value)]));
  }

  function selectedDimensions(prefix) {
    return [...document.querySelectorAll(`input[name="${prefix}-dimension"]:checked`)].map((input) => input.value);
  }

  function renderCandidateDetail(item) {
    const root = byId("memory-candidate-detail");
    if (!root) return;
    if (!item) {
      root.innerHTML = '<div class="memory-detail-empty">选择一条候选。<br>候选可以编辑，但不能绕过人工批准。</div>';
      return;
    }
    root.innerHTML = `<form id="memory-candidate-form" class="memory-form"><label class="memory-field">名称<input id="candidate-title" maxlength="160" value="${escapeHtml(item.title)}"></label><div class="memory-field">学习维度<div class="memory-check-grid">${dimensionsMarkup("candidate", item.dimensions)}</div></div><label class="memory-field">规则（每行一条）<textarea id="candidate-rules" rows="4">${escapeHtml((item.memory.rules || []).join("\n"))}</textarea></label><label class="memory-field">禁止表达<textarea id="candidate-avoid" rows="3">${escapeHtml((item.memory.avoid || []).join("\n"))}</textarea></label><label class="memory-field">偏好<textarea id="candidate-prefer" rows="3">${escapeHtml((item.memory.prefer || []).join("\n"))}</textarea></label><label class="memory-field">结构步骤<textarea id="candidate-structure" rows="3">${escapeHtml((item.memory.structure || []).join("\n"))}</textarea></label><label class="memory-field">视觉方向<textarea id="candidate-visual" rows="3">${escapeHtml((item.memory.visual_directions || []).join("\n"))}</textarea></label><details><summary>适用范围</summary><div class="memory-form">${scopeMarkup("candidate-scope")}</div></details><label class="memory-field">备注<textarea id="candidate-note" rows="2">${escapeHtml(item.note || "")}</textarea></label><label class="memory-confirm"><input id="candidate-authorized" type="checkbox"><span>${escapeHtml(item.eligibility?.reason || "确认来源可用于风格学习")}。若来源尚未批准，必须在这里显式确认原创或授权。</span></label><div class="memory-actions"><button type="submit">保存为新候选版本</button><button id="candidate-approve" type="button" class="primary">人工批准并进入池子</button></div></form>`;
    scopeInputs("candidate-scope", item.scope);
    byId("memory-candidate-form")?.addEventListener("submit", (event) => { void updateCandidate(event); });
    byId("candidate-approve")?.addEventListener("click", () => { void approveCandidate(); });
  }

  function candidateMemory(prefix) {
    return {
      rules: lineValues(byId(`${prefix}-rules`)?.value),
      avoid: lineValues(byId(`${prefix}-avoid`)?.value),
      prefer: lineValues(byId(`${prefix}-prefer`)?.value),
      positive_examples: prefix === "candidate"
        ? memoryState.activeCandidate?.memory?.positive_examples || []
        : [],
      structure: lineValues(byId(`${prefix}-structure`)?.value),
      visual_directions: lineValues(byId(`${prefix}-visual`)?.value),
    };
  }

  async function createCandidate(event) {
    event.preventDefault();
    if (memoryState.busy) return;
    const value = byId("memory-source-select")?.value || "";
    const split = value.indexOf(":");
    if (split < 1) { setStatus("先选择一条来源。", "error"); return; }
    const dimensions = selectedDimensions("source");
    if (!dimensions.length) { setStatus("至少选择一个学习维度。", "error"); return; }
    memoryState.busy = true;
    setStatus("正在提炼候选；它不会自动进入正式池子……");
    try {
      const candidate = await call("/api/pool-memory/candidates", {
        method: "POST",
        body: JSON.stringify({
          source_kind: value.slice(0, split), source_id: value.slice(split + 1),
          title: byId("memory-source-title")?.value || "", dimensions,
          scope: scopePayload("source-scope"), usage_policy: byId("memory-source-policy")?.value,
          note: byId("memory-source-note")?.value || "",
        }),
      });
      await loadWorkspace();
      memoryState.activeCandidate = memoryState.candidates.find((item) => item.id === candidate.id) || null;
      renderCandidates();
      renderCandidateDetail(memoryState.activeCandidate);
      setStatus("候选已生成。请检查、编辑并明确批准。", "ok");
    } catch (error) { setStatus(error.message, "error"); }
    finally { memoryState.busy = false; }
  }

  async function updateCandidate(event) {
    event.preventDefault();
    const item = memoryState.activeCandidate;
    if (!item || memoryState.busy) return;
    memoryState.busy = true;
    try {
      const revised = await call(`/api/pool-memory/candidates/${encodeURIComponent(item.id)}`, {
        method: "PUT",
        body: JSON.stringify({
          title: byId("candidate-title")?.value || item.title,
          dimensions: selectedDimensions("candidate"), scope: scopePayload("candidate-scope"),
          memory: candidateMemory("candidate"), usage_policy: item.usage_policy,
          note: byId("candidate-note")?.value || "",
        }),
      });
      await loadWorkspace();
      memoryState.activeCandidate = memoryState.candidates.find((value) => value.id === revised.id) || null;
      renderCandidates(); renderCandidateDetail(memoryState.activeCandidate);
      setStatus("候选修改已作为新版本保存；旧候选仍保留历史。", "ok");
    } catch (error) { setStatus(error.message, "error"); }
    finally { memoryState.busy = false; }
  }

  async function approveCandidate() {
    const item = memoryState.activeCandidate;
    if (!item || memoryState.busy) return;
    memoryState.busy = true;
    try {
      await call(`/api/pool-memory/candidates/${encodeURIComponent(item.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({
          review_note: byId("candidate-note")?.value || "",
          confirm_source_authorized: Boolean(byId("candidate-authorized")?.checked),
        }),
      });
      memoryState.activeCandidate = null;
      await loadWorkspace();
      setStatus("记忆已由你批准并进入正式池子。", "ok");
    } catch (error) { setStatus(error.message, "error"); }
    finally { memoryState.busy = false; }
  }

  async function submitManual(event) {
    event.preventDefault();
    if (memoryState.busy) return;
    const payload = {
      title: byId("memory-manual-title")?.value || "",
      dimensions: selectedDimensions("manual"), scope: scopePayload("manual-scope"),
      memory: candidateMemory("memory-manual"), usage_policy: "style_and_structure_only",
      note: byId("memory-manual-note")?.value || "",
    };
    memoryState.busy = true;
    try {
      if (memoryState.supersedingId) {
        const reason = window.prompt("请说明为什么用新记忆替代旧记忆：", "规则已更新") || "";
        if (!reason.trim()) throw new Error("替代记忆必须说明原因");
        await call(`/api/pool-memory/items/${encodeURIComponent(memoryState.supersedingId)}/supersede`, {
          method: "POST", body: JSON.stringify({ ...payload, reason }),
        });
        cancelSupersede();
        setStatus("新记忆已建立；旧记忆保留历史，但不再进入新检索。", "ok");
      } else {
        await call("/api/pool-memory/items", {
          method: "POST",
          body: JSON.stringify({ ...payload, confirm_original_or_authorized: Boolean(byId("memory-manual-confirm")?.checked) }),
        });
        setStatus("手工记忆已批准并加入池子。", "ok");
      }
      byId("memory-manual-form")?.reset();
      await loadWorkspace();
    } catch (error) { setStatus(error.message, "error"); }
    finally { memoryState.busy = false; }
  }

  function renderItems() {
    const list = byId("memory-item-list");
    if (!list) return;
    if (!memoryState.items.length) {
      list.innerHTML = '<div class="memory-detail-empty">还没有正式记忆。</div>';
      renderItemDetail(null); return;
    }
    list.innerHTML = memoryState.items.map((item) => `<article class="memory-card ${memoryState.activeItem?.id === item.id ? "active" : ""}"><button type="button" class="memory-card-open" data-memory-id="${escapeHtml(item.id)}"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(compact([...(item.memory.rules || []), ...(item.memory.avoid || [])].join("；"), 140))}</p><span class="memory-card-meta"><span class="memory-chip ${item.revoked || item.superseded ? "warn" : "good"}">${item.revoked ? "已撤销" : item.superseded ? "已替代" : "有效"}</span><span class="memory-chip">引用 ${item.usage_count} 次</span><span class="memory-chip">${item.legacy ? "旧语料兼容" : escapeHtml(item.source.kind || "记忆")}</span></span></button></article>`).join("");
    list.querySelectorAll("[data-memory-id]").forEach((button) => button.addEventListener("click", () => {
      memoryState.activeItem = memoryState.items.find((item) => item.id === button.dataset.memoryId) || null;
      renderItems(); renderItemDetail(memoryState.activeItem);
    }));
    if (memoryState.activeItem) renderItemDetail(memoryState.activeItem);
  }

  function listBlock(title, values) {
    if (!values?.length) return "";
    return `<article class="memory-content-block"><h4>${escapeHtml(title)}</h4><ul>${values.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : `${item.text || ""} · ${item.lesson || ""}`)}</li>`).join("")}</ul></article>`;
  }

  function renderItemDetail(item) {
    const root = byId("memory-item-detail");
    if (!root) return;
    if (!item) { root.innerHTML = ""; return; }
    const scopes = Object.entries(item.scope || {}).filter(([, values]) => values?.length).map(([key, values]) => `${key}: ${values.join(" / ")}`).join(" · ");
    root.innerHTML = `<div class="memory-detail"><div><strong>${escapeHtml(item.title)}</strong><p class="memory-scope-line">${escapeHtml(scopes || "全局范围")}<br>来源：${escapeHtml(item.source.label || item.source.id || item.source.kind)} · ${escapeHtml(item.usage_policy)}</p></div>${listBlock("规则", item.memory.rules)}${listBlock("避免", item.memory.avoid)}${listBlock("偏好", item.memory.prefer)}${listBlock("结构", item.memory.structure)}${listBlock("视觉", item.memory.visual_directions)}${listBlock("短例与学习点", item.memory.positive_examples)}<div class="memory-actions"><button type="button" id="memory-supersede" ${item.revoked || item.superseded ? "disabled" : ""}>用新记忆替代</button><button type="button" id="memory-revoke" class="danger" ${item.revoked || item.superseded ? "disabled" : ""}>撤销但保留历史</button></div></div>`;
    byId("memory-supersede")?.addEventListener("click", () => beginSupersede(item));
    byId("memory-revoke")?.addEventListener("click", () => { void revokeItem(item); });
  }

  function beginSupersede(item) {
    memoryState.supersedingId = item.id;
    switchTab("manual");
    byId("memory-manual-title").value = item.title;
    byId("memory-manual-rules").value = (item.memory.rules || []).join("\n");
    byId("memory-manual-avoid").value = (item.memory.avoid || []).join("\n");
    byId("memory-manual-prefer").value = (item.memory.prefer || []).join("\n");
    byId("memory-manual-structure").value = (item.memory.structure || []).join("\n");
    byId("memory-manual-visual").value = (item.memory.visual_directions || []).join("\n");
    scopeInputs("manual-scope", item.scope);
    document.querySelectorAll('input[name="manual-dimension"]').forEach((input) => { input.checked = item.dimensions.includes(input.value); });
    byId("memory-manual-submit").textContent = "建立替代记忆";
    byId("memory-cancel-supersede").hidden = false;
    setStatus("正在建立替代记忆：旧记录不会删除，但新任务将忽略它。", "ok");
  }

  function cancelSupersede() {
    memoryState.supersedingId = "";
    if (byId("memory-manual-submit")) byId("memory-manual-submit").textContent = "批准并加入池子";
    if (byId("memory-cancel-supersede")) byId("memory-cancel-supersede").hidden = true;
  }

  async function revokeItem(item) {
    const reason = window.prompt("说明撤销原因（历史会保留）：", "这条规则不再适用") || "";
    if (!reason.trim()) return;
    try {
      await call(`/api/pool-memory/items/${encodeURIComponent(item.id)}/revoke`, { method: "POST", body: JSON.stringify({ reason }) });
      memoryState.activeItem = null; await loadWorkspace(); setStatus("记忆已撤销；历史和使用记录仍保留。", "ok");
    } catch (error) { setStatus(error.message, "error"); }
  }

  async function previewRetrieval() {
    try {
      const result = await call("/api/pool-memory/retrieve-preview", {
        method: "POST",
        body: JSON.stringify({ platform: byId("memory-preview-platform")?.value, format: byId("memory-preview-format")?.value, article_type: byId("memory-preview-type")?.value || "", source_text: byId("memory-preview-topic")?.value || "", topics: splitValues(byId("memory-preview-topic")?.value), limit: 6, max_chars: 6000 }),
      });
      const root = byId("memory-preview-results");
      root.innerHTML = `${(result.items || []).map((row) => `<article class="memory-preview-item"><strong>${escapeHtml(row.item.title)} · ${Number(row.score).toFixed(2)}</strong><p>${escapeHtml(row.reasons.join(" · "))}</p></article>`).join("") || '<div class="memory-status">当前条件没有命中正式记忆。</div>'}<pre class="memory-prompt-preview">${escapeHtml(result.prompt_preview)}</pre>`;
    } catch (error) { setStatus(error.message, "error"); }
  }

  function renderUsages() {
    const root = byId("memory-usage-list");
    if (!root) return;
    root.innerHTML = memoryState.usages.length ? memoryState.usages.slice(0, 40).map((usage) => `<article class="memory-usage-row"><div><strong>${escapeHtml(usage.agent_role || "生成器")} · ${escapeHtml(usage.stage || "阶段")}</strong><br><span>${escapeHtml(usage.target_type)} / ${escapeHtml(usage.target_id)}</span></div><span>${Number(usage.score).toFixed(2)}</span></article>`).join("") : '<div class="memory-status">还没有模型实际消费记忆。未配置模型的回退输出不会记为使用。</div>';
  }

  function switchTab(tab) {
    document.querySelectorAll("[data-memory-tab]").forEach((button) => button.classList.toggle("active", button.dataset.memoryTab === tab));
    byId("memory-source-pane").hidden = tab !== "source";
    byId("memory-manual-pane").hidden = tab !== "manual";
  }

  function updateSourceHint() {
    const option = byId("memory-source-select")?.selectedOptions?.[0];
    if (!option?.value) { byId("memory-source-eligibility").textContent = "候选不会自动进入正式池子。"; return; }
    byId("memory-source-eligibility").textContent = option.dataset.reason || "批准时需要确认授权状态。";
    if (option.dataset.platform) byId("source-scope-platforms").value = option.dataset.platform;
    if (option.dataset.format) byId("source-scope-formats").value = option.dataset.format;
    if (option.value.startsWith("pattern_card:")) byId("memory-source-policy").value = "abstract_pattern_only";
  }

  function applyPendingSource() {
    if (!memoryState.pendingSource) return;
    const value = `${memoryState.pendingSource.kind}:${memoryState.pendingSource.id}`;
    const select = byId("memory-source-select");
    if (select && [...select.options].some((option) => option.value === value)) {
      select.value = value; updateSourceHint(); switchTab("source");
      setStatus("已带入当前内容。选择学习维度后生成候选。", "ok");
    }
    memoryState.pendingSource = null;
  }

  async function openWithSource(kind, id) {
    if (!kind || !id) return;
    memoryState.pendingSource = { kind, id };
    await openView();
  }

  function injectEntrypoints() {
    const draftFooter = document.querySelector("#draft-form .editor-footer");
    if (draftFooter && !byId("memory-from-draft")) {
      const button = document.createElement("button");
      button.id = "memory-from-draft"; button.type = "button"; button.className = "secondary-action"; button.textContent = "提炼为写作偏好";
      button.addEventListener("click", () => {
        let draft = null;
        try { draft = typeof state !== "undefined" ? state.currentDraft : null; } catch {}
        if (!draft?.id) { setStatus("当前还没有可提炼的草稿。", "error"); return; }
        void openWithSource("draft_revision", draft.id);
      });
      draftFooter.insertBefore(button, draftFooter.lastElementChild);
    }
    document.querySelectorAll("[data-memory-source-kind][data-memory-source-id]").forEach((button) => {
      if (button.dataset.memoryBound === "true") return;
      button.dataset.memoryBound = "true";
      button.addEventListener("click", () => { void openWithSource(button.dataset.memorySourceKind, button.dataset.memorySourceId); });
    });
  }

  function bindEvents() {
    document.querySelectorAll("[data-memory-tab]").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.memoryTab)));
    byId("memory-refresh")?.addEventListener("click", () => { void loadWorkspace(); });
    byId("memory-source-select")?.addEventListener("change", updateSourceHint);
    byId("memory-source-form")?.addEventListener("submit", (event) => { void createCandidate(event); });
    byId("memory-manual-form")?.addEventListener("submit", (event) => { void submitManual(event); });
    byId("memory-cancel-supersede")?.addEventListener("click", cancelSupersede);
    byId("memory-show-inactive")?.addEventListener("change", () => { void loadWorkspace(); });
    byId("memory-preview-run")?.addEventListener("click", () => { void previewRetrieval(); });
  }

  function boot() {
    injectNav(); injectView(); injectEntrypoints();
    document.addEventListener("x2red:memory-source", (event) => {
      const detail = event.detail || {};
      void openWithSource(detail.kind, detail.id);
    });
    const observer = new MutationObserver(() => { injectNav(); injectView(); injectEntrypoints(); });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
