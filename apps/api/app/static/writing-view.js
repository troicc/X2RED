const STEPS = [
  ["materials", "选择材料", "从来源、草稿和平台稿中多选"],
  ["article", "文章类型", "明确内容任务，不先锁死表达"],
  ["platform", "发布平台", "选择实际进入的工作台"],
  ["reader", "读者与承诺", "写清为谁解决什么问题"],
  ["mode", "写作模式", "决定人工阶段确认节奏"],
  ["visual", "视觉路线", "确认制图路径后再交接"],
];

const LABELS = {
  articleType: {
    deep_explainer: "深度解释",
    news_digest: "资讯速览",
    editorial_view: "编辑观察",
    light_series: "轻内容图组",
  },
  platform: {
    xiaohongshu: "小红书",
    wechat_long: "公众号长文",
    wechat_light: "公众号轻内容",
  },
  writingMode: { studio: "工作室模式 · 分阶段人工确认", fast: "快速模式 · 自动推进到人工终审" },
  visualRoute: {
    html_cards: "HTML / CSS 小红书卡片",
    wechat_inline: "公众号封面与段落配图",
    minimal_zine: "Minimal Zine 无字锚点 + 本地中文",
    none: "暂不制图",
  },
};

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function sourceIdFromRefs(refs) {
  return refs.find((value) => value.startsWith("source:"))?.slice(7) || "";
}

function materialGroup(material) {
  if (material.kind !== "source") return material.kind;
  if (material.platform === "pool") return "pool";
  if (["x", "xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"].includes(material.platform)) {
    return material.platform;
  }
  return "web";
}

const MATERIAL_GROUPS = [
  ["pool", "冻结语料批次"], ["x", "X / 信号"], ["xhs", "小红书"], ["dy", "抖音"],
  ["ks", "快手"], ["bili", "B站"], ["wb", "微博"], ["tieba", "贴吧"],
  ["zhihu", "知乎"], ["web", "网页与文档"], ["draft_revision", "草稿版本"],
  ["platform_variant", "平台成稿"],
];

function injectNavigation() {
  const nav = document.querySelector(".primary-nav");
  if (!nav || nav.querySelector('[data-view="creative-task-view"]')) return;
  const first = nav.querySelector(".nav-item");
  const button = element("button", "nav-item");
  button.type = "button";
  button.dataset.view = "creative-task-view";
  button.innerHTML = '<span class="nav-icon" aria-hidden="true"></span><span>新建创作任务</span>';
  button.addEventListener("click", () => window.setView?.("creative-task-view"));
  nav.insertBefore(button, first);
}

