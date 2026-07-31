const state = { sourceId: null, draftId: null, currentSource: null };
const $ = (id) => document.getElementById(id);

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

function message(el, text, type = "") {
  el.textContent = text;
  el.className = `status ${type}`;
}

async function health() {
  try {
    const data = await api("/health");
    $("health").textContent = `${data.name} ${data.version} · 本地运行`;
  } catch {
    $("health").textContent = "服务不可用";
  }
}

async function loadSources(selectId = null) {
  const items = await api("/api/sources");
  const list = $("source-list");
  list.replaceChildren();
  for (const item of items) {
    const node = $("source-template").content.cloneNode(true);
    const button = node.querySelector("button");
    button.dataset.id = item.id;
    button.classList.toggle("active", item.id === state.sourceId);
    node.querySelector(".source-name").textContent = `@${item.author_handle || item.author_name || "unknown"}`;
    node.querySelector(".source-preview").textContent = item.text_original.slice(0, 90) || "（无正文）";
    button.title = `版权状态：${item.rights_status}`;
    button.addEventListener("click", () => selectSource(item.id));
    list.appendChild(node);
  }
  if (selectId) await selectSource(selectId);
}

async function selectSource(id) {
  state.sourceId = id;
  state.draftId = null;
  document.querySelectorAll(".source-item").forEach((el) => el.classList.toggle("active", el.dataset.id === id));
  const item = await api(`/api/sources/${encodeURIComponent(id)}`);
  state.currentSource = item;
  $("empty-detail").hidden = true;
  $("source-detail").hidden = false;
  $("source-author").textContent = `${item.author_name || ""} @${item.author_handle || ""}`;
  $("source-link").href = item.canonical_url;
  $("source-text").textContent = item.text_original;
  $("rights-status").value = item.rights_status || "needs_review";
  $("rights-note").value = item.rights_note || "";
  const assetStates = new Set(item.assets.map((asset) => asset.rights_status));
  $("asset-rights-status").value = assetStates.size === 1 ? [...assetStates][0] : "needs_review";
  renderAssets(item.assets);
  $("related").textContent = item.related.length
    ? `相关上下文 ${item.related.length} 条：` + item.related.map((related) => related.text_original.slice(0, 55)).join(" ｜ ")
    : "当前未加载额外上下文。";
  message($("rights-status-message"), `当前文本状态：${item.rights_status}`);
  await loadDrafts(id);
}

function renderAssets(assets) {
  const box = $("assets");
  box.replaceChildren();
  for (const asset of assets) {
    const wrap = document.createElement("div");
    wrap.className = "asset";
    const url = asset.local_path ? `/api/assets/${encodeURIComponent(asset.id)}/file` : asset.remote_url;
    const media = document.createElement(asset.kind === "image" ? "img" : "video");
    media.src = url;
    if (asset.kind === "image") media.alt = asset.alt_text || "";
    else media.controls = true;
    const label = document.createElement("div");
    label.textContent = `${asset.state} · ${asset.rights_status}`;
    wrap.append(media, label);
    if (asset.error || asset.rights_note) wrap.title = [asset.error, asset.rights_note].filter(Boolean).join("\n");
    box.appendChild(wrap);
  }
}

async function loadDrafts(sourceId) {
  const drafts = await api(`/api/sources/${encodeURIComponent(sourceId)}/drafts`);
  if (!drafts.length) {
    $("empty-editor").hidden = false;
    $("draft-form").hidden = true;
    return;
  }
  showDraft(drafts[0]);
}

function showDraft(draft) {
  state.draftId = draft.id;
  $("empty-editor").hidden = true;
  $("draft-form").hidden = false;
  $("draft-title").value = draft.title;
  $("draft-body").value = draft.body;
  $("draft-tags").value = draft.tags;
  $("facts-checked").checked = false;
  $("rights-checked").checked = false;
  message($("draft-status"), `当前版本 v${draft.version} · ${draft.created_by}`);
  loadCards(draft.id);
}

async function loadCards(draftId) {
  const renders = await api(`/api/drafts/${encodeURIComponent(draftId)}/cards`);
  const latest = renders.find((render) => render.status === "rendered");
  renderCards(latest || null);
}

function renderCards(render) {
  const gallery = $("card-gallery");
  gallery.replaceChildren();
  if (!render) {
    const empty = document.createElement("div");
    empty.className = "empty compact";
    empty.textContent = "当前版本还没有卡片。";
    gallery.appendChild(empty);
    return;
  }
  let paths = [];
  try {
    paths = JSON.parse(render.output_paths_json || "[]");
  } catch {
    paths = [];
  }
  paths.forEach((_, index) => {
    const image = document.createElement("img");
    image.src = `/api/cards/${encodeURIComponent(render.id)}/files/${index}`;
    image.alt = `小红书卡片 ${index + 1}`;
    image.loading = "lazy";
    gallery.appendChild(image);
  });
}

