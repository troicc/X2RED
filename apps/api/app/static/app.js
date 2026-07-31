const state = {
  sourceId: null,
  draftId: null,
  currentSource: null,
  currentDraft: null,
  currentCardRender: null,
  activeJobId: null,
  sourceItems: [],
  health: null,
};

const $ = (id) => document.getElementById(id);
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function parseJSON(value, fallback) {
  try {
    const parsed = JSON.parse(value || "");
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function message(element, text, type = "") {
  if (!element) return;
  element.textContent = text;
  element.className = `inline-status ${type}`.trim();
}

function formatDate(value) {
  if (!value) return "刚刚归档";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "已归档";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function initials(item) {
  const seed = (item.author_name || item.author_handle || "X").trim();
  return [...seed][0]?.toUpperCase() || "X";
}

function rightsLabel(value) {
  return {
    needs_review: "待确认",
    limited_quote: "有限引用",
    owned: "自有",
    licensed: "已授权",
    open_license: "开放许可",
    do_not_publish: "禁止发布",
  }[value] || value || "待确认";
}

function kindLabel(value) {
  return {
    cover: "封面",
    thesis: "推荐角度",
    facts: "来源事实",
    caution: "核查边界",
    source: "来源页",
    content: "内容页",
  }[value] || "内容页";
}

function setView(viewId) {
  document.querySelectorAll(".app-view").forEach((view) => {
    view.classList.toggle("active", view.id === viewId);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
  const titles = {
    "workbench-view": "创作工作台",
    "publish-view": "发布任务",
    "settings-view": "模型与设置",
  };
  $("page-title").textContent = titles[viewId] || "X2RED";
  if (viewId === "publish-view") loadPublish();
}

function setTab(paneId) {
  document.querySelectorAll(".stage-pane").forEach((pane) => {
    pane.classList.toggle("active", pane.id === paneId);
  });
  document.querySelectorAll(".stage-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === paneId);
  });
}

async function loadHealth() {
  try {
    const data = await api("/health");
    state.health = data;
    $("health").textContent = `${data.name} ${data.version} · 本地运行`;
    $("health").className = "status-chip ok";
    const configured = Boolean(data.model_configured);
    $("model-status").textContent = configured ? `${data.model_name || "AI"} 已连接` : "未配置 AI";
    $("model-status").className = `status-chip ${configured ? "ok" : "error"}`;
    $("settings-model-name").textContent = configured ? data.model_name || "已配置模型" : "未配置模型";
    $("settings-model-copy").textContent = configured
      ? "生成草稿会执行编辑分析、成稿和去翻译味三次模型调用。"
      : "当前只能生成规则化兜底稿。请在 .env 中配置 GLM-5.2 或其他兼容模型。";
  } catch {
    $("health").textContent = "服务不可用";
    $("health").className = "status-chip error";
    $("model-status").textContent = "AI 状态未知";
    $("model-status").className = "status-chip error";
  }
}

async function loadSources(selectId = null) {
  const items = await api("/api/sources");
  state.sourceItems = items;
  renderSourceList();
  if (selectId) await selectSource(selectId);
}

function renderSourceList() {
  const query = $("source-search").value.trim().toLowerCase();
  const list = $("source-list");
  list.replaceChildren();
  const items = state.sourceItems.filter((item) => {
    if (!query) return true;
    return [item.author_name, item.author_handle, item.text_original]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(query));
  });
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "workbench-empty";
    empty.style.minHeight = "180px";
    empty.textContent = query ? "没有匹配的来源" : "来源箱还是空的";
    list.appendChild(empty);
    return;
  }
  for (const item of items) {
    const node = $("source-template").content.cloneNode(true);
    const button = node.querySelector("button");
    button.dataset.id = item.id;
    button.classList.toggle("active", item.id === state.sourceId);
    node.querySelector(".source-mini-avatar").textContent = initials(item);
    node.querySelector(".source-name").textContent = item.author_handle
      ? `@${item.author_handle}`
      : item.author_name || "未知作者";
    node.querySelector(".source-date").textContent = formatDate(item.captured_at);
    node.querySelector(".source-preview").textContent = item.text_original || "（无正文）";
    node.querySelector(".source-rights").textContent = rightsLabel(item.rights_status);
    const dot = node.querySelector(".source-state-dot");
    dot.classList.toggle("ready", item.state === "available");
    button.addEventListener("click", () => selectSource(item.id));
    list.appendChild(node);
  }
}

async function selectSource(id) {
  state.sourceId = id;
  state.draftId = null;
  state.currentDraft = null;
  renderSourceList();
  const item = await api(`/api/sources/${encodeURIComponent(id)}`);
  state.currentSource = item;
  $("empty-workbench").hidden = true;
  $("active-workbench").hidden = false;
  renderSourceDetail(item);
  await loadDrafts(id);
  setTab("source-pane");
}

function renderSourceDetail(item) {
  $("source-avatar").textContent = initials(item);
  $("source-author").textContent = item.author_handle
    ? `${item.author_name || item.author_handle} · @${item.author_handle}`
    : item.author_name || "未知作者";
  $("source-link").href = item.canonical_url;
  $("source-text").textContent = item.text_original || "（无正文）";
  $("source-rights-badge").textContent = rightsLabel(item.rights_status);
  $("rights-status").value = item.rights_status || "needs_review";
  $("rights-note").value = item.rights_note || "";
  const assetStates = new Set((item.assets || []).map((asset) => asset.rights_status));
  $("asset-rights-status").value = assetStates.size === 1 ? [...assetStates][0] : "needs_review";
  renderAssets(item.assets || []);
  renderRelated(item.related || []);
  message($("rights-status-message"), `当前文本状态：${rightsLabel(item.rights_status)}`);
}

function renderRelated(items) {
  $("related-count").textContent = `${items.length} 条上下文`;
  const box = $("related");
  box.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "related-item";
    empty.textContent = "当前未加载额外 Thread 或对话上下文。";
    box.appendChild(empty);
    return;
  }
  items.slice(0, 12).forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "related-item";
    row.textContent = `${String(index + 1).padStart(2, "0")} · ${item.text_original || "（无正文）"}`;
    box.appendChild(row);
  });
}