function injectView() {
  const stack = document.querySelector(".view-stack");
  if (!stack || document.getElementById("creative-task-view")) return null;
  const view = element("section", "app-view creative-task-view");
  view.id = "creative-task-view";
  view.innerHTML = `
    <section class="page-intro studio-intro">
      <span class="section-kicker">UNIFIED CREATIVE BRIEF</span>
      <h2 tabindex="-1">新建创作任务</h2>
      <p>一次说明材料、读者和路线，再交给现有工作台继续编辑、制图与人工审核。</p>
    </section>
    <section class="creative-wizard surface" aria-labelledby="creative-wizard-title">
      <header class="creative-wizard-head">
        <div><span class="section-kicker">TASK WIZARD</span><h3 id="creative-wizard-title">创作简报</h3></div>
        <span id="creative-wizard-save" class="status-chip neutral" role="status">保存在本机</span>
      </header>
      <ol id="creative-wizard-steps" class="creative-wizard-steps" role="tablist" aria-label="创作任务步骤"></ol>
      <form id="creative-task-form" class="creative-task-form" novalidate>
        <section class="creative-step-panel" data-step="0" role="tabpanel">
          <div class="creative-step-heading"><span>01</span><div><h3>选择材料</h3><p>来源、冻结批次、草稿和平台成稿可以一起进入任务。</p></div></div>
          <label class="creative-search-field">搜索材料<input id="creative-material-search" type="search" autocomplete="off" placeholder="搜索标题、作者或摘要" /></label>
          <div id="creative-material-count" class="creative-selection-count">已选 0 个</div>
          <div id="creative-material-list" class="creative-material-list" role="group" aria-label="统一创作任务材料"></div>
        </section>
        <section class="creative-step-panel" data-step="1" role="tabpanel" hidden>
          <div class="creative-step-heading"><span>02</span><div><h3>文章类型</h3><p>类型影响写作目标，不替代来源证据。</p></div></div>
          <div class="creative-choice-grid" data-field="articleType"></div>
        </section>
        <section class="creative-step-panel" data-step="2" role="tabpanel" hidden>
          <div class="creative-step-heading"><span>03</span><div><h3>选择平台</h3><p>完成后会交接到对应的现有工作台，不丢失旧入口。</p></div></div>
          <div class="creative-choice-grid" data-field="platform"></div>
        </section>
        <section class="creative-step-panel" data-step="3" role="tabpanel" hidden>
          <div class="creative-step-heading"><span>04</span><div><h3>读者与文章承诺</h3><p>用可验证、可交付的语言描述读完后的变化。</p></div></div>
          <label class="creative-long-field">目标读者<textarea id="creative-reader" rows="4" maxlength="2000" placeholder="例如：关注 AI 工程、但不写底层 CUDA 的技术读者" required></textarea></label>
          <label class="creative-long-field">文章承诺<textarea id="creative-promise" rows="4" maxlength="2000" placeholder="例如：读完后能判断三类方案的适用边界，而不是只记住产品名" required></textarea></label>
        </section>
        <section class="creative-step-panel" data-step="4" role="tabpanel" hidden>
          <div class="creative-step-heading"><span>05</span><div><h3>写作模式</h3><p>快速模式仍保留最终人工事实与版权审核。</p></div></div>
          <div class="creative-choice-grid" data-field="writingMode"></div>
        </section>
        <section class="creative-step-panel" data-step="5" role="tabpanel" hidden>
          <div class="creative-step-heading"><span>06</span><div><h3>视觉路线与交接</h3><p>图片模型只负责适合的视觉部分；最终中文排版继续由本地工具完成。</p></div></div>
          <div class="creative-choice-grid" data-field="visualRoute"></div>
          <section id="creative-task-summary" class="creative-task-summary" aria-live="polite"></section>
        </section>
        <div id="creative-task-error" class="inline-status" role="alert"></div>
        <footer class="creative-wizard-actions">
          <button id="creative-step-back" class="secondary-action" type="button">上一步</button>
          <button id="creative-step-next" class="primary-action" type="button">下一步</button>
          <button id="creative-task-handoff" class="primary-action" type="submit" hidden>保存并进入工作台</button>
        </footer>
      </form>
    </section>`;
  const publish = document.getElementById("publish-view");
  stack.insertBefore(view, publish || stack.firstChild);
  return view;
}

function renderChoiceGroup(view, field, values, store) {
  const root = view.querySelector(`[data-field="${field}"]`);
  root.replaceChildren();
  Object.entries(values).forEach(([value, label]) => {
    const option = element("label", "creative-choice");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = `creative-${field}`;
    input.value = value;
    input.checked = store.get()[field] === value;
    const copy = element("span", "creative-choice-copy");
    copy.append(element("strong", "", label), element("small", "", {
      deep_explainer: "从证据到判断，适合多阶段研究与审稿",
      news_digest: "压缩信息密度，保留事实边界和来源",
      editorial_view: "突出编辑判断，同时标清不确定项",
      light_series: "用短文案与连续图组完成单一叙事",
      xiaohongshu: "进入小红书编辑、卡片与审核链",
      wechat_long: "进入公众号长文或深度写作链",
      wechat_light: "进入公众号轻内容与 Minimal Zine 链",
      studio: "在研究、结构、写作和审稿阶段逐步确认",
      fast: "自动推进阶段，但不跳过最终人工门禁",
      html_cards: "结构化 HTML/CSS 渲染，确保中文准确",
      wechat_inline: "封面对、段落配图 Prompt 与人工回传",
      minimal_zine: "无字视觉锚点，中文和版式由 X2RED 本地合成",
      none: "先完成文字，稍后再决定视觉路线",
    }[value] || ""));
    option.append(input, copy);
    input.addEventListener("change", () => {
      const patch = { [field]: value, handoffState: "draft" };
      if (field === "platform") {
        patch.visualRoute = { xiaohongshu: "html_cards", wechat_long: "wechat_inline", wechat_light: "minimal_zine" }[value];
      }
      if (field === "articleType" && value === "light_series") {
        patch.platform = "wechat_light";
        patch.visualRoute = "minimal_zine";
      }
      store.update(patch, `choose-${field}`);
      if (field === "platform" || (field === "articleType" && value === "light_series")) {
        renderChoiceGroup(view, "platform", LABELS.platform, store);
        renderChoiceGroup(view, "visualRoute", LABELS.visualRoute, store);
      }
    });
    root.appendChild(option);
  });
}

