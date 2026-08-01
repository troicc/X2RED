const BRIDGE_REQUEST_EVENT = "x2red:wechat-editor-request";
const BRIDGE_RESPONSE_EVENT = "x2red:wechat-editor-response";
const TITLE_MAX_LENGTH = 64;
const TITLE_MIN_SCORE = 50;
const BODY_MIN_SCORE = 70;

function ownerWindow(element) {
  return element?.ownerDocument?.defaultView || window;
}

function visible(element) {
  if (!element || typeof element.getBoundingClientRect !== "function") return false;
  const view = ownerWindow(element);
  const style = view.getComputedStyle ? view.getComputedStyle(element) : null;
  const rect = element.getBoundingClientRect();
  return (!style || (style.display !== "none" && style.visibility !== "hidden"))
    && rect.width > 0
    && rect.height > 0;
}

function allDocuments() {
  const docs = [document];
  document.querySelectorAll("iframe").forEach((frame) => {
    try {
      if (frame.contentDocument) docs.push(frame.contentDocument);
    } catch {}
  });
  return docs;
}

function uniqueElements(elements) {
  return [...new Set(elements.filter(Boolean))];
}

function collectElements(selectors) {
  const elements = [];
  for (const doc of allDocuments()) {
    for (const selector of selectors) {
      try {
        elements.push(...doc.querySelectorAll(selector));
      } catch {}
    }
    const body = doc.body;
    if (body?.getAttribute?.("contenteditable") === "true") elements.push(body);
  }
  return uniqueElements(elements).filter(visible);
}

function rectOf(element) {
  try {
    const rect = element.getBoundingClientRect();
    return {
      top: Number(rect.top || 0),
      bottom: Number(rect.bottom || rect.top + rect.height || 0),
      width: Number(rect.width || 0),
      height: Number(rect.height || 0),
    };
  } catch {
    return { top: 0, bottom: 0, width: 0, height: 0 };
  }
}

function attributeText(element) {
  if (!element) return "";
  const values = [
    element.id,
    typeof element.className === "string" ? element.className : "",
    element.getAttribute?.("name"),
    element.getAttribute?.("placeholder"),
    element.getAttribute?.("data-placeholder"),
    element.getAttribute?.("aria-label"),
    element.getAttribute?.("role"),
    element.getAttribute?.("data-slate-editor"),
  ];
  return values.filter(Boolean).join(" ").toLowerCase();
}

function contextText(element) {
  const values = [];
  const labelledBy = element?.getAttribute?.("aria-labelledby");
  if (labelledBy && element.ownerDocument) {
    labelledBy.split(/\s+/).forEach((id) => {
      const label = element.ownerDocument.getElementById(id);
      if (label?.textContent) values.push(label.textContent.slice(0, 120));
    });
  }
  if (element?.labels) {
    [...element.labels].forEach((label) => {
      if (label?.textContent) values.push(label.textContent.slice(0, 120));
    });
  }
  let parent = element?.parentElement;
  for (let depth = 0; parent && depth < 2; depth += 1, parent = parent.parentElement) {
    values.push(attributeText(parent));
    const text = String(parent.textContent || "").trim().replace(/\s+/g, " ");
    if (text && text.length <= 180) values.push(text);
  }
  return values.filter(Boolean).join(" ").toLowerCase();
}