function renderAssets(assets) {
  const box = $("assets");
  box.replaceChildren();
  if (!assets.length) {
    const empty = document.createElement("div");
    empty.className = "card-empty";
    empty.style.minHeight = "160px";
    empty.textContent = "这条来源没有可用媒体";
    box.appendChild(empty);
    return;
  }
  for (const asset of assets) {
    const wrap = document.createElement("article");
    wrap.className = "asset";
    const url = asset.local_path
      ? `/api/assets/${encodeURIComponent(asset.id)}/file`
      : asset.remote_url;
    const media = document.createElement(asset.kind === "image" ? "img" : "video");
    media.src = url;
    if (asset.kind === "image") media.alt = asset.alt_text || "来源图片";
    else media.controls = true;
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    const stateSpan = document.createElement("span");
    stateSpan.textContent = asset.state;
    const rightsSpan = document.createElement("strong");
    rightsSpan.textContent = rightsLabel(asset.rights_status);
    meta.append(stateSpan, rightsSpan);
    wrap.append(media, meta);
    if (asset.error || asset.rights_note) {
      wrap.title = [asset.error, asset.rights_note].filter(Boolean).join("\n");
    }
    box.appendChild(wrap);
  }
}

async function loadDrafts(sourceId) {
  const drafts = await api(`/api/sources/${encodeURIComponent(sourceId)}/drafts`);
  if (!drafts.length) {
    state.currentDraft = null;
    state.draftId = null;
    $("empty-editor").hidden = false;
    $("draft-form").hidden = true;
    renderAnalysis(null);
    renderCards(null);
    return;
  }
  showDraft(drafts[0], false);
}

