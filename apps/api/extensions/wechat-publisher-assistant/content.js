function visible(element) {
  if (!element) return false;
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
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

function firstVisible(selectors) {
  for (const doc of allDocuments()) {
    for (const selector of selectors) {
      const match = [...doc.querySelectorAll(selector)].find(visible);
      if (match) return match;
    }
  }
  return null;
}

function setNativeValue(element, value) {
  const prototype = element instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  descriptor?.set?.call(element, value);
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  element.blur();
}

function fillRichEditor(editor, html) {
  editor.focus();
  const doc = editor.ownerDocument;
  const selection = doc.getSelection();
  const range = doc.createRange();
  range.selectNodeContents(editor);
  selection.removeAllRanges();
  selection.addRange(range);
  let inserted = false;
  try {
    inserted = doc.execCommand("insertHTML", false, html);
  } catch {
    inserted = false;
  }
  if (!inserted) editor.innerHTML = html;
  editor.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertFromPaste", data: null }));
  editor.dispatchEvent(new Event("change", { bubbles: true }));
  selection.removeAllRanges();
}

function locateBodyEditor() {
  return firstVisible([
    ".ProseMirror[contenteditable='true']",
    "[contenteditable='true'][data-placeholder*='正文']",
    "[contenteditable='true'][data-placeholder*='内容']",
    ".edui-body-container[contenteditable='true']",
    "#ueditor_0",
    "[contenteditable='true'][role='textbox']",
  ]);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "X2RED_FILL_WECHAT") return false;
  try {
    const payload = message.payload || {};
    const fields = [];
    const title = firstVisible([
      "textarea[placeholder*='标题']",
      "input[placeholder*='标题']",
      "textarea[name*='title']",
      "input[name*='title']",
    ]);
    if (title && payload.title) {
      setNativeValue(title, payload.title);
      fields.push("标题");
    }
    const author = firstVisible([
      "input[placeholder*='作者']",
      "textarea[placeholder*='作者']",
      "input[name*='author']",
    ]);
    if (author && payload.author) {
      setNativeValue(author, payload.author);
      fields.push("作者");
    }
    const body = locateBodyEditor();
    if (!body) throw new Error("未找到公众号正文编辑区域，可能是公众号页面结构已变化");
    if (!payload.body_html) throw new Error("该版本还没有可写入的富文本 HTML");
    fillRichEditor(body, payload.body_html);
    fields.push("富文本正文");
    sendResponse({ ok: true, fields });
  } catch (error) {
    sendResponse({ ok: false, error: error.message || String(error) });
  }
  return true;
});
