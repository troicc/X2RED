const BASE = "http://127.0.0.1:8787";
const variantSelect = document.getElementById("variant");
const statusBox = document.getElementById("status");
const fillButton = document.getElementById("fill");
const copyTitleButton = document.getElementById("copy-title");
const copyBodyButton = document.getElementById("copy-body");
const refreshButton = document.getElementById("refresh");
const payloadCache = new Map();

function status(text, kind = "") {
  statusBox.textContent = text;
  statusBox.className = `status${kind ? ` ${kind}` : ""}`;
}

async function api(path) {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function normalizeTitle(value) {
  return [...String(value || "").replace(/\s+/g, " ").trim()].slice(0, 64).join("");
}

function htmlToPlainText(html) {
  const container = document.createElement("div");
  container.innerHTML = String(html || "");
  return String(container.textContent || "")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function selectedPayload() {
  const variantId = variantSelect.value;
  if (!variantId) throw new Error("请先选择公众号版本");
  if (!payloadCache.has(variantId)) {
    payloadCache.set(
      variantId,
      api(`/api/reviews/wechat/${encodeURIComponent(variantId)}/publisher-payload`)
        .catch((error) => {
          payloadCache.delete(variantId);
          throw error;
        })
    );
  }
  return payloadCache.get(variantId);
}

async function writeRichClipboard(html) {
  const plainText = htmlToPlainText(html);
  if (!html) throw new Error("该版本没有可复制的富文本正文");
  if (navigator.clipboard?.write && globalThis.ClipboardItem) {
    const item = new ClipboardItem({
      "text/html": new Blob([html], { type: "text/html" }),
      "text/plain": new Blob([plainText], { type: "text/plain" }),
    });
    await navigator.clipboard.write([item]);
    return "rich";
  }
  await navigator.clipboard.writeText(plainText);
  return "plain";
}

async function loadVariants() {
  [fillButton, copyTitleButton, copyBodyButton].forEach((button) => { button.disabled = true; });
  status("正在读取已生成的公众号版本…");
  try {
    const variants = await api("/api/platforms/variants?platform=wechat&limit=100");
    variantSelect.replaceChildren();
    variants.forEach((variant) => {
      const option = document.createElement("option");
      option.value = variant.id;
      option.textContent = `v${variant.version} · ${variant.title || "未命名文章"} · ${variant.status}`;
      variantSelect.appendChild(option);
    });
    const disabled = variants.length === 0;
    [fillButton, copyTitleButton, copyBodyButton].forEach((button) => { button.disabled = disabled; });
    status(
      variants.length
        ? `已读取 ${variants.length} 个版本。自动写入会先校验标题与正文目标。`
        : "没有公众号版本。",
      variants.length ? "ok" : "error"
    );
  } catch (error) {
    status(`无法连接 X2RED：${error.message}`, "error");
  }
}

async function fillEditor() {
  const variantId = variantSelect.value;
  if (!variantId) return;
  fillButton.disabled = true;
  status("正在识别标题与正文，并优先调用微信编辑器 API…");
  try {
    const payload = await selectedPayload();
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !String(tab.url || "").startsWith("https://mp.weixin.qq.com/")) {
      throw new Error("请先打开微信公众号图文编辑器页面");
    }
    const result = await chrome.tabs.sendMessage(tab.id, {
      type: "X2RED_FILL_WECHAT",
      payload,
    });
    if (!result?.ok) {
      if (result?.fallback === "clipboard") {
        try {
          const copiedMode = await writeRichClipboard(payload.body_html);
          status(
            `${result.error} 正文已${copiedMode === "rich" ? "按富文本" : "按纯文本"}复制，请点击公众号正文区域后按 Command+V。`,
            "error"
          );
          return;
        } catch {}
      }
      throw new Error(result?.error || "公众号编辑器未识别");
    }
    const methodLabel = {
      official_api_set_content: "微信编辑器 API",
      official_api_insert_html: "微信编辑器插入 API",
      dom_verified: "已校验的正文节点",
    }[result.method] || result.method || "安全写入";
    const warnings = Array.isArray(result.warnings) && result.warnings.length
      ? ` 提醒：${result.warnings.join("；")}。`
      : "";
    status(
      `已写入：${(result.fields || []).join("、")}。正文方式：${methodLabel}。${warnings}请检查图片和封面后保存草稿。`,
      "ok"
    );
  } catch (error) {
    status(error.message, "error");
  } finally {
    fillButton.disabled = false;
  }
}

async function copyTitle() {
  copyTitleButton.disabled = true;
  try {
    const payload = await selectedPayload();
    const title = normalizeTitle(payload.title);
    if (!title) throw new Error("该版本没有标题");
    await navigator.clipboard.writeText(title);
    status(`标题已复制（${[...title].length}/64），请点击标题区域后按 Command+V。`, "ok");
  } catch (error) {
    status(error.message, "error");
  } finally {
    copyTitleButton.disabled = false;
  }
}

async function copyBody() {
  copyBodyButton.disabled = true;
  try {
    const payload = await selectedPayload();
    const mode = await writeRichClipboard(payload.body_html);
    status(
      mode === "rich"
        ? "富文本正文已复制。请点击公众号正文区域后按 Command+V，格式会随 HTML 一起粘贴。"
        : "浏览器不支持富文本剪贴板，已复制纯文本正文。",
      "ok"
    );
  } catch (error) {
    status(error.message, "error");
  } finally {
    copyBodyButton.disabled = false;
  }
}

fillButton.addEventListener("click", fillEditor);
copyTitleButton.addEventListener("click", copyTitle);
copyBodyButton.addEventListener("click", copyBody);
refreshButton.addEventListener("click", () => {
  payloadCache.clear();
  void loadVariants();
});
variantSelect.addEventListener("change", () => status("已切换版本。可自动写入，也可分别复制标题和富文本正文。"));
loadVariants();
