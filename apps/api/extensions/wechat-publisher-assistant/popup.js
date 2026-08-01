const BASE = "http://127.0.0.1:8787";
const variantSelect = document.getElementById("variant");
const statusBox = document.getElementById("status");
const fillButton = document.getElementById("fill");
const refreshButton = document.getElementById("refresh");

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

async function loadVariants() {
  fillButton.disabled = true;
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
    fillButton.disabled = variants.length === 0;
    status(variants.length ? `已读取 ${variants.length} 个版本。请选择已排版版本。` : "没有公众号版本。", variants.length ? "ok" : "error");
  } catch (error) {
    status(`无法连接 X2RED：${error.message}`, "error");
  }
}

async function fillEditor() {
  const variantId = variantSelect.value;
  if (!variantId) return;
  fillButton.disabled = true;
  status("正在读取富文本并写入公众号编辑器…");
  try {
    const payload = await api(`/api/reviews/wechat/${encodeURIComponent(variantId)}/publisher-payload`);
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !String(tab.url || "").startsWith("https://mp.weixin.qq.com/")) {
      throw new Error("请先打开微信公众号图文编辑器页面");
    }
    const result = await chrome.tabs.sendMessage(tab.id, {
      type: "X2RED_FILL_WECHAT",
      payload,
    });
    if (!result?.ok) throw new Error(result?.error || "公众号编辑器未识别");
    const fields = result.fields || [];
    status(`已写入：${fields.join("、")}。请检查排版、图片和封面后再保存草稿。`, "ok");
  } catch (error) {
    status(error.message, "error");
  } finally {
    fillButton.disabled = false;
  }
}

fillButton.addEventListener("click", fillEditor);
refreshButton.addEventListener("click", loadVariants);
loadVariants();