function showDraft(draft, switchToAnalysis = false) {
  state.draftId = draft.id;
  state.currentDraft = draft;
  $("empty-editor").hidden = true;
  $("draft-form").hidden = false;
  $("draft-title").value = draft.title;
  $("draft-body").value = draft.body;
  $("draft-tags").value = draft.tags;
  $("facts-checked").checked = false;
  $("rights-checked").checked = false;
  const provenance = parseJSON(draft.provenance_json, {});
  const generator = provenance.generator || draft.created_by;
  const passes = Array.isArray(provenance.quality_passes) ? provenance.quality_passes.length : 0;
  const passCopy = passes ? ` · ${passes} 道编辑流程` : "";
  message($("draft-status"), `当前版本 v${draft.version} · ${generator}${passCopy}`);
  renderAnalysis(draft);
  loadCards(draft.id);
  if (switchToAnalysis) setTab("analysis-pane");
}

function renderAnalysis(draft) {
  const provenance = draft ? parseJSON(draft.provenance_json, {}) : {};
  const analysis = provenance.editorial_analysis;
  const hasAnalysis = analysis && typeof analysis === "object" && Object.keys(analysis).length > 0;
  $("analysis-empty").hidden = hasAnalysis;
  $("analysis-content").hidden = !hasAnalysis;
  if (!hasAnalysis) return;

  $("analysis-topic").textContent = analysis.topic || "编辑分析";
  $("analysis-summary").textContent = analysis.one_sentence_summary || "";
  const recommended = analysis.recommended_angle || {};
  $("analysis-angle-name").textContent = recommended.name || "尚未选择角度";
  $("analysis-angle-reason").textContent = recommended.reason || "";
  renderAnalysisList($("analysis-facts"), analysis.verified_facts, "statement");
  renderAnalysisList($("analysis-claims"), analysis.author_claims, "statement");
  renderAnalysisList($("analysis-uncertainties"), analysis.uncertainties);
  renderAnalysisList($("analysis-values"), analysis.audience_value);
  renderTitleCandidates(analysis.title_candidates || []);
}

function renderAnalysisList(container, values, objectField = null) {
  container.replaceChildren();
  const items = Array.isArray(values) ? values : [];
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "analysis-list-item";
    empty.textContent = "模型未返回这一项";
    container.appendChild(empty);
    return;
  }
  items.slice(0, 8).forEach((raw) => {
    const row = document.createElement("div");
    row.className = "analysis-list-item";
    row.textContent = objectField && raw && typeof raw === "object"
      ? raw[objectField] || ""
      : String(raw || "");
    container.appendChild(row);
  });
}

function renderTitleCandidates(titles) {
  const box = $("analysis-titles");
  box.replaceChildren();
  if (!Array.isArray(titles) || !titles.length) {
    const empty = document.createElement("span");
    empty.className = "helper-copy";
    empty.textContent = "没有候选标题";
    box.appendChild(empty);
    return;
  }
  titles.slice(0, 8).forEach((title) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "title-chip";
    button.textContent = title;
    button.title = "点击替换当前标题";
    button.addEventListener("click", () => {
      $("draft-title").value = title;
      setTab("draft-pane");
    });
    box.appendChild(button);
  });
}

async function loadCards(draftId) {
  const renders = await api(`/api/drafts/${encodeURIComponent(draftId)}/cards`);
  const latest = renders.find((render) => render.status === "rendered");
  renderCards(latest || null);
}

