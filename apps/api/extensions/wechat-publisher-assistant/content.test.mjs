import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

class FakeElement {
  constructor({ tagName = "DIV", attrs = {}, rect = {}, parent = null, text = "" } = {}) {
    this.tagName = tagName;
    this.attrs = { ...attrs };
    this.id = attrs.id || "";
    this.className = attrs.class || "";
    this.parentElement = parent;
    this.textContent = text;
    this.innerText = text;
    this.maxLength = attrs.maxlength ? Number(attrs.maxlength) : 0;
    this.isContentEditable = attrs.contenteditable === "true";
    this._rect = {
      top: rect.top || 0,
      bottom: rect.bottom ?? ((rect.top || 0) + (rect.height || 0)),
      width: rect.width || 0,
      height: rect.height || 0,
    };
    this.ownerDocument = { getElementById: () => null };
  }
  getAttribute(name) { return this.attrs[name] ?? null; }
  getBoundingClientRect() { return this._rect; }
  contains(other) {
    for (let node = other; node; node = node.parentElement) {
      if (node === this) return true;
    }
    return false;
  }
}

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  Math,
  Date,
  Object,
  String,
  Number,
  Boolean,
  RegExp,
  Error,
  Array,
  Set,
  document: {
    querySelectorAll: () => [],
    addEventListener: () => {},
    removeEventListener: () => {},
  },
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(new URL("./content.js", import.meta.url), "utf8"), sandbox);

const api = sandbox.__X2RED_WECHAT_TESTS__;
assert.ok(api, "test API must be exported");

assert.equal([...api.normalizeTitle(" 标题   有   空格 ")].join(""), "标题 有 空格");
assert.equal([...api.normalizeTitle("甲".repeat(80))].length, 64);

const title = new FakeElement({
  attrs: {
    contenteditable: "true",
    role: "textbox",
    "data-placeholder": "请输入标题",
    maxlength: "64",
    class: "article-title-editor",
  },
  rect: { top: 180, width: 820, height: 150 },
});
const body = new FakeElement({
  attrs: {
    contenteditable: "true",
    role: "textbox",
    class: "ProseMirror editor-content",
    "data-placeholder": "请输入正文",
  },
  rect: { top: 390, width: 900, height: 760 },
});
const genericSmallTextbox = new FakeElement({
  attrs: { contenteditable: "true", role: "textbox" },
  rect: { top: 200, width: 800, height: 120 },
});

assert.ok(api.titleCandidateScore(title) >= api.TITLE_MIN_SCORE, "contenteditable title must be recognized");
assert.ok(api.titleCandidateScore(body) < api.TITLE_MIN_SCORE, "body must not be recognized as title");
assert.ok(api.bodyCandidateScore(body, title) >= api.BODY_MIN_SCORE, "large body editor must be recognized");
assert.ok(api.bodyCandidateScore(title, title) < api.BODY_MIN_SCORE, "title cannot be selected as body");
assert.ok(api.bodyCandidateScore(genericSmallTextbox, title) < api.BODY_MIN_SCORE, "generic small textbox must not be used as body");
assert.equal(api.isTitleLike(title), true);
assert.equal(api.isTitleLike(body), false);

console.log("wechat publisher selector regression tests passed");
