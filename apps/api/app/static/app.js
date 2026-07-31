const state = {
  sourceId: null,
  draftId: null,
  currentSource: null,
  currentDraft: null,
  currentCardRender: null,
  activeJobId: null,
  sourceItems: [],
  workspaceState: "active",
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
  if (response.status === 204) return null;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
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
  if (!value) return "刚刚";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "已保存";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatLongDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function initials(item) {
  const seed = (item.author_name || item.author_handle || "X").trim();
  return [...seed][0]?.toUpperCase() || "X";
}

function contentKindLabel(value) {
  return {
    article: "ARTICLE",
    post: "POST",
    thread: "THREAD",
    longer_post: "LONG POST",
  }[value] || String(value || "POST").toUpperCase();
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

function safeImageUrl(value) {
  try {
    const url = new URL(value || "", window.location.href);
    if (url.origin === window.location.origin && url.pathname.startsWith("/api/assets/")) return url.href;
    if (url.protocol !== "https:") return "";
    const host = url.hostname.toLowerCase();
    return ["pbs.twimg.com", "abs.twimg.com", "video.twimg.com"].includes(host) ? url.href : "";
  } catch {
    return "";
  }
}

function plainHtml(value) {
  if (!value) return "";
  const documentValue = new DOMParser().parseFromString(String(value), "text/html");
  return (documentValue.body.textContent || "").replace(/\s+/g, " ").trim();
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
    "settings-view": "模型与 Skill",
  };
  $("page-title").textContent = titles[viewId] || "X2RED";
  if (viewId === "publish-view") loadPublish();
  if (viewId === "settings-view") loadSkills();
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
      ? "模型已连接。下方每个 Skill 可单独启用、指定模型名称与推理强度。"
      : "当前只能使用规则化兜底稿。请先在 .env 中配置 GLM 或兼容模型。";
  } catch {
    $("health").textContent = "服务不可用";
    $("health").className = "status-chip error";
    $("model-status").textContent = "AI 状态未知";
    $("model-status").className = "status-chip error";
  }
}

async function loadSources(selectId = null) {
  const items = await api(`/api/sources?workspace_state=${encodeURIComponent(state.workspaceState)}`);
  state.sourceItems = items || [];
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
    empty.className = "source-list-empty";
    empty.textContent = query
      ? "没有匹配的来源"
      : state.workspaceState === "active" ? "来源箱还是空的" : "还没有归档内容";
    list.appendChild(empty);
    return;
  }
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `source-item${item.id === state.sourceId ? " active" : ""}`;
    const top = document.createElement("span");
    top.className = "source-item-top";
    const avatar = document.createElement("span");
    avatar.className = "source-mini-avatar";
    avatar.textContent = initials(item);
    const meta = document.createElement("span");
    meta.className = "source-meta";
    const name = document.createElement("strong");
    name.textContent = item.author_handle ? `@${item.author_handle}` : item.author_name || "未知作者";
    const date = document.createElement("small");
    date.textContent = formatDate(item.archived_at || item.captured_at);
    meta.append(name, date);
    const dot = document.createElement("span");
    dot.className = `source-state-dot${item.state === "available" ? " ready" : ""}`;
    top.append(avatar, meta, dot);
    const preview = document.createElement("span");
    preview.className = "source-preview";
    preview.textContent = item.text_original || "（无正文）";
    const bottom = document.createElement("span");
    bottom.className = "source-item-bottom";
    const type = document.createElement("span");
    type.className = "source-type";
    type.textContent = contentKindLabel(item.content_kind);
    const published = document.createElement("span");
    published.className = "source-published";
    published.textContent = item.published_count ? `已发布 ${item.published_count} 次` : item.provider === "x2pdf" ? "X2PDF" : "X SOURCE";
    bottom.append(type, published);
    button.append(top, preview, bottom);
    button.addEventListener("click", () => selectSource(item.id));
    list.appendChild(button);
  }
}

function clearActiveSource() {
  state.sourceId = null;
  state.draftId = null;
  state.currentSource = null;
  state.currentDraft = null;
  $("empty-workbench").hidden = false;
  $("active-workbench").hidden = true;
  renderSourceList();
}