function renderCards(render) {
  state.currentCardRender = render;
  const gallery = $("card-gallery");
  gallery.replaceChildren();
  if (!render) {
    const empty = document.createElement("div");
    empty.className = "card-empty";
    empty.textContent = "当前草稿还没有生成卡片";
    gallery.appendChild(empty);
    return;
  }
  const paths = parseJSON(render.output_paths_json, []);
  const specs = parseJSON(render.spec_json, []);
  paths.forEach((_, index) => {
    const spec = specs[index] || {};
    const figure = document.createElement("button");
    figure.type = "button";
    figure.className = "card-preview";
    const image = document.createElement("img");
    image.src = `/api/cards/${encodeURIComponent(render.id)}/files/${index}`;
    image.alt = `小红书卡片 ${index + 1}`;
    image.loading = "lazy";
    const meta = document.createElement("div");
    meta.className = "card-preview-meta";
    const label = document.createElement("strong");
    label.textContent = kindLabel(spec.kind);
    const count = document.createElement("span");
    count.textContent = `${String(index + 1).padStart(2, "0")} / ${String(paths.length).padStart(2, "0")}`;
    meta.append(label, count);
    figure.append(image, meta);
    figure.addEventListener("click", () => openLightbox(image.src, `${kindLabel(spec.kind)} · ${spec.title || ""}`));
    gallery.appendChild(figure);
  });
}

function openLightbox(src, caption) {
  $("lightbox-image").src = src;
  $("lightbox-caption").textContent = caption;
  $("card-lightbox").hidden = false;
}

function closeLightbox() {
  $("card-lightbox").hidden = true;
  $("lightbox-image").src = "";
}

