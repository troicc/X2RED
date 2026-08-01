(() => {
  const apiCall = window.api || (async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let message = `请求失败：${response.status}`;
      try { message = (await response.json()).detail || message; } catch {}
      throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
  });

  const RECIPES = [
    ["comfort", "人生慰藉", "高压生活中的具体安慰，不写廉价鸡汤"],
    ["mature_life", "中老年生活", "平等、有经验感，不俯视、不讲养生神话"],
    ["seasonal", "节气时令", "物候、饮食和日常提醒，保留地区与个体差异"],
    ["photo_quote", "照片短句", "照片承担叙事，文字只留一句"],
    ["short_commentary", "一句短评", "抓住现实矛盾，短但不省略事实边界"],
  ];
  const STYLES = [
    ["auto", "自动匹配", "按内容配方选择"],
    ["minimal_zine", "极简杂志", "旧纸、留白、小型视觉锚点"],
    ["photo_editorial", "照片编辑", "大幅照片、电影颗粒、少字"],
    ["classical_ink", "古典水墨", "宣纸、墨色、朱砂印记"],
    ["dark_contemplative", "深色沉思", "炭黑、暖光、博物馆感"],
    ["seasonal_folk", "节气民艺", "木刻、剪纸、物候和饮食图形"],
    ["old_newspaper", "旧报刊", "新闻纸、半色调、评论标题"],
  ];

  const state = {
    ready: false,
    busy: false,
    mode: "article",
    sources: [],
    drafts: [],
    variants: [],
    currentVariant: null,
    candidateIndex: 0,
    corpus: [],
  };

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function parse(value, fallback = {}) {
    try { return JSON.parse(value || ""); } catch { return fallback; }
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  function injectStyles() {
    if (document.getElementById("light-content-lab-v12-style")) return;
    const style = document.createElement("style");
    style.id = "light-content-lab-v12-style";
    style.textContent = `
.wechat-mode-tabs{display:flex;gap:8px;margin:18px 0 0;padding:6px;width:max-content;border:1px solid #dfe3ee;border-radius:14px;background:#f3f5fb}.wechat-mode-tab{min-height:38px;padding:0 16px;border:0;border-radius:10px;background:transparent;color:#646d80;font-weight:800;cursor:pointer}.wechat-mode-tab.active{background:#20263a;color:#fff;box-shadow:0 7px 20px #20263a22}.light-lab{margin-top:18px}.light-lab[hidden]{display:none}.light-lab-shell{display:grid;grid-template-columns:minmax(280px,330px) minmax(440px,1fr) minmax(330px,430px);gap:16px;align-items:start}.light-lab-panel{min-width:0;border:1px solid #e0e4ee;border-radius:22px;background:#fff;box-shadow:0 18px 44px #1720330b;overflow:hidden}.light-lab-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px 18px 14px;border-bottom:1px solid #edf0f5}.light-lab-panel-head h3{margin:3px 0 0;font-size:18px}.light-lab-panel-body{padding:16px}.light-lab-brief .light-lab-panel-body,.light-lab-preview .light-lab-panel-body{max-height:calc(100vh - 265px);overflow:auto}.light-field{display:grid;gap:6px;margin-bottom:12px;color:#4e5769;font-size:12px;font-weight:760}.light-field input,.light-field select,.light-field textarea{width:100%;border:1px solid #dce1eb;border-radius:11px;background:#fbfcff;padding:10px 11px;color:#202534;font:inherit}.light-field textarea{resize:vertical}.light-choice-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}.light-choice{position:relative;display:grid;gap:4px;padding:11px;border:1px solid #e0e4ec;border-radius:12px;background:#fafbfe;text-align:left;cursor:pointer}.light-choice input{position:absolute;opacity:0;pointer-events:none}.light-choice strong{font-size:12px}.light-choice small{color:#7a8292;font-size:10px;line-height:1.35}.light-choice:has(input:checked){border-color:#5768f4;background:#eef0ff;box-shadow:0 0 0 2px #6977f321}.light-recipe-grid{grid-template-columns:1fr}.light-style-grid{grid-template-columns:1fr 1fr}.light-generate{width:100%;min-height:46px;border:0;border-radius:13px;background:linear-gradient(120deg,#405af6,#7547eb);color:#fff;font-weight:850;cursor:pointer}.light-generate:disabled{opacity:.5}.light-status{margin-top:10px;min-height:36px;padding:9px 10px;border-radius:10px;background:#f2f4f8;color:#626b7e;font-size:11px;line-height:1.55}.light-status.ok{background:#eaf8f0;color:#18744b}.light-status.error{background:#fff0f0;color:#b42318}.light-corpus{margin-top:16px;border-top:1px solid #eceff4;padding-top:14px}.light-corpus summary{cursor:pointer;color:#353d50;font-size:12px;font-weight:850}.light-corpus-count{display:inline-flex;margin-left:6px;padding:2px 7px;border-radius:999px;background:#eceffd;color:#4c5bd9;font-size:10px}.light-version-rail{display:flex;gap:7px;overflow:auto;padding:12px 16px;border-bottom:1px solid #edf0f5}.light-version-chip{flex:0 0 auto;padding:7px 10px;border:1px solid #dfe3eb;border-radius:999px;background:#fafbfe;color:#626b7e;font-size:10px;font-weight:750;cursor:pointer}.light-version-chip.active{border-color:#3f55eb;background:#eef0ff;color:#3347cb}.light-editor-empty{display:grid;place-items:center;min-height:560px;padding:40px;color:#7d8595;text-align:center}.light-editor-main{padding:18px}.light-editor-main[hidden]{display:none}.light-quality-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.light-score{display:flex;align-items:baseline;gap:5px}.light-score strong{font-size:30px}.light-score span{color:#848b99;font-size:11px}.light-agent-badge{padding:6px 9px;border-radius:999px;background:#f0ebff;color:#6346be;font-size:10px;font-weight:850}.light-candidate-tabs{display:flex;gap:7px;margin-bottom:14px}.light-candidate-tab{padding:8px 11px;border:1px solid #dfe3ed;border-radius:9px;background:#fff;color:#5d6575;font-size:11px;font-weight:800;cursor:pointer}.light-candidate-tab.active{border-color:#273dd5;background:#273dd5;color:#fff}.light-review-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:14px}.light-review-card{padding:10px 11px;border:1px solid #e4e7ee;border-radius:11px;background:#fafbfc}.light-review-card strong{display:block;margin-bottom:4px;font-size:11px}.light-review-card span{color:#737b89;font-size:10px;line-height:1.45}.light-editor-form{display:grid;gap:10px}.light-editor-form label{display:grid;gap:5px;color:#50596b;font-size:11px;font-weight:760}.light-editor-form input,.light-editor-form textarea{width:100%;border:1px solid #dce1eb;border-radius:10px;padding:10px 11px;font:inherit}.light-editor-form textarea{resize:vertical}.light-action-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:13px}.light-action{min-height:38px;padding:0 13px;border:1px solid #dce1eb;border-radius:10px;background:#fff;color:#394256;font-size:11px;font-weight:820;cursor:pointer}.light-action.primary{border-color:#3349de;background:#3349de;color:#fff}.light-action.approve{border-color:#177348;background:#177348;color:#fff}.light-feedback{margin-top:14px;padding-top:14px;border-top:1px solid #eceff4}.light-feedback textarea{width:100%;min-height:86px;border:1px solid #dce1eb;border-radius:11px;padding:10px;font:inherit;resize:vertical}.light-preview-summary{padding:14px 16px;border-bottom:1px solid #edf0f5}.light-preview-summary h4{margin:0;font-size:15px}.light-preview-summary p{margin:5px 0 0;color:#737b8a;font-size:11px;line-height:1.55}.light-gallery{display:grid;gap:13px}.light-poster{margin:0;padding:8px;border:1px solid #e1e4eb;border-radius:14px;background:#f8f9fc}.light-poster img{display:block;width:100%;aspect-ratio:3/5;object-fit:cover;border-radius:9px;background:#ddd}.light-poster figcaption{display:flex;justify-content:space-between;gap:8px;padding:8px 2px 2px;color:#626b79;font-size:10px}.light-preview-actions{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:13px}.light-preview-actions a,.light-preview-actions button{padding:7px 10px;border:1px solid #dce1eb;border-radius:9px;background:#fff;color:#475166;font-size:10px;font-weight:800;text-decoration:none;cursor:pointer}@media(max-width:1260px){.light-lab-shell{grid-template-columns:300px minmax(430px,1fr)}.light-lab-preview{grid-column:1/-1}.light-lab-preview .light-lab-panel-body{max-height:none}.light-gallery{grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}}@media(max-width:860px){.light-lab-shell{grid-template-columns:1fr}.light-lab-brief .light-lab-panel-body{max-height:none}.light-style-grid{grid-template-columns:1fr 1fr}.light-review-grid{grid-template-columns:1fr}}
`;
    document.head.appendChild(style);
  }

  function injectModeTabs() {
    const view = document.getElementById("wechat-view");
    const intro = view?.querySelector(".page-intro");
    if (!view || !intro || document.getElementById("wechat-mode-tabs")) return;
    const tabs = el("div", "wechat-mode-tabs");
    tabs.id = "wechat-mode-tabs";
    [["article", "长文编辑"], ["light", "轻内容图组"]].forEach(([value, label]) => {
      const button = el("button", "wechat-mode-tab", label);
      button.type = "button";
      button.dataset.mode = value;
      button.addEventListener("click", () => setMode(value));
      tabs.appendChild(button);
    });
    intro.appendChild(tabs);
  }

  function injectLab() {
    const view = document.getElementById("wechat-view");
    const longLayout = view?.querySelector(".platform-studio-layout");
    if (!view || !longLayout || document.getElementById("wechat-light-lab")) return;
    const lab = el("section", "light-lab");
    lab.id = "wechat-light-lab";
    lab.hidden = true;
    lab.innerHTML = `
      <div class="light-lab-shell">
        <aside class="light-lab-panel light-lab-brief">
          <div class="light-lab-panel-head"><div><span class="section-kicker">BRIEF + CORPUS</span><h3>轻内容任务</h3></div><button id="light-refresh" class="secondary-action" type="button">刷新</button></div>
          <div class="light-lab-panel-body">
            <label class="light-field">来源<select id="light-source"></select></label>
            <label class="light-field">基础终稿<select id="light-draft"><option value="">直接使用来源</option></select></label>
            <div class="light-field"><span>内容配方</span><div id="light-recipe-grid" class="light-choice-grid light-recipe-grid"></div></div>
            <label id="light-seasonal-field" class="light-field" hidden>节气或时令主题<input id="light-seasonal-topic" maxlength="120" placeholder="例如：处暑、入伏吃什么、秋分早晚温差" /></label>
            <div class="light-field"><span>视觉路线</span><div id="light-style-grid" class="light-choice-grid light-style-grid"></div></div>
            <div class="light-choice-grid">
              <label class="light-field">图片数量<select id="light-count"><option>3</option><option selected>4</option><option>5</option><option>6</option></select></label>
              <label class="light-field">质量模式<select id="light-quality"><option value="studio" selected>工作室 · 多路审稿</option><option value="fast">快速 · 控制调用</option></select></label>
            </div>
            <label class="light-field">目标读者<input id="light-audience" maxlength="500" placeholder="例如：工作压力大的城市读者；50 岁以上关注日常生活的人" /></label>
            <label class="light-field">语气<input id="light-tone" maxlength="300" value="自然、具体、克制" /></label>
            <label class="light-field">本轮要求<textarea id="light-initial-feedback" rows="3" maxlength="3000" placeholder="例如：不要泛泛安慰，要写出照顾家庭后忽略自己的具体处境"></textarea></label>
            <button id="light-generate" class="light-generate" type="button">多 Agent 生成 3 个候选</button>
            <div id="light-status" class="light-status">只有你批准的成品才会进入私有优质语料。</div>
            <details class="light-corpus">
              <summary>私有语料库 <span id="light-corpus-count" class="light-corpus-count">0</span></summary>
              <label class="light-field" style="margin-top:12px">授权样本标题<input id="light-corpus-title" maxlength="160" /></label>
              <label class="light-field">授权样本正文<textarea id="light-corpus-body" rows="5" maxlength="8000" placeholder="只添加你原创或有权使用的样本"></textarea></label>
              <label class="light-field">学习备注<input id="light-corpus-note" maxlength="3000" placeholder="例如：喜欢开头的生活现场，不要照抄句子" /></label>
              <button id="light-corpus-add" class="light-action" type="button">加入授权样本</button>
            </details>
          </div>
        </aside>

        <main class="light-lab-panel light-lab-editor">
          <div class="light-lab-panel-head"><div><span class="section-kicker">CANDIDATES + REVIEW</span><h3>候选与总编审阅</h3></div><span id="light-current-state" class="status-chip neutral">未生成</span></div>
          <div id="light-version-rail" class="light-version-rail"></div>
          <div id="light-editor-empty" class="light-editor-empty"><div><h3>先建立轻内容任务</h3><p>系统会生成三个不同角度，并由读者审稿、文化事实审校和视觉导演独立评分。</p></div></div>
          <div id="light-editor-main" class="light-editor-main" hidden>
            <div class="light-quality-row"><div class="light-score"><strong id="light-score">0.0</strong><span>/ 10 综合质量</span></div><span id="light-agent-badge" class="light-agent-badge">多 Agent</span></div>
            <div id="light-candidate-tabs" class="light-candidate-tabs"></div>
            <div id="light-review-grid" class="light-review-grid"></div>
            <form id="light-editor-form" class="light-editor-form">
              <label>标题<input id="light-edit-title" maxlength="160" /></label>
              <label>副标题<input id="light-edit-subtitle" maxlength="240" /></label>
              <label>摘要<textarea id="light-edit-summary" rows="3" maxlength="1000"></textarea></label>
              <label>短正文<textarea id="light-edit-body" rows="10" maxlength="50000"></textarea></label>
              <label>标签<input id="light-edit-tags" maxlength="1000" /></label>
            </form>
            <div class="light-action-row">
              <button id="light-use-candidate" class="light-action" type="button">采用当前候选</button>
              <button id="light-save-edit" class="light-action" type="button">保存人工修改</button>
              <button id="light-render" class="light-action primary" type="button">按当前稿生成图组</button>
              <button id="light-approve" class="light-action approve" type="button">批准并加入优质语料</button>
            </div>
            <div class="light-feedback">
              <label class="light-field">继续迭代意见<textarea id="light-feedback" maxlength="3000" placeholder="指出具体问题：哪句话假、哪个角度不对、照片应是什么气质、哪些内容必须删"></textarea></label>
              <button id="light-iterate" class="light-action primary" type="button">按反馈再迭代一轮</button>
            </div>
          </div>
        </main>

        <aside class="light-lab-panel light-lab-preview">
          <div class="light-lab-panel-head"><div><span class="section-kicker">VISUAL OUTPUT</span><h3>图组预览</h3></div></div>
          <div id="light-preview-summary" class="light-preview-summary"><h4>尚未生成图组</h4><p>不同视觉路线会调用不同构图算法，不再只换文字。</p></div>
          <div class="light-lab-panel-body">
            <div id="light-preview-actions" class="light-preview-actions"></div>
            <div id="light-gallery" class="light-gallery"></div>
          </div>
        </aside>
      </div>`;
    longLayout.insertAdjacentElement("beforebegin", lab);
    buildChoices();
    bindEvents();
  }

  function buildChoices() {
    const recipeGrid = document.getElementById("light-recipe-grid");
    if (recipeGrid && !recipeGrid.children.length) {
      RECIPES.forEach(([value, label, note], index) => {
        const choice = el("label", "light-choice");
        choice.innerHTML = `<input type="radio" name="light-recipe" value="${value}" ${index === 0 ? "checked" : ""}><strong>${label}</strong><small>${note}</small>`;
        choice.querySelector("input").addEventListener("change", updateConditionalFields);
        recipeGrid.appendChild(choice);
      });
    }
    const styleGrid = document.getElementById("light-style-grid");
    if (styleGrid && !styleGrid.children.length) {
      STYLES.forEach(([value, label, note], index) => {
        const choice = el("label", "light-choice");
        choice.innerHTML = `<input type="radio" name="light-style" value="${value}" ${index === 0 ? "checked" : ""}><strong>${label}</strong><small>${note}</small>`;
        styleGrid.appendChild(choice);
      });
    }
  }

  function bindEvents() {
    document.getElementById("light-source")?.addEventListener("change", async () => {
      await loadDrafts();
      renderVersions();
    });
    document.getElementById("light-refresh")?.addEventListener("click", loadLab);
    document.getElementById("light-generate")?.addEventListener("click", generate);
    document.getElementById("light-use-candidate")?.addEventListener("click", useCandidate);
    document.getElementById("light-save-edit")?.addEventListener("click", saveEdit);
    document.getElementById("light-render")?.addEventListener("click", renderCurrent);
    document.getElementById("light-approve")?.addEventListener("click", approveCurrent);
    document.getElementById("light-iterate")?.addEventListener("click", iterateCurrent);
    document.getElementById("light-corpus-add")?.addEventListener("click", addCorpus);
  }

  function updateConditionalFields() {
    const recipe = selected("light-recipe", "comfort");
    const field = document.getElementById("light-seasonal-field");
    if (field) field.hidden = recipe !== "seasonal";
  }

  function selected(name, fallback = "") {
    return document.querySelector(`input[name='${name}']:checked`)?.value || fallback;
  }

  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll(".wechat-mode-tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.mode === mode);
    });
    const view = document.getElementById("wechat-view");
    const longLayout = view?.querySelector(".platform-studio-layout");
    const lab = document.getElementById("wechat-light-lab");
    if (longLayout) longLayout.hidden = mode === "light";
    if (lab) lab.hidden = mode !== "light";
    if (mode === "light") loadLab().catch((error) => status(error.message, "error"));
  }

  function status(text, kind = "") {
    const target = document.getElementById("light-status");
    if (!target) return;
    target.textContent = text;
    target.className = `light-status${kind ? ` ${kind}` : ""}`;
  }

  function setBusy(value, message = "") {
    state.busy = value;
    ["light-generate", "light-use-candidate", "light-save-edit", "light-render", "light-approve", "light-iterate", "light-corpus-add"].forEach((id) => {
      const button = document.getElementById(id);
      if (button) button.disabled = value;
    });
    if (message) status(message);
  }

  async function loadLab(preferredVariantId = "") {
    if (state.busy) return;
    const previousSource = document.getElementById("light-source")?.value || "";
    const [sources, variants, corpus] = await Promise.all([
      apiCall("/api/sources?workspace_state=active"),
      apiCall("/api/platforms/variants?platform=wechat&limit=200"),
      apiCall(`/api/platforms/wechat/light/corpus?recipe=${encodeURIComponent(selected("light-recipe", "comfort"))}&limit=100`),
    ]);
    state.sources = sources;
    state.variants = variants.filter((item) => item.format === "light_series");
    state.corpus = corpus;
    fillSources(previousSource);
    await loadDrafts();
    document.getElementById("light-corpus-count").textContent = String(corpus.length);
    renderVersions();
    const targetId = preferredVariantId || state.currentVariant?.id;
    const target = state.variants.find((item) => item.id === targetId)
      || state.variants.find((item) => item.source_id === document.getElementById("light-source")?.value);
    if (target) selectVariant(target.id);
  }

  function fillSources(previous = "") {
    const select = document.getElementById("light-source");
    if (!select) return;
    select.replaceChildren();
    state.sources.forEach((source) => {
      const option = new Option(
        `${source.author_handle ? `@${source.author_handle}` : source.author_name || "来源"} · ${(source.text_original || "").replace(/\s+/g, " ").slice(0, 52)}`,
        source.id,
      );
      select.appendChild(option);
    });
    const urlSource = new URLSearchParams(location.search).get("source") || "";
    const preferred = previous || urlSource;
    if (preferred && state.sources.some((item) => item.id === preferred)) select.value = preferred;
  }

  async function loadDrafts() {
    const sourceId = document.getElementById("light-source")?.value || "";
    const select = document.getElementById("light-draft");
    if (!select) return;
    const previous = select.value;
    select.replaceChildren(new Option("直接使用来源", ""));
    state.drafts = sourceId ? await apiCall(`/api/sources/${encodeURIComponent(sourceId)}/drafts`) : [];
    state.drafts.forEach((draft) => select.appendChild(new Option(`v${draft.version} · ${draft.title || "未命名终稿"}`, draft.id)));
    if (previous && state.drafts.some((item) => item.id === previous)) select.value = previous;
    else if (state.drafts.length) select.value = state.drafts[0].id;
  }

  function renderVersions() {
    const rail = document.getElementById("light-version-rail");
    if (!rail) return;
    rail.replaceChildren();
    const sourceId = document.getElementById("light-source")?.value || "";
    const values = state.variants.filter((item) => !sourceId || item.source_id === sourceId);
    values.forEach((variant) => {
      const meta = parse(variant.metadata_json, {});
      const button = el("button", `light-version-chip${state.currentVariant?.id === variant.id ? " active" : ""}`, `v${variant.version} · ${meta.recipe_label || "轻内容"} · ${meta.visual_style_label || meta.visual_style || ""}`);
      button.type = "button";
      button.addEventListener("click", () => selectVariant(variant.id));
      rail.appendChild(button);
    });
    if (!values.length) rail.appendChild(el("span", "light-version-chip", "当前来源暂无轻内容版本"));
  }

  function selectVariant(id) {
    const variant = state.variants.find((item) => item.id === id);
    if (!variant) return;
    state.currentVariant = variant;
    state.candidateIndex = Number(parse(variant.metadata_json, {}).selected_candidate_index || 0);
    renderVersions();
    renderEditor();
    renderGallery();
  }

  function currentMeta() {
    return parse(state.currentVariant?.metadata_json, {});
  }

  function currentCandidate() {
    const meta = currentMeta();
    const candidates = Array.isArray(meta.candidates) ? meta.candidates : [];
    return candidates[state.candidateIndex] || {
      title: state.currentVariant?.title || "",
      subtitle: state.currentVariant?.subtitle || "",
      summary: state.currentVariant?.summary || "",
      body_markdown: state.currentVariant?.body_markdown || "",
      tags: state.currentVariant?.tags || "",
    };
  }

  function renderEditor() {
    const variant = state.currentVariant;
    const empty = document.getElementById("light-editor-empty");
    const main = document.getElementById("light-editor-main");
    if (!variant) {
      empty.hidden = false;
      main.hidden = true;
      return;
    }
    empty.hidden = true;
    main.hidden = false;
    const meta = currentMeta();
    document.getElementById("light-current-state").textContent = `v${variant.version} · 第 ${meta.iteration_round || 1} 轮 · ${variant.status}`;
    document.getElementById("light-score").textContent = Number(meta.quality_score || 0).toFixed(1);
    document.getElementById("light-agent-badge").textContent = meta.generator?.includes("fallback") ? "结构化回退" : "6 角色 Agent";
    const tabs = document.getElementById("light-candidate-tabs");
    tabs.replaceChildren();
    const candidates = Array.isArray(meta.candidates) ? meta.candidates : [];
    candidates.forEach((candidate, index) => {
      const button = el("button", `light-candidate-tab${index === state.candidateIndex ? " active" : ""}`, `候选 ${index + 1} · ${candidate.angle || "不同角度"}`);
      button.type = "button";
      button.addEventListener("click", () => {
        state.candidateIndex = index;
        renderEditor();
      });
      tabs.appendChild(button);
    });
    if (!candidates.length) tabs.appendChild(el("span", "light-agent-badge", "人工版本"));
    renderReview(meta);
    const candidate = currentCandidate();
    document.getElementById("light-edit-title").value = candidate.title || variant.title || "";
    document.getElementById("light-edit-subtitle").value = candidate.subtitle || variant.subtitle || "";
    document.getElementById("light-edit-summary").value = candidate.summary || variant.summary || "";
    document.getElementById("light-edit-body").value = candidate.body_markdown || variant.body_markdown || "";
    document.getElementById("light-edit-tags").value = Array.isArray(candidate.tags) ? candidate.tags.join(",") : candidate.tags || variant.tags || "";
  }

  function renderReview(meta) {
    const grid = document.getElementById("light-review-grid");
    grid.replaceChildren();
    const audience = reviewAt(meta.reviews?.audience, state.candidateIndex);
    const culture = reviewAt(meta.reviews?.culture, state.candidateIndex);
    const cards = [
      ["目标读者审稿", audience, "是否真实、尊重、值得分享"],
      ["文化事实审校", culture, "是否忠于来源、无夸大和刻板印象"],
      ["总编选择", { average: meta.quality_score, strengths: [meta.chief_editor_note], must_fix: [meta.revision_summary] }, "为什么选这版、修改了什么"],
      ["语料使用", { strengths: [`参考 ${meta.corpus_item_ids?.length || 0} 条已批准语料`], must_fix: [meta.human_approved ? "已进入优质语料" : "尚未批准，不会回流"] }, "只学习结构与节奏，不照抄句子"],
    ];
    cards.forEach(([title, review, fallback]) => {
      const card = el("article", "light-review-card");
      const strengths = Array.isArray(review?.strengths) ? review.strengths.filter(Boolean).slice(0, 2).join("；") : "";
      const fixes = Array.isArray(review?.must_fix) ? review.must_fix.filter(Boolean).slice(0, 2).join("；") : "";
      card.innerHTML = `<strong>${escapeHtml(title)}${Number.isFinite(Number(review?.average)) ? ` · ${Number(review.average).toFixed(1)}` : ""}</strong><span>${escapeHtml(strengths || fixes || fallback)}</span>`;
      grid.appendChild(card);
    });
  }

  function reviewAt(payload, index) {
    const values = Array.isArray(payload?.candidate_reviews) ? payload.candidate_reviews : [];
    return values.find((item) => Number(item.candidate_index) === index) || payload || {};
  }

  function renderGallery() {
    const variant = state.currentVariant;
    const gallery = document.getElementById("light-gallery");
    const actions = document.getElementById("light-preview-actions");
    const summary = document.getElementById("light-preview-summary");
    gallery.replaceChildren();
    actions.replaceChildren();
    if (!variant) return;
    const meta = currentMeta();
    const files = parse(variant.output_paths_json, {});
    summary.innerHTML = `<h4>${escapeHtml(variant.title)}</h4><p>${escapeHtml(meta.recipe_label || "轻内容")} · ${escapeHtml(meta.visual_style_label || meta.visual_style || "")} · 第 ${meta.iteration_round || 1} 轮 · 质量 ${Number(meta.quality_score || 0).toFixed(1)}</p>`;
    const posterKeys = Object.keys(files).filter((key) => /^poster_\d+$/.test(key)).sort();
    const specs = Array.isArray(meta.poster_specs) ? meta.poster_specs : [];
    if (files.package) actions.appendChild(downloadLink(variant.id, "package", "下载发布包"));
    if (files.preview) actions.appendChild(downloadLink(variant.id, "preview", "打开整组预览"));
    if (!posterKeys.length) {
      gallery.appendChild(el("div", "light-editor-empty", "当前稿还没有渲染图片。先检查文案，再点击“按当前稿生成图组”。"));
      return;
    }
    posterKeys.forEach((key, index) => {
      const spec = specs[index] || {};
      const figure = el("figure", "light-poster");
      const image = document.createElement("img");
      image.src = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/${key}?v=${Date.now()}`;
      image.alt = spec.phrase || `海报 ${index + 1}`;
      const caption = document.createElement("figcaption");
      caption.innerHTML = `<span>${escapeHtml(spec.phrase || `第 ${index + 1} 张`)}</span><span>${escapeHtml(spec.visual_style || meta.visual_style || "")}</span>`;
      figure.append(image, caption);
      gallery.appendChild(figure);
    });
  }

  function downloadLink(variantId, key, label) {
    const link = el("a", "", label);
    link.href = `/api/platforms/variants/${encodeURIComponent(variantId)}/files/${encodeURIComponent(key)}`;
    link.target = "_blank";
    link.rel = "noreferrer";
    return link;
  }

  function briefPayload() {
    return {
      source_id: document.getElementById("light-source")?.value || "",
      draft_id: document.getElementById("light-draft")?.value || null,
      recipe: selected("light-recipe", "comfort"),
      image_count: Number(document.getElementById("light-count")?.value || 4),
      seasonal_topic: document.getElementById("light-seasonal-topic")?.value || "",
      audience: document.getElementById("light-audience")?.value || "",
      tone: document.getElementById("light-tone")?.value || "自然、具体、克制",
      visual_style: selected("light-style", "auto"),
      quality_mode: document.getElementById("light-quality")?.value || "studio",
      feedback: document.getElementById("light-initial-feedback")?.value || "",
      theme: "zen",
      author: "",
    };
  }

  async function generate() {
    if (state.busy) return;
    const payload = briefPayload();
    if (!payload.source_id) return status("请先选择来源。", "error");
    setBusy(true, "选题策划、主笔、两路审稿、视觉导演和总编正在协作…");
    try {
      const variant = await apiCall("/api/platforms/wechat/light/variants", { method: "POST", body: JSON.stringify(payload) });
      status("已生成三个不同角度。请先看审稿意见和文案，再决定采用或继续迭代。", "ok");
      await loadLab(variant.id);
    } catch (error) {
      status(error.message || String(error), "error");
    } finally {
      setBusy(false);
    }
  }

  function editorPayload() {
    return {
      title: document.getElementById("light-edit-title")?.value || "",
      subtitle: document.getElementById("light-edit-subtitle")?.value || "",
      summary: document.getElementById("light-edit-summary")?.value || "",
      body_markdown: document.getElementById("light-edit-body")?.value || "",
      tags: document.getElementById("light-edit-tags")?.value || "",
      theme: state.currentVariant?.theme || "zen",
    };
  }

  async function useCandidate() {
    if (!state.currentVariant || state.busy) return;
    setBusy(true, "正在把当前候选保存为新的不可变版本…");
    try {
      const variant = await apiCall(`/api/platforms/wechat/light/variants/${encodeURIComponent(state.currentVariant.id)}/select-candidate`, {
        method: "POST",
        body: JSON.stringify({ candidate_index: state.candidateIndex }),
      });
      status(`候选 ${state.candidateIndex + 1} 已保存为 v${variant.version}。`, "ok");
      await loadLab(variant.id);
    } catch (error) {
      status(error.message || String(error), "error");
    } finally { setBusy(false); }
  }

  async function saveEdit() {
    if (!state.currentVariant || state.busy) return;
    setBusy(true, "正在保存人工修改版本…");
    try {
      const variant = await apiCall(`/api/platforms/variants/${encodeURIComponent(state.currentVariant.id)}`, {
        method: "PUT",
        body: JSON.stringify(editorPayload()),
      });
      status(`人工修改已保存为 v${variant.version}。`, "ok");
      await loadLab(variant.id);
    } catch (error) {
      status(error.message || String(error), "error");
    } finally { setBusy(false); }
  }

  async function renderCurrent() {
    if (!state.currentVariant || state.busy) return;
    setBusy(true, "正在使用当前视觉路线生成完全不同的构图…");
    try {
      const result = await apiCall(`/api/platforms/variants/${encodeURIComponent(state.currentVariant.id)}/render`, {
        method: "POST",
        body: JSON.stringify({ package: true }),
      });
      status(`已生成 ${Object.keys(result.files || {}).filter((key) => key.startsWith("poster_")).length} 张图。`, "ok");
      await loadLab(result.variant.id);
    } catch (error) {
      status(error.message || String(error), "error");
    } finally { setBusy(false); }
  }

  async function iterateCurrent() {
    if (!state.currentVariant || state.busy) return;
    const feedback = document.getElementById("light-feedback")?.value.trim() || "";
    if (!feedback) return status("请写清楚哪句话不对、哪个角度不合适或画面应该怎样。", "error");
    setBusy(true, "正在带着你的反馈重新策划、写作和独立审稿…");
    try {
      const variant = await apiCall(`/api/platforms/wechat/light/variants/${encodeURIComponent(state.currentVariant.id)}/iterate`, {
        method: "POST",
        body: JSON.stringify({ feedback, quality_mode: document.getElementById("light-quality")?.value || "studio" }),
      });
      document.getElementById("light-feedback").value = "";
      status(`第 ${parse(variant.metadata_json, {}).iteration_round || 2} 轮已完成，请比较候选和评分。`, "ok");
      await loadLab(variant.id);
    } catch (error) {
      status(error.message || String(error), "error");
    } finally { setBusy(false); }
  }

  async function approveCurrent() {
    if (!state.currentVariant || state.busy) return;
    const note = document.getElementById("light-feedback")?.value.trim() || "人工确认可作为未来同配方的正向样本";
    setBusy(true, "正在冻结当前成品并加入私有优质语料…");
    try {
      await apiCall(`/api/platforms/wechat/light/variants/${encodeURIComponent(state.currentVariant.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
      status("已批准。以后同配方只学习这版的结构、节奏和判断方式，不照抄句子。", "ok");
      await loadLab(state.currentVariant.id);
    } catch (error) {
      status(error.message || String(error), "error");
    } finally { setBusy(false); }
  }

  async function addCorpus() {
    if (state.busy) return;
    const title = document.getElementById("light-corpus-title")?.value.trim() || "";
    const body = document.getElementById("light-corpus-body")?.value.trim() || "";
    if (!title && !body) return status("请粘贴你原创或有权使用的样本。", "error");
    setBusy(true, "正在加入授权样本…");
    try {
      await apiCall("/api/platforms/wechat/light/corpus", {
        method: "POST",
        body: JSON.stringify({
          recipe: selected("light-recipe", "comfort"),
          title,
          body_markdown: body,
          visual_style: selected("light-style", "auto"),
          note: document.getElementById("light-corpus-note")?.value || "",
        }),
      });
      ["light-corpus-title", "light-corpus-body", "light-corpus-note"].forEach((id) => { document.getElementById(id).value = ""; });
      status("授权样本已加入。后续只提炼其抽象风格，不复制原句。", "ok");
      await loadLab(state.currentVariant?.id || "");
    } catch (error) {
      status(error.message || String(error), "error");
    } finally { setBusy(false); }
  }

  function boot() {
    injectStyles();
    const observer = new MutationObserver(() => {
      injectModeTabs();
      injectLab();
      if (document.getElementById("wechat-mode-tabs") && !state.ready) {
        state.ready = true;
        setMode("article");
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    injectModeTabs();
    injectLab();
    if (document.getElementById("wechat-mode-tabs")) {
      state.ready = true;
      setMode("article");
    }
  }

  document.addEventListener("x2red:open-wechat-light", (event) => {
    setMode("light");
    const sourceId = event.detail?.sourceId;
    if (sourceId) {
      setTimeout(() => {
        const select = document.getElementById("light-source");
        if (select && [...select.options].some((option) => option.value === sourceId)) {
          select.value = sourceId;
          void loadDrafts();
        }
      }, 400);
    }
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