function renderMaterials(view, materials, store) {
  const root = view.querySelector("#creative-material-list");
  const query = view.querySelector("#creative-material-search").value.trim().toLowerCase();
  const selected = new Set(store.get().materialRefs);
  root.replaceChildren();
  MATERIAL_GROUPS.forEach(([groupId, label]) => {
    const values = materials.filter((item) => materialGroup(item) === groupId && (
      !query || `${item.title} ${item.author} ${item.excerpt}`.toLowerCase().includes(query)
    ));
    if (!values.length) return;
    const group = element("section", "creative-material-group");
    group.appendChild(element("h4", "", label));
    const list = element("div", "creative-material-options");
    values.forEach((item) => {
      const row = element("label", "creative-material-option");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = item.ref;
      input.checked = selected.has(item.ref);
      const copy = element("span");
      copy.append(
        element("strong", "", item.title || "未命名材料"),
        element("small", "", [item.author, item.excerpt].filter(Boolean).join(" · ") || "无摘要"),
      );
      row.append(input, copy);
      input.addEventListener("change", () => {
        const next = new Set(store.get().materialRefs);
        if (input.checked) next.add(item.ref); else next.delete(item.ref);
        store.update({ materialRefs: [...next], handoffState: "draft" }, "materials");
        view.querySelector("#creative-material-count").textContent = `已选 ${next.size} 个`;
      });
      list.appendChild(row);
    });
    group.appendChild(list);
    root.appendChild(group);
  });
  if (!root.children.length) root.appendChild(element("p", "creative-empty-copy", "没有符合当前搜索的材料。"));
  view.querySelector("#creative-material-count").textContent = `已选 ${selected.size} 个`;
}

function updateSummary(view, store) {
  const task = store.get();
  const summary = view.querySelector("#creative-task-summary");
  summary.replaceChildren();
  const title = element("div", "creative-summary-head");
  title.append(element("span", "section-kicker", "HANDOFF REVIEW"), element("h3", "", "交接前确认"));
  const list = element("dl", "creative-summary-grid");
  [
    ["材料", `${task.materialRefs.length} 个`],
    ["文章类型", LABELS.articleType[task.articleType]],
    ["平台", LABELS.platform[task.platform]],
    ["写作模式", LABELS.writingMode[task.writingMode]],
    ["视觉路线", LABELS.visualRoute[task.visualRoute]],
    ["目标读者", task.reader || "待填写"],
    ["文章承诺", task.promise || "待填写"],
  ].forEach(([term, description]) => list.append(element("dt", "", term), element("dd", "", description)));
  summary.append(title, list);
}

function validateStep(step, task) {
  if (step === 0 && !task.materialRefs.length) return "请至少选择一个材料。";
  if (step === 3 && !task.reader.trim()) return "请填写目标读者。";
  if (step === 3 && !task.promise.trim()) return "请填写文章承诺。";
  return "";
}

function dispatchHandoff(task) {
  const sourceId = sourceIdFromRefs(task.materialRefs);
  const detail = { ...task, sourceId };
  document.dispatchEvent(new CustomEvent("x2red:creative-task-handoff", { detail }));
  if (task.platform === "xiaohongshu") {
    window.setView?.("workbench-view");
    if (sourceId && typeof window.loadSources === "function") void window.loadSources(sourceId);
  } else {
    window.setView?.("wechat-view");
    if (task.platform === "wechat_light") {
      window.setTimeout(() => document.dispatchEvent(new CustomEvent("x2red:open-wechat-light", {
        detail: { sourceId },
      })), 0);
    }
  }
}