async function selectSource(id) {
  state.sourceId = id;
  state.draftId = null;
  state.currentDraft = null;
  renderSourceList();
  try {
    const item = await api(`/api/sources/${encodeURIComponent(id)}`);
    state.currentSource = item;
    $("empty-workbench").hidden = true;
    $("active-workbench").hidden = false;
    renderSourceDetail(item);
    await loadDrafts(id);
    setTab("source-pane");
  } catch (error) {
    clearActiveSource();
    window.alert(error.message);
  }
}

function renderSourceDetail(item) {
  $("source-avatar").textContent = initials(item);
  $("source-author").textContent = item.author_handle
    ? `${item.author_name || item.author_handle} · @${item.author_handle}`
    : item.author_name || "未知作者";
  $("source-link").href = item.canonical_url;
  $("source-kind-badge").textContent = contentKindLabel(item.content_kind);
  $("archive-source").textContent = item.workspace_state === "archived" ? "恢复到来源箱" : "归档";
  $("editor-note").value = item.editor_note || "";
  renderXSource(item);
  renderAssets(item.assets || []);
}

function avatarNode(item, sizeClass = "x-avatar") {
  const src = safeImageUrl(item.author_avatar_url);
  if (src) {
    const image = document.createElement("img");
    image.className = sizeClass;
    image.src = src;
    image.alt = item.author_name || item.author_handle || "作者头像";
    return image;
  }
  const fallback = document.createElement("span");
  fallback.className = `${sizeClass} x-avatar-fallback`;
  fallback.textContent = initials(item);
  return fallback;
}

function createXHeader(item) {
  const header = document.createElement("header");
  header.className = "x-post-header";
  header.appendChild(avatarNode(item));
  const identity = document.createElement("div");
  identity.className = "x-post-identity";
  const firstLine = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = item.author_name || item.author_handle || "未知作者";
  const handle = document.createElement("span");
  handle.textContent = item.author_handle ? `@${item.author_handle}` : "";
  firstLine.append(name, handle);
  const time = document.createElement("small");
  time.textContent = formatLongDate(item.created_at || item.captured_at);
  identity.append(firstLine, time);
  const logo = document.createElement("span");
  logo.className = "x-glyph";
  logo.textContent = "𝕏";
  header.append(identity, logo);
  return header;
}

