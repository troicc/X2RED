(() => {
  const reviewState = {
    xhsArtifact: null,
    wechatVariant: null,
    moduleArtifact: null,
    coverArtifact: null,
    busy: false,
  };

  const pageTypes = [
    ["hero_cover", "封面"],
    ["key_result", "核心结果"],
    ["concept_diagram", "概念图解"],
    ["before_after", "前后对比"],
    ["workflow_flow", "流程"],
    ["key_takeaways", "关键要点"],
    ["opinion_close", "判断收束"],
  ];
  const moduleTypes = [
    ["paragraph", "正文段落"],
    ["heading", "章节标题"],
    ["quote", "引用/重点框"],
    ["list", "列表"],
    ["code", "代码块"],
    ["image", "图片"],
  ];

  function callApi(path, options = {}) {
    if (typeof api === "function") return api(path, options);
    return fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    }).then(async (response) => {
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
      return response.status === 204 ? null : response.json();
    });
  }

  function parse(value, fallback = {}) {
    try { return JSON.parse(value || ""); } catch { return fallback; }
  }

  function node(tag, className = "", text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  function select(values, selected = "") {
    const element = document.createElement("select");
    values.forEach(([value, label]) => element.add(new Option(label, value)));
    element.value = selected;
    return element;
  }

  function injectStyles() {
    if (document.getElementById("review-v09-style")) return;
    const style = document.createElement("style");
    style.id = "review-v09-style";
    style.textContent = `
.review-launch{border:1px solid #725cff!important;background:#f0edff!important;color:#4b38c7!important}.review-overlay{position:fixed;z-index:1200;inset:0;display:grid;grid-template-columns:1fr min(760px,92vw);background:#11182780;backdrop-filter:blur(8px)}.review-drawer{grid-column:2;height:100vh;overflow:auto;background:#f7f8fc;box-shadow:-28px 0 80px #0003}.review-head{position:sticky;z-index:20;top:0;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:22px 26px;border-bottom:1px solid #e0e4ee;background:#ffffffed;backdrop-filter:blur(18px)}.review-head h2{margin:0;font-size:24px}.review-head p{margin:5px 0 0;color:#667085;font-size:13px}.review-close{width:42px;height:42px;border:0;border-radius:13px;background:#eef1f6;font-size:22px;cursor:pointer}.review-body{padding:24px 26px 120px}.review-section{margin-bottom:20px;padding:18px;border:1px solid #e0e4ee;border-radius:18px;background:#fff}.review-section h3{margin:0 0 14px}.review-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.review-grid label,.review-field{display:grid;gap:7px;color:#526071;font-size:12px;font-weight:760}.review-grid select,.review-grid input,.review-grid textarea,.review-field input,.review-field textarea,.review-field select{width:100%;border:1px solid #d9dfeb;border-radius:11px;background:#fff;padding:10px 11px;color:#111827;font:inherit}.review-page,.review-module{margin:12px 0;padding:16px;border:1px solid #dfe4ef;border-radius:16px;background:#fff}.review-page-top,.review-module-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.review-page-top strong,.review-module-top strong{font-size:14px}.review-mini-actions{display:flex;gap:6px}.review-mini-actions button{border:0;border-radius:9px;padding:7px 9px;background:#edf0f6;color:#49556a;cursor:pointer}.review-textarea{min-height:88px;resize:vertical}.review-dock{position:fixed;z-index:1220;right:0;bottom:0;width:min(760px,92vw);display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 24px;border-top:1px solid #dfe4ee;background:#ffffffed;backdrop-filter:blur(18px)}.review-dock span{color:#667085;font-size:12px}.review-dock div{display:flex;gap:8px}.review-dock button,.review-action{border:0;border-radius:11px;padding:11px 15px;font-weight:800;cursor:pointer}.review-primary{background:#315efb;color:#fff}.review-secondary{background:#edf1f8;color:#364153}.review-danger{background:#fff0f0;color:#b42318}.wechat-review-tabs{display:flex;gap:7px;margin:4px 0 16px;padding:5px;border-radius:13px;background:#eef1f7}.wechat-review-tabs button{flex:1;border:0;border-radius:9px;padding:10px 8px;background:transparent;color:#5c6678;font-weight:760;cursor:pointer}.wechat-review-tabs button.active{background:#fff;color:#24324b;box-shadow:0 4px 16px #1f293714}.wechat-review-panel{margin-bottom:16px;padding:16px;border:1px solid #dfe4ef;border-radius:16px;background:#f9faff}.wechat-review-panel h4{margin:0 0 8px}.wechat-review-panel p{margin:0 0 12px;color:#677286;font-size:13px;line-height:1.6}.review-status{min-height:24px;color:#667085;font-size:12px}.review-status.ok{color:#168455}.review-status.error{color:#b42318}.publisher-steps{display:grid;gap:8px;margin:12px 0}.publisher-steps div{padding:11px 12px;border-radius:11px;background:#fff;color:#445064;font-size:13px}.publisher-links{display:flex;flex-wrap:wrap;gap:8px}.publisher-links a{display:inline-flex;padding:10px 13px;border-radius:10px;background:#315efb;color:#fff;text-decoration:none;font-size:13px;font-weight:800}@media(max-width:780px){.review-grid{grid-template-columns:1fr}}
`;
    document.head.appendChild(style);
  }

  function injectStoryboardButton() {
    const actions = document.querySelector(".card-control-actions");
    if (!actions || document.getElementById("open-storyboard-review")) return;
    const button = node("button", "secondary-action review-launch", "审阅故事板");
    button.id = "open-storyboard-review";
    button.type = "button";
    button.addEventListener("click", openStoryboardReview);
    actions.prepend(button);
  }

  async function artifactFor(artifactType, scopeType, scopeId) {
    return callApi("/api/reviews/artifacts", {
      method: "POST",
      body: JSON.stringify({ artifact_type: artifactType, scope_type: scopeType, scope_id: scopeId }),
    });
  }

  async function openStoryboardReview() {
    if (!state?.draftId) {
      window.alert("请先选择一篇文案");
      return;
    }
    const artifact = await artifactFor("xhs_storyboard", "draft", state.draftId);
    reviewState.xhsArtifact = artifact;
    renderStoryboardDrawer(artifact);
  }

  function overlay(title, description) {
    document.getElementById("review-overlay")?.remove();
    const root = node("section", "review-overlay");
    root.id = "review-overlay";
    const drawer = node("article", "review-drawer");
    const head = node("header", "review-head");
    const copy = node("div");
    copy.append(node("h2", "", title), node("p", "", description));
    const close = node("button", "review-close", "×");
    close.type = "button";
    close.addEventListener("click", () => root.remove());
    head.append(copy, close);
    const body = node("div", "review-body");
    const dock = node("footer", "review-dock");
    drawer.append(head, body, dock);
    root.appendChild(drawer);
    root.addEventListener("click", (event) => { if (event.target === root) root.remove(); });
    document.body.appendChild(root);
    return { root, body, dock };
  }

  function renderStoryboardDrawer(artifact) {
    const payload = parse(artifact.payload_json, {});
    const { body, dock } = overlay("小红书故事板 Review", `v${artifact.version} · ${artifact.state} · 每一页都可以独立修改、排序和批准`);
    const direction = node("section", "review-section");
    direction.appendChild(node("h3", "", "视觉方向"));
    const grid = node("div", "review-grid");
    const styleField = node("label", "", "构图语言");
    const styleSelect = select([["technical_blueprint", "技术蓝图"], ["data_poster", "数据海报"], ["editorial_collage", "编辑拼贴"], ["paper_cut", "纸张切片"]], payload.art_direction?.style || "technical_blueprint");
    styleSelect.dataset.field = "style";
    styleField.appendChild(styleSelect);
    const paletteField = node("label", "", "配色");
    const paletteSelect = select([["electric_blue", "电光蓝"], ["signal_red", "信号红"], ["acid_green", "酸性绿"], ["violet", "深紫"], ["ink", "黑白墨色"]], payload.art_direction?.palette || "electric_blue");
    paletteSelect.dataset.field = "palette";
    paletteField.appendChild(paletteSelect);
    grid.append(styleField, paletteField);
    direction.appendChild(grid);
    body.appendChild(direction);

    const pagesSection = node("section", "review-section");
    pagesSection.appendChild(node("h3", "", "页面故事线"));
    const pagesBox = node("div");
    pagesBox.id = "review-pages";
    (payload.pages || []).forEach((page, index) => pagesBox.appendChild(pageEditor(page, index)));
    const add = node("button", "review-action review-secondary", "增加一页");
    add.type = "button";
    add.addEventListener("click", () => pagesBox.appendChild(pageEditor({ kind: "key_takeaways", kicker: "新页面", title: "", body: "", items: [] }, pagesBox.children.length)));
    pagesSection.append(pagesBox, add);
    body.appendChild(pagesSection);

    const status = node("span", "review-status", `当前状态：${artifact.state}`);
    const actions = node("div");
    const request = node("button", "review-danger", "退回修改");
    const save = node("button", "review-secondary", "保存新版本");
    const approve = node("button", "review-primary", "批准并生成");
    request.addEventListener("click", () => decideArtifact("changes_requested", "故事板需要继续修改", status));
    save.addEventListener("click", () => saveStoryboard(status));
    approve.addEventListener("click", () => approveAndRenderStoryboard(status));
    actions.append(request, save, approve);
    dock.append(status, actions);
  }

  function pageEditor(page, index) {
    const card = node("article", "review-page");
    card.dataset.pageId = page.id || `page-${Date.now()}-${index}`;
    const top = node("div", "review-page-top");
    const label = node("strong", "", `第 ${index + 1} 页`);
    const controls = node("div", "review-mini-actions");
    [["↑", -1], ["↓", 1]].forEach(([text, direction]) => {
      const button = node("button", "", text);
      button.type = "button";
      button.addEventListener("click", () => moveCard(card, direction));
      controls.appendChild(button);
    });
    const remove = node("button", "", "删除");
    remove.type = "button";
    remove.addEventListener("click", () => card.remove());
    controls.appendChild(remove);
    top.append(label, controls);
    const grid = node("div", "review-grid");
    const kindField = node("label", "", "页型");
    const kind = select(pageTypes, page.kind || "key_takeaways");
    kind.dataset.pageField = "kind";
    kindField.appendChild(kind);
    const kickerField = node("label", "", "栏目短标");
    const kicker = document.createElement("input");
    kicker.value = page.kicker || "";
    kicker.dataset.pageField = "kicker";
    kickerField.appendChild(kicker);
    grid.append(kindField, kickerField);
    const titleField = node("label", "review-field", "页面标题");
    const title = document.createElement("input");
    title.value = page.title || "";
    title.dataset.pageField = "title";
    titleField.appendChild(title);
    const bodyField = node("label", "review-field", "补充说明");
    const bodyInput = node("textarea", "review-textarea");
    bodyInput.value = page.body || "";
    bodyInput.dataset.pageField = "body";
    bodyField.appendChild(bodyInput);
    const itemsField = node("label", "review-field", "要点（每行一条，最多 4 条）");
    const items = node("textarea", "review-textarea");
    items.value = (page.items || []).join("\n");
    items.dataset.pageField = "items";
    itemsField.appendChild(items);
    const visualField = node("label", "review-field", "画面说明");
    const visual = node("textarea", "review-textarea");
    visual.value = page.visual_brief || "";
    visual.dataset.pageField = "visual_brief";
    visualField.appendChild(visual);
    card.append(top, grid, titleField, bodyField, itemsField, visualField);
    return card;
  }

  function moveCard(card, direction) {
    const sibling = direction < 0 ? card.previousElementSibling : card.nextElementSibling;
    if (!sibling) return;
    if (direction < 0) card.parentElement.insertBefore(card, sibling);
    else card.parentElement.insertBefore(sibling, card);
    [...card.parentElement.children].forEach((item, index) => {
      const label = item.querySelector(".review-page-top strong");
      if (label) label.textContent = `第 ${index + 1} 页`;
    });
  }

  function collectStoryboard() {
    const artDirection = {};
    document.querySelectorAll("[data-field]").forEach((field) => { artDirection[field.dataset.field] = field.value; });
    const pages = [...document.querySelectorAll("#review-pages .review-page")].map((card) => {
      const value = (name) => card.querySelector(`[data-page-field="${name}"]`)?.value || "";
      return {
        id: card.dataset.pageId,
        kind: value("kind"),
        kicker: value("kicker"),
        title: value("title"),
        body: value("body"),
        items: value("items").split("\n").map((item) => item.trim()).filter(Boolean).slice(0, 4),
        visual_brief: value("visual_brief"),
      };
    });
    return { art_direction: artDirection, pages };
  }

  async function saveStoryboard(status) {
    try {
      status.textContent = "正在保存故事板版本…";
      const artifact = await callApi(`/api/reviews/artifacts/${encodeURIComponent(reviewState.xhsArtifact.id)}`, {
        method: "PUT",
        body: JSON.stringify({ payload: collectStoryboard(), note: "人工编辑故事板" }),
      });
      reviewState.xhsArtifact = artifact;
      status.textContent = `已保存 v${artifact.version}`;
      status.className = "review-status ok";
    } catch (error) {
      status.textContent = error.message;
      status.className = "review-status error";
    }
  }

  async function decideArtifact(decision, note, status) {
    const artifact = reviewState.xhsArtifact;
    if (!artifact) return;
    try {
      const updated = await callApi(`/api/reviews/artifacts/${encodeURIComponent(artifact.id)}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision, note }),
      });
      reviewState.xhsArtifact = updated;
      status.textContent = decision === "approved" ? "故事板已批准" : "已标记需要修改";
      status.className = "review-status ok";
    } catch (error) {
      status.textContent = error.message;
      status.className = "review-status error";
    }
  }

  async function approveAndRenderStoryboard(status) {
    await saveStoryboard(status);
    if (!reviewState.xhsArtifact) return;
    try {
      const approved = await callApi(`/api/reviews/artifacts/${encodeURIComponent(reviewState.xhsArtifact.id)}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision: "approved", note: "批准用于发布卡片" }),
      });
      reviewState.xhsArtifact = approved;
      status.textContent = "正在按批准故事板渲染…";
      await callApi(`/api/reviews/artifacts/${encodeURIComponent(approved.id)}/render-storyboard`, {
        method: "POST",
        body: JSON.stringify({ template: document.getElementById("card-template")?.value || "tech_minimal", preview: false }),
      });
      await loadCards(state.draftId);
      status.textContent = "已生成审阅版卡片";
      status.className = "review-status ok";
    } catch (error) {
      status.textContent = error.message;
      status.className = "review-status error";
    }
  }

  function injectWechatReview() {
    const form = document.getElementById("wechat-editor");
    if (!form || document.getElementById("wechat-review-tabs")) return;
    const heading = form.querySelector(".panel-heading");
    const tabs = node("div", "wechat-review-tabs");
    tabs.id = "wechat-review-tabs";
    [["article", "正文"], ["modules", "模块 Review"], ["cover", "封面 Review"], ["publish", "发布助手"]].forEach(([view, label]) => {
      const button = node("button", view === "article" ? "active" : "", label);
      button.type = "button";
      button.dataset.reviewView = view;
      button.addEventListener("click", () => showWechatReviewView(view));
      tabs.appendChild(button);
    });
    const panel = node("section", "wechat-review-panel");
    panel.id = "wechat-review-panel";
    panel.hidden = true;
    heading.insertAdjacentElement("afterend", tabs);
    tabs.insertAdjacentElement("afterend", panel);
  }

  function showWechatReviewView(view) {
    document.querySelectorAll("#wechat-review-tabs button").forEach((button) => button.classList.toggle("active", button.dataset.reviewView === view));
    const panel = document.getElementById("wechat-review-panel");
    const articleFields = [...document.querySelectorAll("#wechat-editor > label, #wechat-editor > .platform-editor-actions")];
    const articleMode = view === "article";
    articleFields.forEach((element) => { element.hidden = !articleMode; });
    panel.hidden = articleMode;
    if (articleMode) return;
    if (!reviewState.wechatVariant) {
      panel.replaceChildren(node("p", "", "请先选择一个公众号版本。"));
      return;
    }
    if (view === "modules") loadWechatModules(panel);
    if (view === "cover") loadWechatCover(panel);
    if (view === "publish") renderPublisherPanel(panel);
  }

  async function loadWechatModules(panel) {
    panel.replaceChildren(node("p", "", "正在生成可审阅模块树…"));
    try {
      const artifact = await artifactFor("wechat_module_tree", "platform_variant", reviewState.wechatVariant.id);
      reviewState.moduleArtifact = artifact;
      renderWechatModules(panel, artifact);
    } catch (error) { panel.replaceChildren(node("p", "review-status error", error.message)); }
  }

  function renderWechatModules(panel, artifact) {
    const payload = parse(artifact.payload_json, {});
    panel.replaceChildren();
    panel.append(node("h4", "", `公众号模块树 · v${artifact.version}`), node("p", "", "在这里调整章节、正文、重点框、列表与图片。批准后会创建新的公众号文章版本，不覆盖当前版本。"));
    const box = node("div");
    box.id = "wechat-module-list";
    (payload.modules || []).forEach((module, index) => box.appendChild(moduleEditor(module, index)));
    const actions = node("div", "platform-editor-actions");
    const status = node("span", "review-status", `状态：${artifact.state}`);
    const controls = node("div");
    const add = node("button", "secondary-action", "增加模块");
    const save = node("button", "secondary-action", "保存 Review 版本");
    const approve = node("button", "primary-action", "批准并应用到文章");
    add.type = save.type = approve.type = "button";
    add.addEventListener("click", () => box.appendChild(moduleEditor({ type: "paragraph", text: "" }, box.children.length)));
    save.addEventListener("click", () => saveWechatModules(payload, status));
    approve.addEventListener("click", () => approveWechatModules(payload, status));
    controls.append(add, save, approve);
    actions.append(status, controls);
    panel.append(box, actions);
  }

  function moduleEditor(module, index) {
    const card = node("article", "review-module");
    card.dataset.moduleId = module.id || `module-${Date.now()}-${index}`;
    const top = node("div", "review-module-top");
    const kind = select(moduleTypes, module.type || "paragraph");
    kind.dataset.moduleField = "type";
    const controls = node("div", "review-mini-actions");
    [["↑", -1], ["↓", 1]].forEach(([text, direction]) => {
      const button = node("button", "", text);
      button.type = "button";
      button.addEventListener("click", () => moveCard(card, direction));
      controls.appendChild(button);
    });
    const remove = node("button", "", "删除");
    remove.type = "button";
    remove.addEventListener("click", () => card.remove());
    controls.appendChild(remove);
    top.append(kind, controls);
    const content = node("textarea", "review-textarea");
    content.dataset.moduleField = "content";
    content.value = module.type === "list" ? (module.items || []).join("\n") : module.type === "image" ? `${module.alt || ""}\n${module.url || ""}` : module.text || "";
    card.append(top, content);
    return card;
  }

  function collectModules() {
    return [...document.querySelectorAll("#wechat-module-list .review-module")].map((card) => {
      const type = card.querySelector("[data-module-field='type']").value;
      const content = card.querySelector("[data-module-field='content']").value;
      if (type === "list") return { id: card.dataset.moduleId, type, ordered: false, items: content.split("\n").map((item) => item.trim()).filter(Boolean) };
      if (type === "heading") return { id: card.dataset.moduleId, type, level: 2, text: content };
      if (type === "image") {
        const [alt = "", url = ""] = content.split("\n");
        return { id: card.dataset.moduleId, type, alt, url };
      }
      return { id: card.dataset.moduleId, type, text: content };
    });
  }

  async function saveWechatModules(basePayload, status) {
    try {
      const payload = { ...basePayload, modules: collectModules() };
      const revised = await callApi(`/api/reviews/artifacts/${encodeURIComponent(reviewState.moduleArtifact.id)}`, {
        method: "PUT", body: JSON.stringify({ payload, note: "人工调整公众号模块" }),
      });
      reviewState.moduleArtifact = revised;
      status.textContent = `已保存 Review v${revised.version}`;
      status.className = "review-status ok";
      return revised;
    } catch (error) { status.textContent = error.message; status.className = "review-status error"; return null; }
  }

  async function approveWechatModules(basePayload, status) {
    const revised = await saveWechatModules(basePayload, status);
    if (!revised) return;
    try {
      const approved = await callApi(`/api/reviews/artifacts/${encodeURIComponent(revised.id)}/decision`, {
        method: "POST", body: JSON.stringify({ decision: "approved", note: "批准应用到公众号文章" }),
      });
      const applied = await callApi(`/api/reviews/artifacts/${encodeURIComponent(approved.id)}/apply-wechat-modules`, { method: "POST" });
      status.textContent = "已创建新的公众号文章版本";
      status.className = "review-status ok";
      document.dispatchEvent(new CustomEvent("x2red:wechat-refresh-request", { detail: { variantId: applied.applied_to_id } }));
    } catch (error) { status.textContent = error.message; status.className = "review-status error"; }
  }

  async function loadWechatCover(panel) {
    panel.replaceChildren(node("p", "", "正在建立封面视觉 brief…"));
    try {
      const artifact = await artifactFor("wechat_cover_brief", "platform_variant", reviewState.wechatVariant.id);
      reviewState.coverArtifact = artifact;
      renderWechatCover(panel, artifact);
    } catch (error) { panel.replaceChildren(node("p", "review-status error", error.message)); }
  }

  function renderWechatCover(panel, artifact) {
    const payload = parse(artifact.payload_json, {});
    panel.replaceChildren();
    panel.append(node("h4", "", `公众号封面 brief · v${artifact.version}`), node("p", "", "封面是独立可审阅产物。选择构图后批准并重渲染，不影响正文版本。"));
    const grid = node("div", "review-grid");
    const fields = [
      ["cover_style", "构图", [["auto", "自动"], ["image_cinema", "影像电影感"], ["tech_blueprint", "技术蓝图"], ["data_poster", "数据海报"], ["editorial_split", "编辑分栏"]]],
      ["theme", "主题", [[payload.theme || "graphite", payload.theme || "graphite"]]],
    ];
    fields.forEach(([name, label, options]) => {
      const wrapper = node("label", "", label);
      const control = select(options, payload[name] || options[0][0]);
      control.dataset.coverField = name;
      wrapper.appendChild(control);
      grid.appendChild(wrapper);
    });
    panel.appendChild(grid);
    [["title", "主标题"], ["short_title", "分享短标题"], ["subtitle", "副标题"], ["series_label", "对外栏目名（可空）"], ["emphasis", "视觉锚点，如 54倍"]].forEach(([name, label]) => {
      const wrapper = node("label", "review-field", label);
      const input = document.createElement(name === "subtitle" ? "textarea" : "input");
      input.value = payload[name] || "";
      input.dataset.coverField = name;
      wrapper.appendChild(input);
      panel.appendChild(wrapper);
    });
    const actions = node("div", "platform-editor-actions");
    const status = node("span", "review-status", `状态：${artifact.state}`);
    const controls = node("div");
    const save = node("button", "secondary-action", "保存 brief");
    const render = node("button", "primary-action", "批准并重做封面");
    save.type = render.type = "button";
    save.addEventListener("click", () => saveWechatCover(status));
    render.addEventListener("click", () => approveWechatCover(status));
    controls.append(save, render);
    actions.append(status, controls);
    panel.appendChild(actions);
  }

  function collectCover() {
    const payload = {};
    document.querySelectorAll("[data-cover-field]").forEach((field) => { payload[field.dataset.coverField] = field.value; });
    return payload;
  }

  async function saveWechatCover(status) {
    try {
      const revised = await callApi(`/api/reviews/artifacts/${encodeURIComponent(reviewState.coverArtifact.id)}`, {
        method: "PUT", body: JSON.stringify({ payload: collectCover(), note: "人工调整公众号封面" }),
      });
      reviewState.coverArtifact = revised;
      status.textContent = `已保存封面 brief v${revised.version}`;
      status.className = "review-status ok";
      return revised;
    } catch (error) { status.textContent = error.message; status.className = "review-status error"; return null; }
  }

  async function approveWechatCover(status) {
    const revised = await saveWechatCover(status);
    if (!revised) return;
    try {
      const approved = await callApi(`/api/reviews/artifacts/${encodeURIComponent(revised.id)}/decision`, {
        method: "POST", body: JSON.stringify({ decision: "approved", note: "批准生成公众号封面" }),
      });
      await callApi(`/api/reviews/artifacts/${encodeURIComponent(approved.id)}/render-wechat-cover`, { method: "POST" });
      status.textContent = "新封面对已生成";
      status.className = "review-status ok";
      document.dispatchEvent(new CustomEvent("x2red:wechat-refresh-request", { detail: { variantId: reviewState.wechatVariant.id } }));
    } catch (error) { status.textContent = error.message; status.className = "review-status error"; }
  }

  function renderPublisherPanel(panel) {
    panel.replaceChildren();
    panel.append(node("h4", "", "公众号发布助手"), node("p", "", "富文本复制仍可能被公众号二次过滤。推荐使用浏览器发布助手，将标题、作者和内联 HTML 分别写入编辑器。"));
    const steps = node("div", "publisher-steps");
    ["下载并解压发布助手", "在 chrome://extensions 打开开发者模式并加载已解压扩展", "打开公众号图文编辑器，点击扩展并选择当前版本", "检查图片、封面和换行后保存草稿"].forEach((text, index) => steps.appendChild(node("div", "", `${index + 1}. ${text}`)));
    const links = node("div", "publisher-links");
    const download = node("a", "", "下载发布助手 ZIP");
    download.href = "/api/reviews/wechat-assistant/extension.zip";
    const open = node("a", "", "打开公众号编辑器");
    open.href = "https://mp.weixin.qq.com/";
    open.target = "_blank";
    open.rel = "noreferrer";
    links.append(download, open);
    panel.append(steps, links);
  }

  document.addEventListener("x2red:wechat-variant-selected", (event) => {
    reviewState.wechatVariant = event.detail?.variant || null;
    reviewState.moduleArtifact = null;
    reviewState.coverArtifact = null;
    const active = document.querySelector("#wechat-review-tabs button.active")?.dataset.reviewView;
    if (active && active !== "article") showWechatReviewView(active);
  });

  function boot() {
    injectStyles();
    injectStoryboardButton();
    injectWechatReview();
    const observer = new MutationObserver(() => {
      injectStoryboardButton();
      injectWechatReview();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