export async function initWritingView({ store, api }) {
  injectNavigation();
  const view = injectView() || document.getElementById("creative-task-view");
  if (!view || view.dataset.creativeReady) return;
  view.dataset.creativeReady = "true";
  const steps = view.querySelector("#creative-wizard-steps");
  STEPS.forEach(([key, label], index) => {
    const item = element("li", "creative-wizard-step");
    const button = element("button", "", `${String(index + 1).padStart(2, "0")} · ${label}`);
    button.type = "button";
    button.dataset.step = String(index);
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => setStep(index, true));
    item.dataset.key = key;
    item.appendChild(button);
    steps.appendChild(item);
  });

  renderChoiceGroup(view, "articleType", LABELS.articleType, store);
  renderChoiceGroup(view, "platform", LABELS.platform, store);
  renderChoiceGroup(view, "writingMode", LABELS.writingMode, store);
  renderChoiceGroup(view, "visualRoute", LABELS.visualRoute, store);
  view.querySelectorAll(".creative-step-heading h3").forEach((heading) => { heading.tabIndex = -1; });
  const reader = view.querySelector("#creative-reader");
  const promise = view.querySelector("#creative-promise");
  reader.value = store.get().reader;
  promise.value = store.get().promise;
  reader.addEventListener("input", () => store.update({ reader: reader.value, handoffState: "draft" }, "reader"));
  promise.addEventListener("input", () => store.update({ promise: promise.value, handoffState: "draft" }, "promise"));

  let materials = [];
  const materialRoot = view.querySelector("#creative-material-list");
  materialRoot.appendChild(element("p", "creative-loading", "正在读取可用材料…"));
  try {
    materials = await api.get("/api/writing/material-options?limit=500");
    renderMaterials(view, materials, store);
  } catch (error) {
    materialRoot.replaceChildren(element("p", "creative-empty-copy", `材料读取失败：${error.message}`));
  }
  view.querySelector("#creative-material-search").addEventListener("input", () => renderMaterials(view, materials, store));

  const errorNode = view.querySelector("#creative-task-error");
  const back = view.querySelector("#creative-step-back");
  const next = view.querySelector("#creative-step-next");
  const handoff = view.querySelector("#creative-task-handoff");

  function setStep(requested, focus = false) {
    const step = Math.min(5, Math.max(0, requested));
    store.update({ step }, "step");
    view.querySelectorAll(".creative-step-panel").forEach((panel) => {
      panel.hidden = Number(panel.dataset.step) !== step;
    });
    view.querySelectorAll("[role=tab]").forEach((tab, index) => {
      const active = index === step;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      tab.closest("li").classList.toggle("is-active", active);
      tab.closest("li").classList.toggle("is-complete", index < step);
    });
    back.hidden = step === 0;
    next.hidden = step === 5;
    handoff.hidden = step !== 5;
    errorNode.textContent = "";
    updateSummary(view, store);
    if (focus) view.querySelector(`.creative-step-panel[data-step="${step}"] h3`)?.focus({ preventScroll: true });
  }

  steps.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    setStep(store.get().step + (event.key === "ArrowRight" ? 1 : -1), true);
    view.querySelector(`[role=tab][data-step="${store.get().step}"]`)?.focus();
  });
  back.addEventListener("click", () => setStep(store.get().step - 1, true));
  next.addEventListener("click", () => {
    const task = store.get();
    const error = validateStep(task.step, task);
    if (error) {
      errorNode.textContent = error;
      view.querySelector(`.creative-step-panel[data-step="${task.step}"] input, .creative-step-panel[data-step="${task.step}"] textarea`)?.focus();
      return;
    }
    setStep(task.step + 1, true);
  });
  view.querySelector("#creative-task-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const task = store.get();
    const error = validateStep(0, task) || validateStep(3, task);
    if (error) {
      errorNode.textContent = error;
      setStep(!task.materialRefs.length ? 0 : 3, true);
      return;
    }
    const ready = store.update({ handoffState: "handed_off" }, "handoff");
    dispatchHandoff(ready);
  });
  store.subscribe(() => {
    updateSummary(view, store);
    const saved = view.querySelector("#creative-wizard-save");
    saved.textContent = "已自动保存到本机";
    window.setTimeout(() => { saved.textContent = "保存在本机"; }, 1200);
  });
  setStep(store.get().step);
}