$("intake-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  message($("intake-status"), "正在读取 FxTwitter、保存来源并处理媒体…");
  try {
    const result = await api("/api/intake/x", {
      method: "POST",
      body: JSON.stringify({
        url: $("x-url").value,
        mode: $("mode").value,
        download_media: $("download-media").checked,
      }),
    });
    message($("intake-status"), `已导入 ${result.imported_count} 条内容、发现 ${result.asset_count} 个素材。`, "ok");
    await loadSources(result.source_id);
  } catch (error) {
    message($("intake-status"), error.message, "error");
  } finally {
    button.disabled = false;
  }
});

$("save-rights").addEventListener("click", async () => {
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
    renderAssets(item.assets);
    message($("rights-status-message"), "版权判断已保存。", "ok");
    await loadSources();
  } catch (error) {
    message($("rights-status-message"), error.message, "error");
  } finally {
    button.disabled = false;
  }
});

$("generate-draft").addEventListener("click", async () => {
  if (!state.sourceId) return;
  const button = $("generate-draft");
  button.disabled = true;
  try {
    const draft = await api(`/api/sources/${encodeURIComponent(state.sourceId)}/drafts`, {
      method: "POST",
      body: JSON.stringify({ style: $("draft-style").value }),
    });
    showDraft(draft);
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
});

$("draft-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.draftId) return;
  try {
    const draft = await api(`/api/drafts/${encodeURIComponent(state.draftId)}`, {
      method: "PUT",
      body: JSON.stringify({
        title: $("draft-title").value,
        body: $("draft-body").value,
        tags: $("draft-tags").value,
      }),
    });
    showDraft(draft);
    message($("draft-status"), `已保存为新版本 v${draft.version}，请重新生成卡片并审核。`, "ok");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  }
});

$("generate-cards").addEventListener("click", async () => {
  if (!state.draftId) return;
  const button = $("generate-cards");
  button.disabled = true;
  message($("draft-status"), "正在生成卡片…");
  try {
    const render = await api(`/api/drafts/${encodeURIComponent(state.draftId)}/cards`, {
      method: "POST",
      body: JSON.stringify({ template: $("card-template").value, max_cards: 6 }),
    });
    renderCards(render);
    message($("draft-status"), "图片卡片已生成。", "ok");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  } finally {
    button.disabled = false;
  }
});

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
    message($("draft-status"), decision === "approved" ? "此版本已批准。" : "此版本已退回。", decision === "approved" ? "ok" : "error");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  }
}

$("approve").addEventListener("click", () => review("approved"));
$("reject").addEventListener("click", () => review("rejected"));
$("prepare").addEventListener("click", async () => {
  if (!state.draftId) return;
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
  } catch (error) {
    message($("draft-status"), error.message, "error");
  }
});

async function loadPublish() {
  const tasks = await api("/api/publish");
  const box = $("publish-list");
  box.replaceChildren();
  for (const task of tasks) {
    const row = document.createElement("div");
    row.className = "publish-task";

    const details = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = task.title;
    const meta = document.createElement("small");
    meta.textContent = `${task.state} · ${task.package_path || "尚未打包"}`;
    const error = document.createElement("small");
    error.className = "error-text";
    error.textContent = task.error || "";
    details.append(title, meta, error);
    if (task.result_url) {
      const result = document.createElement("a");
      result.href = task.result_url;
      result.target = "_blank";
      result.rel = "noreferrer";
      result.textContent = "查看已发布笔记";
      details.appendChild(result);
    }

    const actions = document.createElement("div");
    actions.className = "row wrap gap";
    const openButton = document.createElement("button");
    openButton.textContent = "打开小红书预览";
    openButton.disabled = !["packaged", "failed"].includes(task.state);
    openButton.addEventListener("click", async () => {
      openButton.disabled = true;
      try {
        await api(`/api/publish/${encodeURIComponent(task.id)}/open-xhs`, { method: "POST" });
        await loadPublish();
      } catch (requestError) {
        alert(requestError.message);
        openButton.disabled = false;
      }
    });
    actions.appendChild(openButton);

    if (task.state === "awaiting_user_confirmation") {
      const confirmButton = document.createElement("button");
      confirmButton.className = "approve";
      confirmButton.textContent = "记录发布结果";
      confirmButton.addEventListener("click", async () => {
        const resultUrl = window.prompt("粘贴发布成功的小红书作品链接");
        if (!resultUrl) return;
        try {
          await api(`/api/publish/${encodeURIComponent(task.id)}/mark-published`, {
            method: "POST",
            body: JSON.stringify({ result_url: resultUrl }),
          });
          await loadPublish();
        } catch (requestError) {
          alert(requestError.message);
        }
      });
      actions.appendChild(confirmButton);
    }

    row.append(details, actions);
    box.appendChild(row);
  }
}

$("refresh").addEventListener("click", () => loadSources());
$("refresh-publish").addEventListener("click", loadPublish);

const queryUrl = new URLSearchParams(location.search).get("url");
if (queryUrl) $("x-url").value = queryUrl;
health();
loadSources();
loadPublish();