function createXPost(item, options = {}) {
  const post = document.createElement("article");
  post.className = `x-post${options.thread ? " x-thread-post" : ""}`;
  if (options.thread) {
    const line = document.createElement("span");
    line.className = "x-thread-line";
    post.appendChild(line);
  }
  post.appendChild(createXHeader(item));
  const body = document.createElement("div");
  body.className = "x-post-body";
  const text = document.createElement("p");
  text.className = "x-post-text";
  text.textContent = item.text_original || "（无正文）";
  body.appendChild(text);
  if (options.includeAssets) body.appendChild(createXMediaGrid(item.assets || []));
  const metrics = parseJSON(item.metrics_json, {});
  const metricValues = [
    ["回复", metrics.replies || metrics.reply_count],
    ["转发", metrics.reposts || metrics.retweets || metrics.retweet_count],
    ["喜欢", metrics.likes || metrics.favorite_count],
    ["浏览", metrics.views || metrics.view_count],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (metricValues.length) {
    const footer = document.createElement("footer");
    footer.className = "x-post-metrics";
    metricValues.forEach(([label, value]) => {
      const node = document.createElement("span");
      node.textContent = `${value} ${label}`;
      footer.appendChild(node);
    });
    body.appendChild(footer);
  }
  post.appendChild(body);
  return post;
}

function createXMediaGrid(assets) {
  const grid = document.createElement("div");
  grid.className = `x-media-grid media-count-${Math.min(assets.length, 4)}`;
  assets.slice(0, 4).forEach((asset) => {
    const src = asset.local_path
      ? `/api/assets/${encodeURIComponent(asset.id)}/file`
      : safeImageUrl(asset.remote_url);
    if (!src) return;
    if (asset.kind === "image") {
      const image = document.createElement("img");
      image.src = src;
      image.alt = asset.alt_text || "来源图片";
      image.loading = "lazy";
      grid.appendChild(image);
    } else {
      const video = document.createElement("video");
      video.src = src;
      video.controls = true;
      grid.appendChild(video);
    }
  });
  return grid;
}

function recursiveText(value) {
  if (typeof value === "string") return plainHtml(value);
  if (Array.isArray(value)) return value.map(recursiveText).filter(Boolean).join(" ");
  if (value && typeof value === "object") {
    return ["title", "name", "text", "html", "label", "caption", "description"]
      .map((key) => recursiveText(value[key]))
      .filter(Boolean)
      .join(" ") || Object.values(value).map(recursiveText).filter(Boolean).join(" ");
  }
  return "";
}

function renderArticleBlock(block) {
  if (!block || typeof block !== "object") return null;
  const type = block.type;
  if (type === "heading") {
    const level = Math.min(Math.max(Number(block.level) || 2, 2), 4);
    const heading = document.createElement(`h${level}`);
    heading.textContent = plainHtml(block.html || block.text);
    return heading.textContent ? heading : null;
  }
  if (type === "paragraph") {
    const paragraph = document.createElement("p");
    paragraph.textContent = plainHtml(block.html || block.text);
    return paragraph.textContent ? paragraph : null;
  }
  if (type === "blockquote") {
    const quote = document.createElement("blockquote");
    quote.textContent = recursiveText(block.paragraphs || block.html || block.text);
    return quote.textContent ? quote : null;
  }
  if (type === "code") {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = block.text || "";
    pre.appendChild(code);
    return pre;
  }
  if (type === "formula") {
    const formula = document.createElement("div");
    formula.className = "x-article-formula";
    formula.textContent = block.latex || block.text || plainHtml(block.mathml) || "数学公式";
    return formula;
  }
  if (type === "separator") return document.createElement("hr");
  if (type === "image" || type === "media") {
    const src = safeImageUrl(block.url || block.src || block.imageUrl || block.thumbnailUrl);
    if (!src) return null;
    const figure = document.createElement("figure");
    const image = document.createElement("img");
    image.src = src;
    image.alt = block.alt || block.caption || "长文图片";
    image.loading = "lazy";
    figure.appendChild(image);
    if (block.caption) {
      const caption = document.createElement("figcaption");
      caption.textContent = recursiveText(block.caption);
      figure.appendChild(caption);
    }
    return figure;
  }
  if (type === "list") {
    const list = block.ordered ? document.createElement("ol") : document.createElement("ul");
    const values = Array.isArray(block.items) ? block.items : [];
    values.forEach((value) => {
      const item = document.createElement("li");
      item.textContent = recursiveText(value);
      if (item.textContent) list.appendChild(item);
    });
    return list.childElementCount ? list : null;
  }
  if (type === "table") {
    const table = document.createElement("div");
    table.className = "x-article-table";
    table.textContent = recursiveText(block.rows || block);
    return table.textContent ? table : null;
  }
  if (["embedded_post", "link_card"].includes(type)) {
    const card = document.createElement("div");
    card.className = "x-embed-card";
    card.textContent = recursiveText(block);
    return card.textContent ? card : null;
  }
  const fallback = recursiveText(block);
  if (!fallback) return null;
  const paragraph = document.createElement("p");
  paragraph.textContent = fallback;
  return paragraph;
}

function renderStructuredArticle(item, documentValue) {
  const article = document.createElement("article");
  article.className = "x-article";
  article.appendChild(createXHeader(item));
  const content = document.createElement("div");
  content.className = "x-article-content";
  const title = document.createElement("h1");
  title.textContent = documentValue.metadata?.title || item.text_original.split("\n")[0] || "X Article";
  content.appendChild(title);
  const cover = safeImageUrl(documentValue.metadata?.coverImage);
  if (cover) {
    const image = document.createElement("img");
    image.className = "x-article-cover";
    image.src = cover;
    image.alt = "Article cover";
    content.appendChild(image);
  }
  (documentValue.blocks || []).forEach((block) => {
    const node = renderArticleBlock(block);
    if (node) content.appendChild(node);
  });
  article.appendChild(content);
  return article;
}

function renderXSource(item) {
  const feed = $("x-source-feed");
  feed.replaceChildren();
  const documentValue = parseJSON(item.structured_content_json, {});
  if (documentValue && Array.isArray(documentValue.blocks) && documentValue.blocks.length) {
    feed.appendChild(renderStructuredArticle(item, documentValue));
  } else {
    feed.appendChild(createXPost(item, { includeAssets: true }));
    (item.related || []).forEach((related) => {
      feed.appendChild(createXPost(related, { thread: true, includeAssets: false }));
    });
  }
  $("related-count").textContent = `${(item.related || []).length} 条上下文`;
}

function renderAssets(assets) {
  const box = $("assets");
  box.replaceChildren();
  if (!assets.length) {
    const empty = document.createElement("div");
    empty.className = "card-empty";
    empty.style.minHeight = "120px";
    empty.textContent = "这条来源没有可用媒体";
    box.appendChild(empty);
    return;
  }
  for (const asset of assets) {
    const wrap = document.createElement("article");
    wrap.className = "asset";
    const url = asset.local_path ? `/api/assets/${encodeURIComponent(asset.id)}/file` : safeImageUrl(asset.remote_url);
    if (!url) continue;
    const media = document.createElement(asset.kind === "image" ? "img" : "video");
    media.src = url;
    if (asset.kind === "image") media.alt = asset.alt_text || "来源图片";
    else media.controls = true;
    const meta = document.createElement("div");
    meta.className = "asset-meta";
    meta.textContent = asset.role || asset.kind;
    wrap.append(media, meta);
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
  const provenance = parseJSON(draft.provenance_json, {});
  const generator = provenance.generator || draft.created_by;
  const passes = Array.isArray(provenance.quality_passes) ? provenance.quality_passes.length : 0;
  message($("draft-status"), `当前版本 v${draft.version} · ${generator}${passes ? ` · ${passes} 个 Skill` : ""}`);
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
    row.textContent = objectField && raw && typeof raw === "object" ? raw[objectField] || "" : String(raw || "");
    container.appendChild(row);
  });
}