function maxLengthOf(element) {
  const raw = element?.getAttribute?.("maxlength");
  const value = raw == null ? Number(element?.maxLength || 0) : Number(raw);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function isContentEditable(element) {
  return element?.getAttribute?.("contenteditable") === "true"
    || element?.isContentEditable === true;
}

function isTextField(element) {
  const tag = String(element?.tagName || "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || isContentEditable(element);
}

function isTitleLike(element) {
  if (!element) return false;
  const semantic = `${attributeText(element)} ${contextText(element)}`;
  if (/(正文|content-body|editor-content|ueditor|prosemirror|slate-editor)/i.test(semantic)) return false;
  if (/(标题|\btitle\b|title_|_title)/i.test(semantic)) return true;
  const maxLength = maxLengthOf(element);
  const rect = rectOf(element);
  return maxLength > 0 && maxLength <= 80 && rect.height > 0 && rect.height <= 220;
}

function titleCandidateScore(element) {
  if (!isTextField(element)) return -1000;
  const semantic = attributeText(element);
  const context = contextText(element);
  const rect = rectOf(element);
  const maxLength = maxLengthOf(element);
  const tag = String(element.tagName || "").toUpperCase();
  let score = 0;

  if (element.id === "title") score += 140;
  if (/(placeholder|data-placeholder|aria-label)/i.test(semantic) && /标题/.test(semantic)) score += 110;
  if (/(标题|\btitle\b|title_|_title)/i.test(semantic)) score += 80;
  if (/标题/.test(context)) score += 35;
  if (tag === "INPUT" || tag === "TEXTAREA") score += 18;
  if (isContentEditable(element)) score += 8;
  if (maxLength > 0 && maxLength <= 128) score += 26;
  if (rect.height >= 28 && rect.height <= 220) score += 18;
  if (rect.width >= 300) score += 10;

  if (/(作者|author)/i.test(`${semantic} ${context}`)) score -= 130;
  if (/(正文|ueditor|prosemirror|slate-editor|editor-content|content-body)/i.test(`${semantic} ${context}`)) score -= 180;
  if (rect.height > 300) score -= 100;
  if (maxLength > 256) score -= 60;
  return score;
}

function bodyCandidateScore(element, titleElement = null) {
  if (!element || !isContentEditable(element)) return -1000;
  if (titleElement && element === titleElement) return -10000;
  if (titleElement && (element.contains?.(titleElement) || titleElement.contains?.(element))) return -5000;

  const semantic = attributeText(element);
  const context = contextText(element);
  const rect = rectOf(element);
  const maxLength = maxLengthOf(element);
  let score = 10;

  if (element.id === "ueditor_0") score += 220;
  if (/prosemirror/i.test(semantic)) score += 190;
  if (/edui-body-container|slate-editor/i.test(semantic)) score += 175;
  if (/(正文|content-body|editor-content|article-content)/i.test(`${semantic} ${context}`)) score += 135;
  if (/(ueditor|editor|content|article)/i.test(semantic)) score += 45;
  if (rect.height >= 260) score += 80;
  if (rect.height >= 500) score += 30;
  if (rect.width >= 500) score += 30;
  if (rect.width * rect.height >= 220000) score += 24;
  if (titleElement) {
    const titleRect = rectOf(titleElement);
    if (rect.top >= titleRect.bottom - 20) score += 30;
  }

  if (isTitleLike(element)) score -= 300;
  if (/(标题|\btitle\b|作者|author)/i.test(`${semantic} ${context}`)) score -= 260;
  if (maxLength > 0 && maxLength <= 128) score -= 180;
  if (rect.height > 0 && rect.height < 120) score -= 120;
  return score;
}

function locateTitleEditor() {
  const candidates = collectElements([
    "textarea#title",
    "input#title",
    "textarea[placeholder*='标题']",
    "input[placeholder*='标题']",
    "textarea[name*='title']",
    "input[name*='title']",
    "[contenteditable='true'][data-placeholder*='标题']",
    "[contenteditable='true'][aria-label*='标题']",
    "[contenteditable='true'][id*='title']",
    "[contenteditable='true'][class*='title']",
    "input",
    "textarea",
    "[contenteditable='true']",
  ]);
  const ranked = candidates
    .map((element) => ({ element, score: titleCandidateScore(element) }))
    .sort((a, b) => b.score - a.score);
  return ranked[0]?.score >= TITLE_MIN_SCORE ? ranked[0].element : null;
}

function locateAuthorEditor() {
  const candidates = collectElements([
    "input#author",
    "textarea#author",
    "input[placeholder*='作者']",
    "textarea[placeholder*='作者']",
    "input[name*='author']",
    "textarea[name*='author']",
  ]);
  return candidates.find((element) => {
    const semantic = `${attributeText(element)} ${contextText(element)}`;
    return /(作者|author)/i.test(semantic);
  }) || null;
}

function locateBodyEditor(titleElement) {
  const candidates = collectElements([
    ".ProseMirror[contenteditable='true']",
    "[data-slate-editor='true']",
    ".edui-body-container[contenteditable='true']",
    "#ueditor_0[contenteditable='true']",
    "[contenteditable='true'][data-placeholder*='正文']",
    "[contenteditable='true'][aria-label*='正文']",
    "[contenteditable='true'][data-placeholder*='内容']",
    "[contenteditable='true'][aria-label*='内容']",
    ".editor-content [contenteditable='true']",
    "[contenteditable='true'][role='textbox']",
    "[contenteditable='true']",
  ]);
  const ranked = candidates
    .map((element) => ({ element, score: bodyCandidateScore(element, titleElement) }))
    .sort((a, b) => b.score - a.score);
  return ranked[0]?.score >= BODY_MIN_SCORE ? ranked[0].element : null;
}

function sliceCodePoints(value, limit) {
  return [...String(value || "")].slice(0, limit).join("");
}

function normalizeTitle(value) {
  return sliceCodePoints(String(value || "").replace(/\s+/g, " ").trim(), TITLE_MAX_LENGTH);
}

function readFieldValue(element) {
  if (!element) return "";
  const tag = String(element.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA") return String(element.value || "");
  return String(element.innerText || element.textContent || "").trim();
}

function dispatchInputEvents(element, inputType, data) {
  const view = ownerWindow(element);
  try {
    element.dispatchEvent(new view.InputEvent("input", {
      bubbles: true,
      inputType,
      data,
    }));
  } catch {
    element.dispatchEvent(new view.Event("input", { bubbles: true }));
  }
  element.dispatchEvent(new view.Event("change", { bubbles: true }));
}

function setNativeValue(element, value) {
  const view = ownerWindow(element);
  const tag = String(element.tagName || "").toUpperCase();
  const prototype = tag === "TEXTAREA"
    ? view.HTMLTextAreaElement?.prototype
    : view.HTMLInputElement?.prototype;
  const descriptor = prototype && Object.getOwnPropertyDescriptor(prototype, "value");
  if (descriptor?.set) descriptor.set.call(element, value);
  else element.value = value;
  dispatchInputEvents(element, "insertText", value);
  element.blur?.();
}

function setEditableText(element, value) {
  const doc = element.ownerDocument;
  const view = ownerWindow(element);
  element.focus?.();
  const selection = doc.getSelection?.();
  let inserted = false;
  if (selection && doc.createRange) {
    const range = doc.createRange();
    range.selectNodeContents(element);
    selection.removeAllRanges();
    selection.addRange(range);
    try {
      inserted = Boolean(doc.execCommand?.("insertText", false, value));
    } catch {
      inserted = false;
    }
    selection.removeAllRanges();
  }
  if (!inserted) element.textContent = value;
  try {
    element.dispatchEvent(new view.InputEvent("input", {
      bubbles: true,
      inputType: "insertText",
      data: value,
    }));
  } catch {
    element.dispatchEvent(new view.Event("input", { bubbles: true }));
  }
  element.dispatchEvent(new view.Event("change", { bubbles: true }));
  element.blur?.();
}

function setFieldText(element, value) {
  const tag = String(element.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA") setNativeValue(element, value);
  else setEditableText(element, value);
}

function plainTextFromHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = String(html || "");
  return String(template.content?.textContent || template.textContent || "")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function fillRichEditor(editor, html) {
  editor.focus?.();
  const doc = editor.ownerDocument;
  const selection = doc.getSelection?.();
  let inserted = false;
  if (selection && doc.createRange) {
    const range = doc.createRange();
    range.selectNodeContents(editor);
    selection.removeAllRanges();
    selection.addRange(range);
    try {
      inserted = Boolean(doc.execCommand?.("insertHTML", false, html));
    } catch {
      inserted = false;
    }
    selection.removeAllRanges();
  }
  if (!inserted) editor.innerHTML = html;
  dispatchInputEvents(editor, "insertFromPaste", null);
}

function richEditorLooksFilled(editor, html) {
  const expected = plainTextFromHtml(html);
  const actual = String(editor?.innerText || editor?.textContent || "")
    .replace(/\s+/g, " ")
    .trim();
  const minimum = Math.min(Math.max(Math.floor(expected.length * 0.12), 8), 120);
  return actual.length >= minimum || Boolean(editor?.querySelector?.("img,video,table"));
}

function requestPageBridge(action, payload, timeoutMs = 7000) {
  return new Promise((resolve) => {
    const requestId = globalThis.crypto?.randomUUID?.()
      || `x2red-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    let finished = false;
    const finish = (result) => {
      if (finished) return;
      finished = true;
      document.removeEventListener(BRIDGE_RESPONSE_EVENT, onResponse);
      clearTimeout(timer);
      resolve(result);
    };
    const onResponse = (event) => {
      try {
        const detail = JSON.parse(String(event.detail || "{}"));
        if (detail.requestId !== requestId) return;
        finish(detail.result || { ok: false, code: "empty_bridge_response" });
      } catch {}
    };
    const timer = setTimeout(() => finish({ ok: false, code: "bridge_timeout" }), timeoutMs);
    document.addEventListener(BRIDGE_RESPONSE_EVENT, onResponse);
    document.dispatchEvent(new CustomEvent(BRIDGE_REQUEST_EVENT, {
      detail: JSON.stringify({ requestId, action, payload }),
    }));
  });
}

function createUserError(message, code, fallback = "clipboard") {
  const error = new Error(message);
  error.code = code;
  error.fallback = fallback;
  return error;
}

async function fillWechat(payload) {
  const fields = [];
  const warnings = [];
  const titleValue = normalizeTitle(payload.title);
  const title = locateTitleEditor();

  if (payload.title && !title) {
    throw createUserError("未能高置信识别公众号标题区域，已停止自动写入，避免正文再次进入标题。", "title_not_found");
  }
  if (title && titleValue) {
    setFieldText(title, titleValue);
    const readBack = normalizeTitle(readFieldValue(title));
    if (readBack !== titleValue) {
      throw createUserError("公众号标题写入后校验失败，已停止继续写正文。", "title_verification_failed");
    }
    fields.push("标题");
    if ([...String(payload.title || "")].length > TITLE_MAX_LENGTH) {
      warnings.push("标题已按公众号 64 字限制截断");
    }
  }

  const author = locateAuthorEditor();
  if (author && payload.author) {
    setFieldText(author, sliceCodePoints(payload.author, 16));
    fields.push("作者");
  } else if (payload.author) {
    warnings.push("未识别作者栏，作者未自动写入");
  }

  if (!payload.body_html) {
    throw createUserError("该版本还没有可写入的富文本 HTML。", "body_html_missing", "none");
  }

  const expectedTitle = title ? normalizeTitle(readFieldValue(title)) : "";
  let method = "";
  const apiResult = await requestPageBridge("set_content", { html: payload.body_html });
  if (apiResult?.ok) {
    method = apiResult.method || "official_api";
  } else {
    const body = locateBodyEditor(title);
    if (!body) {
      throw createUserError(
        "微信正文编辑器未能高置信识别。为避免误填，已停止自动写入，请使用“复制富文本正文”后在正文区域按 Command+V。",
        "body_not_found"
      );
    }
    if (body === title || isTitleLike(body)) {
      throw createUserError("检测到正文目标与标题区域冲突，已阻止写入。", "body_title_collision");
    }
    fillRichEditor(body, payload.body_html);
    if (!richEditorLooksFilled(body, payload.body_html)) {
      throw createUserError("正文写入后回读校验失败，已停止自动操作。", "body_verification_failed");
    }
    method = "dom_verified";
  }

  if (title && normalizeTitle(readFieldValue(title)) !== expectedTitle) {
    setFieldText(title, expectedTitle);
    throw createUserError(
      "检测到正文写入影响了标题，标题已恢复，正文自动写入已判定失败。请改用富文本复制。",
      "title_polluted"
    );
  }

  fields.push("富文本正文");
  return { ok: true, fields, method, warnings, title_length: [...titleValue].length };
}

if (globalThis.chrome?.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "X2RED_FILL_WECHAT") return false;
    void fillWechat(message.payload || {})
      .then(sendResponse)
      .catch((error) => {
        sendResponse({
          ok: false,
          error: error.message || String(error),
          code: error.code || "wechat_fill_failed",
          fallback: error.fallback || "clipboard",
        });
      });
    return true;
  });
}

globalThis.__X2RED_WECHAT_TESTS__ = Object.freeze({
  TITLE_MAX_LENGTH,
  TITLE_MIN_SCORE,
  BODY_MIN_SCORE,
  normalizeTitle,
  isTitleLike,
  titleCandidateScore,
  bodyCandidateScore,
});
