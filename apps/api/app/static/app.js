const state = { sourceId: null, draftId: null };
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
  list.innerHTML = "";
  for (const item of items) {
    const node = $("source-template").content.cloneNode(true);
    const button = node.querySelector("button");
    button.dataset.id = item.id;
    button.classList.toggle("active", item.id === state.sourceId);
    node.querySelector(".source-name").textContent = `@${item.author_handle || item.author_name || "unknown"}`;
    node.querySelector(".source-preview").textContent = item.text_original.slice(0, 90) || "（无正文）";
    button.addEventListener("click", () => selectSource(item.id));
    list.appendChild(node);
  }
  if (selectId) await selectSource(selectId);
}

async function selectSource(id) {
  state.sourceId = id;
  state.draftId = null;
  document.querySelectorAll(".source-item").forEach((el) => el.classList.toggle("active", el.dataset.id === id));
  const item = await api(`/api/sources/${id}`);
  $("empty-detail").hidden = true;
  $("source-detail").hidden = false;
  $("source-author").textContent = `${item.author_name || ""} @${item.author_handle || ""}`;
  $("source-link").href = item.canonical_url;
  $("source-text").textContent = item.text_original;
  renderAssets(item.assets);
  $("related").textContent = item.related.length
    ? `相关上下文 ${item.related.length} 条：` + item.related.map((r) => r.text_original.slice(0, 55)).join(" ｜ ")
    : "当前未加载额外上下文。";
  await loadDrafts(id);
}

function renderAssets(assets) {
  const box = $("assets");
  box.innerHTML = "";
  for (const asset of assets) {
    const wrap = document.createElement("div");
    wrap.className = "asset";
    const url = asset.local_path ? `/api/assets/${asset.id}/file` : asset.remote_url;
    if (asset.kind === "image") wrap.innerHTML = `<img src="${url}" alt=""><div>${asset.state}</div>`;
    else wrap.innerHTML = `<video src="${url}" controls></video><div>${asset.state}</div>`;
    if (asset.error) wrap.title = asset.error;
    box.appendChild(wrap);
  }
}

async function loadDrafts(sourceId) {
  const drafts = await api(`/api/sources/${sourceId}/drafts`);
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
  message($("draft-status"), `当前版本 v${draft.version} · ${draft.created_by}`);
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

$("generate-draft").addEventListener("click", async () => {
  if (!state.sourceId) return;
  const button = $("generate-draft");
  button.disabled = true;
  try {
    const draft = await api(`/api/sources/${state.sourceId}/drafts`, {
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
    const draft = await api(`/api/drafts/${state.draftId}`, {
      method: "PUT",
      body: JSON.stringify({
        title: $("draft-title").value,
        body: $("draft-body").value,
        tags: $("draft-tags").value,
      }),
    });
    showDraft(draft);
    message($("draft-status"), `已保存为新版本 v${draft.version}`, "ok");
  } catch (error) {
    message($("draft-status"), error.message, "error");
  }
});

async function review(decision) {
  if (!state.draftId) return;
  try {
    await api(`/api/drafts/${state.draftId}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, reason: "" }),
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
    const task = await api(`/api/publish/drafts/${state.draftId}/prepare`, { method: "POST" });
    message($("draft-status"), `发布包已生成：${task.package_path}`, "ok");
    await loadPublish();
  } catch (error) {
    message($("draft-status"), error.message, "error");
  }
});

async function loadPublish() {
  const tasks = await api("/api/publish");
  const box = $("publish-list");
  box.innerHTML = "";
  for (const task of tasks) {
    const row = document.createElement("div");
    row.className = "publish-task";
    row.innerHTML = `<div><strong>${task.title}</strong><small>${task.state} · ${task.package_path || "尚未打包"}</small><small class="error-text">${task.error || ""}</small></div>`;
    const button = document.createElement("button");
    button.textContent = "打开小红书预览";
    button.disabled = !["packaged", "failed"].includes(task.state);
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api(`/api/publish/${task.id}/open-xhs`, { method: "POST" });
        await loadPublish();
      } catch (error) {
        alert(error.message);
        button.disabled = false;
      }
    });
    row.appendChild(button);
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