function renderTitleCandidates(titles) {
  const box = $("analysis-titles");
  box.replaceChildren();
  if (!Array.isArray(titles) || !titles.length) {
    box.textContent = "没有候选标题";
    return;
  }
  titles.slice(0, 8).forEach((title) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "title-chip";
    button.textContent = title;
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

async function pollIntakeJob(jobId, submitButton) {
  state.activeJobId = jobId;
  submitButton.disabled = true;
  for (let count = 0; count < 600; count += 1) {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (job.state === "succeeded") {
      const result = parseJSON(job.result_json, {});
      message($("intake-status"), `已导入 ${result.imported_count || 0} 条内容，发现 ${result.asset_count || 0} 个素材。`, "ok");
      state.activeJobId = null;
      submitButton.disabled = false;
      state.workspaceState = "active";
      updateSourceTabs();
      await loadSources(result.source_id || null);
      return;
    }
    if (["failed", "canceled"].includes(job.state)) {
      state.activeJobId = null;
      submitButton.disabled = false;
      message($("intake-status"), `导入失败：${job.error || "未知错误"}`, "error");
      return;
    }
    message($("intake-status"), job.state === "running" ? "正在读取、归档与复原…" : "任务等待执行…");
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
    if (active && !state.activeJobId) pollIntakeJob(active.id, $("intake-form").querySelector('button[type="submit"]'));
  } catch {
    // 页面其他功能不依赖历史任务。
  }
}

async function saveNote() {
  if (!state.sourceId) return;
  const button = $("save-note");
  button.disabled = true;
  try {
    const item = await api(`/api/sources/${encodeURIComponent(state.sourceId)}/note`, {
      method: "PUT",
      body: JSON.stringify({ editor_note: $("editor-note").value }),
    });
    state.currentSource = item;
    message($("note-status"), "我的判断已保存，会进入下一次 AI 分析。", "ok");
  } catch (error) {
    message($("note-status"), error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function toggleArchive() {
  if (!state.currentSource) return;
  const isArchived = state.currentSource.workspace_state === "archived";
  const path = isArchived ? "restore" : "archive";
  const item = await api(`/api/sources/${encodeURIComponent(state.sourceId)}/${path}`, { method: "POST" });
  state.currentSource = item;
  clearActiveSource();
  await loadSources();
}

async function deleteSource() {
  if (!state.currentSource) return;
  const label = state.currentSource.author_handle ? `@${state.currentSource.author_handle}` : "这条来源";
  if (!window.confirm(`彻底删除 ${label} 及其草稿、卡片和发布记录？此操作不可恢复。`)) return;
  await api(`/api/sources/${encodeURIComponent(state.sourceId)}`, { method: "DELETE" });
  clearActiveSource();
  await loadSources();
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
  const labels = { de_translate: "去翻译味", stronger_insight: "更有判断", concise: "精简正文", rewrite_title: "重写标题" };
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "处理中…";
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
      body: JSON.stringify({ title: $("draft-title").value, body: $("draft-body").value, tags: $("draft-tags").value }),
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
  button.textContent = "正在排版…";
  try {
    const render = await api(`/api/drafts/${encodeURIComponent(state.draftId)}/cards`, {
      method: "POST",
      body: JSON.stringify({ template: $("card-template").value, max_cards: 7 }),
    });
    renderCards(render);
    message($("draft-status"), "HTML/CSS 卡片已生成。", "ok");
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
      body: JSON.stringify({ decision, reason: "", facts_checked: $("facts-checked").checked, rights_checked: true }),
    });
    message($("draft-status"), decision === "approved" ? "当前版本已批准。" : "当前版本已退回。", decision === "approved" ? "ok" : "error");
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
      body: JSON.stringify({ include_cards: true, include_source_assets: $("include-source-assets").checked }),
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
    details.append(title, meta);
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
    openButton.disabled = task.state === "published";
    openButton.addEventListener("click", async () => {
      openButton.disabled = true;
      try { await api(`/api/publish/${encodeURIComponent(task.id)}/open-xhs`, { method: "POST" }); await loadPublish(); }
      catch (error) { window.alert(error.message); }
      finally { openButton.disabled = false; }
    });
    const markButton = document.createElement("button");
    markButton.type = "button";
    markButton.className = "secondary-action";
    markButton.textContent = task.state === "published" ? "已发布并归档" : "标记已发布";
    markButton.disabled = task.state === "published";
    markButton.addEventListener("click", async () => {
      const resultUrl = window.prompt("粘贴已发布的小红书笔记链接");
      if (!resultUrl) return;
      markButton.disabled = true;
      try {
        await api(`/api/publish/${encodeURIComponent(task.id)}/mark-published`, { method: "POST", body: JSON.stringify({ result_url: resultUrl }) });
        if (state.currentSource?.id === state.sourceId) clearActiveSource();
        await Promise.all([loadPublish(), loadSources()]);
      } catch (error) { window.alert(error.message); }
      finally { markButton.disabled = false; }
    });
    actions.append(openButton, markButton);
    row.append(details, actions);
    box.appendChild(row);
  }
}

async function loadSkills() {
  const list = $("skill-list");
  list.textContent = "正在读取 Skill…";
  try {
    const skills = await api("/api/settings/skills");
    list.replaceChildren();
    skills.forEach((skill) => {
      const row = document.createElement("article");
      row.className = "skill-row";
      const copy = document.createElement("div");
      copy.className = "skill-copy";
      const title = document.createElement("strong");
      title.textContent = skill.label;
      const code = document.createElement("code");
      code.textContent = skill.skill_name;
      const description = document.createElement("p");
      description.textContent = skill.description;
      copy.append(title, code, description);
      const controls = document.createElement("div");
      controls.className = "skill-controls";
      const enabled = document.createElement("input");
      enabled.type = "checkbox";
      enabled.checked = skill.enabled;
      enabled.title = "启用 Skill";
      const model = document.createElement("input");
      model.value = skill.model_name || state.health?.model_name || "";
      model.placeholder = "模型名称";
      const effort = document.createElement("select");
      ["low", "medium", "high"].forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = { low: "低推理", medium: "中推理", high: "高推理" }[value];
        effort.appendChild(option);
      });
      effort.value = skill.reasoning_effort || "medium";
      const save = document.createElement("button");
      save.type = "button";
      save.className = "secondary-action";
      save.textContent = "保存";
      save.addEventListener("click", async () => {
        save.disabled = true;
        try {
          await api(`/api/settings/skills/${encodeURIComponent(skill.skill_name)}`, {
            method: "PUT",
            body: JSON.stringify({ enabled: enabled.checked, model_name: model.value, reasoning_effort: effort.value, prompt_version: skill.prompt_version || "v1" }),
          });
          save.textContent = "已保存";
          setTimeout(() => { save.textContent = "保存"; }, 1200);
        } catch (error) { window.alert(error.message); }
        finally { save.disabled = false; }
      });
      controls.append(enabled, model, effort, save);
      row.append(copy, controls);
      list.appendChild(row);
    });
  } catch (error) {
    list.textContent = error.message;
  }
}

function updateSourceTabs() {
  document.querySelectorAll(".source-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.sourceState === state.workspaceState);
  });
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  document.querySelectorAll(".stage-tab").forEach((button) => button.addEventListener("click", () => setTab(button.dataset.tab)));
  document.querySelectorAll(".source-tab").forEach((button) => button.addEventListener("click", async () => {
    state.workspaceState = button.dataset.sourceState;
    updateSourceTabs();
    clearActiveSource();
    await loadSources();
  }));
  document.querySelectorAll("[data-transform]").forEach((button) => button.addEventListener("click", () => transformDraft(button.dataset.transform, button)));
  $("source-search").addEventListener("input", renderSourceList);
  $("refresh").addEventListener("click", () => loadSources());
  $("refresh-publish").addEventListener("click", loadPublish);
  $("refresh-skills").addEventListener("click", loadSkills);
  $("save-note").addEventListener("click", saveNote);
  $("archive-source").addEventListener("click", () => toggleArchive().catch((error) => window.alert(error.message)));
  $("delete-source").addEventListener("click", () => deleteSource().catch((error) => window.alert(error.message)));
  $("generate-draft").addEventListener("click", generateDraft);
  $("draft-form").addEventListener("submit", saveDraft);
  $("generate-cards").addEventListener("click", generateCards);
  $("approve").addEventListener("click", () => review("approved"));
  $("reject").addEventListener("click", () => review("rejected"));
  $("prepare").addEventListener("click", preparePublish);
  $("close-lightbox").addEventListener("click", closeLightbox);
  $("card-lightbox").addEventListener("click", (event) => { if (event.target === $("card-lightbox")) closeLightbox(); });

  $("intake-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    const input = $("x-url");
    const submittedUrl = input.value;
    button.disabled = true;
    message($("intake-status"), "任务正在排队…");
    try {
      const job = await api("/api/jobs/intake", {
        method: "POST",
        body: JSON.stringify({ url: submittedUrl, mode: $("mode").value, download_media: $("download-media").checked }),
      });
      input.value = "";
      input.focus();
      await pollIntakeJob(job.id, button);
    } catch (error) {
      input.value = submittedUrl;
      input.focus();
      message($("intake-status"), error.message, "error");
      button.disabled = false;
    }
  });
}

async function boot() {
  bindEvents();
  const params = new URLSearchParams(window.location.search);
  const prefilledUrl = params.get("url");
  const sourceId = params.get("source");
  if (prefilledUrl) $("x-url").value = prefilledUrl;
  await Promise.all([loadHealth(), loadPublish()]);
  await loadSources(sourceId || null);
  resumeLatestIntakeJob();
}

boot();