function showJobFailure(job, submitButton) {
  const box = $("intake-status");
  box.replaceChildren();
  box.className = "inline-status error";
  const text = document.createElement("span");
  text.textContent = `导入失败：${job.error || "未知错误"} `;
  const retryButton = document.createElement("button");
  retryButton.type = "button";
  retryButton.className = "tool-button";
  retryButton.textContent = "重试";
  retryButton.addEventListener("click", async () => {
    retryButton.disabled = true;
    try {
      const retried = await api(`/api/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST" });
      await pollIntakeJob(retried.id, submitButton);
    } catch (error) {
      message(box, error.message, "error");
      submitButton.disabled = false;
    }
  });
  box.append(text, retryButton);
  submitButton.disabled = false;
}

async function pollIntakeJob(jobId, submitButton) {
  state.activeJobId = jobId;
  submitButton.disabled = true;
  for (let count = 0; count < 600; count += 1) {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (job.state === "succeeded") {
      const result = parseJSON(job.result_json, {});
      message(
        $("intake-status"),
        `已归档 ${result.imported_count || 0} 条内容，发现 ${result.asset_count || 0} 个素材。`,
        "ok",
      );
      state.activeJobId = null;
      submitButton.disabled = false;
      await loadSources(result.source_id || null);
      return;
    }
    if (job.state === "failed" || job.state === "canceled") {
      state.activeJobId = null;
      showJobFailure(job, submitButton);
      return;
    }
    const label = job.state === "running" ? "正在读取、归档与规范化" : "任务等待执行";
    message($("intake-status"), `${label} · 第 ${job.attempts || 0} 次尝试`);
    await sleep(500);
  }
  state.activeJobId = null;
  submitButton.disabled = false;
  message($("intake-status"), "任务仍在后台运行，可稍后刷新来源箱。", "error");
}

async function resumeLatestIntakeJob() {
  try {
    const jobs = await api("/api/jobs?limit=20");
    const active = jobs.find((job) => job.kind === "intake_x" && ["pending", "running"].includes(job.state));
    if (active && !state.activeJobId) {
      pollIntakeJob(active.id, $("intake-form").querySelector('button[type="submit"]'));
    }
  } catch {
    // 页面其他功能不依赖历史任务。
  }
}

async function saveRights() {
  if (!state.sourceId) return;
  const button = $("save-rights");
  button.disabled = true;
  try {
    const item = await api(`/api/sources/${encodeURIComponent(state.sourceId)}/rights`, {
      method: "PUT",
      body: JSON.stringify({
        source_status: $("rights-status").value,
        source_note: $("rights-note").value,
        asset_status: $("asset-rights-status").value,
        asset_note: $("rights-note").value,
        apply_to_related: $("apply-related-rights").checked,
      }),
    });
    state.currentSource = item;
    renderSourceDetail(item);
    message($("rights-status-message"), "版权判断已保存。", "ok");
    await loadSources();
  } catch (error) {
    message($("rights-status-message"), error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function generateDraft() {
  if (!state.sourceId) return;
  const button = $("generate-draft");
  button.disabled = true;
  button.textContent = "AI 正在分析…";
  try {
    const draft = await api(`/api/sources/${encodeURIComponent(state.sourceId)}/drafts`, {
      method: "POST",
      body: JSON.stringify({ style: $("draft-style").value }),
    });
    showDraft(draft, true);
  } catch (error) {
    window.alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "AI 分析并生成";
  }
}

async function transformDraft(action, button) {
  if (!state.draftId) return;
  const labels = {
    de_translate: "去翻译味",
    stronger_insight: "更有判断",
    concise: "精简正文",
    rewrite_title: "重写标题",
  };
  button.disabled = true;
  const oldText = button.textContent;
  button.textContent = "处理中…";
  message($("draft-status"), `${labels[action]}：AI 正在受来源约束地改写…`);
  try {
    const draft = await api(`/api/drafts/${encodeURIComponent(state.draftId)}/transform`, {
      method: "POST",
      body: JSON.stringify({ action, instruction: "" }),
    });
    showDraft(draft, false);
    setTab("draft-pane");
    message($("draft-status"), `已生成 v${draft.version} · ${labels[action]}`, "ok");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

async function saveDraft(event) {
  event.preventDefault();
  if (!state.draftId) return;
  const button = event.submitter;
  button.disabled = true;
  try {
    const draft = await api(`/api/drafts/${encodeURIComponent(state.draftId)}`, {
      method: "PUT",
      body: JSON.stringify({
        title: $("draft-title").value,
        body: $("draft-body").value,
        tags: $("draft-tags").value,
      }),
    });
    showDraft(draft, false);
    message($("draft-status"), `已保存为新版本 v${draft.version}，卡片需要重新生成。`, "ok");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function generateCards() {
  if (!state.draftId) return;
  const button = $("generate-cards");
  button.disabled = true;
  button.textContent = "正在构建叙事…";
  message($("draft-status"), "正在生成内容驱动的卡片组…");
  try {
    const render = await api(`/api/drafts/${encodeURIComponent(state.draftId)}/cards`, {
      method: "POST",
      body: JSON.stringify({ template: $("card-template").value, max_cards: 7 }),
    });
    renderCards(render);
    message($("draft-status"), "整套图片卡片已生成。", "ok");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "生成整套卡片";
  }
}

async function review(decision) {
  if (!state.draftId) return;
  try {
    await api(`/api/drafts/${encodeURIComponent(state.draftId)}/review`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        reason: "",
        facts_checked: $("facts-checked").checked,
        rights_checked: $("rights-checked").checked,
      }),
    });
    message(
      $("draft-status"),
      decision === "approved" ? "当前版本已批准。" : "当前版本已退回。",
      decision === "approved" ? "ok" : "error",
    );
  } catch (error) {
    message($("draft-status"), error.message, "error");
  }
}

async function preparePublish() {
  if (!state.draftId) return;
  const button = $("prepare");
  button.disabled = true;
  try {
    const task = await api(`/api/publish/drafts/${encodeURIComponent(state.draftId)}/prepare`, {
      method: "POST",
      body: JSON.stringify({
        include_cards: true,
        include_source_assets: $("include-source-assets").checked,
      }),
    });
    message($("draft-status"), `发布包已生成：${task.package_path}`, "ok");
    await loadPublish();
    setView("publish-view");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function loadPublish() {
  const tasks = await api("/api/publish");
  const box = $("publish-list");
  box.replaceChildren();
  if (!tasks.length) {
    const empty = document.createElement("div");
    empty.className = "card-empty";
    empty.textContent = "还没有发布任务";
    box.appendChild(empty);
    return;
  }
  for (const task of tasks) {
    const row = document.createElement("article");
    row.className = "publish-task";
    const details = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = task.title;
    const meta = document.createElement("small");
    meta.textContent = `${task.state} · ${task.package_path || "尚未打包"}`;
    const error = document.createElement("small");
    error.style.color = "var(--danger)";
    error.textContent = task.error || "";
    details.append(title, meta, error);
    if (task.result_url) {
      const result = document.createElement("a");
      result.href = task.result_url;
      result.target = "_blank";
      result.rel = "noreferrer";
      result.textContent = "查看已发布笔记 ↗";
      details.appendChild(result);
    }

    const actions = document.createElement("div");
    actions.className = "publish-actions";
    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "primary-action";
    openButton.textContent = "打开小红书预览";
    openButton.addEventListener("click", async () => {
      openButton.disabled = true;
      try {
        await api(`/api/publish/${encodeURIComponent(task.id)}/open-xhs`, { method: "POST" });
        await loadPublish();
      } catch (err) {
        window.alert(err.message);
      } finally {
        openButton.disabled = false;
      }
    });
    const markButton = document.createElement("button");
    markButton.type = "button";
    markButton.className = "secondary-action";
    markButton.textContent = "标记已发布";
    markButton.addEventListener("click", async () => {
      const resultUrl = window.prompt("粘贴已发布的小红书笔记链接");
      if (!resultUrl) return;
      markButton.disabled = true;
      try {
        await api(`/api/publish/${encodeURIComponent(task.id)}/mark-published`, {
          method: "POST",
          body: JSON.stringify({ result_url: resultUrl }),
        });
        await loadPublish();
      } catch (err) {
        window.alert(err.message);
      } finally {
        markButton.disabled = false;
      }
    });
    actions.append(openButton, markButton);
    row.append(details, actions);
    box.appendChild(row);
  }
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelectorAll(".stage-tab").forEach((button) => {
    button.addEventListener("click", () => setTab(button.dataset.tab));
  });
  document.querySelectorAll("[data-transform]").forEach((button) => {
    button.addEventListener("click", () => transformDraft(button.dataset.transform, button));
  });

  $("source-search").addEventListener("input", renderSourceList);
  $("refresh").addEventListener("click", () => loadSources());
  $("refresh-publish").addEventListener("click", loadPublish);
  $("save-rights").addEventListener("click", saveRights);
  $("generate-draft").addEventListener("click", generateDraft);
  $("draft-form").addEventListener("submit", saveDraft);
  $("generate-cards").addEventListener("click", generateCards);
  $("approve").addEventListener("click", () => review("approved"));
  $("reject").addEventListener("click", () => review("rejected"));
  $("prepare").addEventListener("click", preparePublish);
  $("close-lightbox").addEventListener("click", closeLightbox);
  $("card-lightbox").addEventListener("click", (event) => {
    if (event.target === $("card-lightbox")) closeLightbox();
  });

  $("intake-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    message($("intake-status"), "任务正在排队…");
    try {
      const job = await api("/api/jobs/intake", {
        method: "POST",
        body: JSON.stringify({
          url: $("x-url").value,
          mode: $("mode").value,
          download_media: $("download-media").checked,
        }),
      });
      await pollIntakeJob(job.id, button);
    } catch (error) {
      message($("intake-status"), error.message, "error");
      button.disabled = false;
    }
  });
}

async function boot() {
  bindEvents();
  const prefilledUrl = new URLSearchParams(window.location.search).get("url");
  if (prefilledUrl) $("x-url").value = prefilledUrl;
  await Promise.all([loadHealth(), loadSources(), loadPublish()]);
  resumeLatestIntakeJob();
}

boot();
