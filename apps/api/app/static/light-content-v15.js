(() => {
  if (window.__x2redLightContentV15) return;

  const RECIPES = [
    ["comfort", "人生慰藉", "从具体处境出发，不写廉价鸡汤"],
    ["mature_life", "中老年生活", "平等、有经验感，不俯视"],
    ["seasonal", "节气时令", "物候、饮食与日常提醒"],
    ["photo_quote", "照片短句", "一张图承担叙事，文字保持克制"],
    ["short_commentary", "一句短评", "短，但不省略事实边界"],
  ];

  const STYLES = [
    ["auto", "自动匹配", "按内容和配方选择视觉路线"],
    ["minimal_zine", "Minimal Zine", "无字视觉锚点 + 本地中文排版"],
    ["photo_editorial", "照片编辑", "大幅照片、电影颗粒、少字"],
    ["classical_ink", "古典水墨", "宣纸、墨色、朱砂印记"],
    ["dark_contemplative", "深色沉思", "炭黑、暖光、博物馆感"],
    ["seasonal_folk", "节气民艺", "木刻、剪纸、物候和饮食图形"],
    ["old_newspaper", "旧报刊", "新闻纸、半色调、评论标题"],
  ];

  const SOURCE_GROUPS = [
    ["pool", "语料池批次"],
    ["x", "X / 信号台"],
    ["xhs", "小红书"],
    ["dy", "抖音"],
    ["ks", "快手"],
    ["bili", "B站"],
    ["wb", "微博"],
    ["tieba", "贴吧"],
    ["zhihu", "知乎"],
    ["web", "网页与文档"],
  ];

  const FIELDS = [
    "phrase",
    "note",
    "visual_metaphor",
    "layout",
    "anchor",
    "accent",
    "texture",
    "mood",
    "focus_x",
    "focus_y",
    "zoom",
  ];

  const LAYOUT_OPTIONS = [
    ["center-fragment", "中央碎片 · 下方留白"],
    ["lower-left-float", "左下浮动 · 右侧文字区"],
    ["upper-right-block", "右上块面 · 左下文字区"],
    ["dual-panel", "双面板 · 两个视觉区域"],
    ["irregular-cutout", "不规则裁切 · 纸张留白"],
    ["type-led", "文字主导 · 画面退后"],
    ["dot-orbit", "点阵环绕 · 中央视觉"],
    ["single-specimen", "单件标本 · 右下标签区"],
  ];

  const ANCHOR_OPTIONS = [
    ["tiny-faded-photo", "小幅褪色照片"],
    ["torn-paper-clipping", "撕纸剪贴"],
    ["flat-silhouette", "平面剪影"],
    ["solid-color-block", "纯色块"],
    ["old-printed-illustration", "旧印刷插图"],
    ["object-specimen", "物件标本"],
    ["translucent-geometric-overlay", "半透明几何叠层"],
    ["abstract-texture-window", "抽象质感窗口"],
  ];

  const TEXTURE_OPTIONS = [
    ["xerox-softness", "复印机柔化"],
    ["risograph-grain", "孔版印刷颗粒"],
    ["letterpress-ink-bleed", "活版印刷洇墨"],
    ["halftone-degradation", "半色调磨损"],
    ["film-grain-photo", "胶片颗粒"],
    ["scan-noise-paper-fibers", "扫描噪点与纸纤维"],
    ["aged-paper-mottling", "旧纸斑驳"],
    ["soft-motion-blur", "轻微动态模糊"],
  ];

  const ACCENT_OPTIONS = [
    ["blue", "蓝色"],
    ["cobalt", "钴蓝"],
    ["ultramarine", "群青"],
    ["cyan", "青蓝"],
    ["violet", "紫罗兰"],
    ["magenta", "洋红"],
    ["magenta-pink", "洋红粉"],
    ["yellow", "黄色"],
    ["lemon-yellow", "柠檬黄"],
    ["green", "绿色"],
    ["pear-green", "梨绿"],
    ["orange", "橙色"],
    ["red", "红色"],
    ["tomato-red", "番茄红"],
    ["vermilion", "朱砂红"],
  ];

  const LAYOUTS = new Set(LAYOUT_OPTIONS.map(([value]) => value));
  const ANCHORS = new Set(ANCHOR_OPTIONS.map(([value]) => value));
  const TEXTURES = new Set(TEXTURE_OPTIONS.map(([value]) => value));
  const NAMED_ACCENTS = new Set(ACCENT_OPTIONS.map(([value]) => value));
  const ACCENT_COLOR_NAMES = new Map([
    ["#1646d8", "cobalt"],
    ["#263fca", "ultramarine"],
    ["#00a7c6", "cyan"],
    ["#6f3cc3", "violet"],
    ["#cb247d", "magenta-pink"],
    ["#d5aa00", "lemon-yellow"],
    ["#4d9b4a", "pear-green"],
    ["#d46f1b", "orange"],
    ["#c93a2b", "tomato-red"],
    ["#c91f2c", "vermilion"],
  ]);

  const controller = {
    state: {
      ready: false,
      mode: "article",
      stage: readStage(),
      busy: false,
      loading: false,
      loadToken: 0,
      sources: [],
      drafts: [],
      variants: [],
      corpus: [],
      currentVariant: null,
      candidateIndex: 0,
      editor: emptyEditor(),
      storyboard: [],
      storyboardDirty: false,
      selectedPage: 1,
      pageEvidence: new Map(),
      status: {
        text: "先设定任务，再逐步完成文案、分镜和交付。",
        type: "",
      },
      brief: {
        sourceId: "",
        draftId: "",
        recipe: "comfort",
        imageCount: 4,
        seasonalTopic: "",
        audience: "",
        tone: "自然、具体、克制",
        visualStyle: "auto",
        qualityMode: "studio",
        feedback: "",
      },
    },
  };

  window.__x2redLightContentV15 = controller;
  const { state } = controller;

  const call = window.api || (async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    return response.json();
  });

  const node = (id) => document.getElementById(id);

  function emptyEditor() {
    return {
      title: "",
      subtitle: "",
      summary: "",
      body_markdown: "",
      tags: "",
    };
  }

  function readStage() {
    try {
      const value = Number(window.localStorage.getItem("x2red.light-content.v15.stage"));
      return value >= 1 && value <= 4 ? value : 1;
    } catch {
      return 1;
    }
  }

  function saveStage() {
    try {
      window.localStorage.setItem("x2red.light-content.v15.stage", String(state.stage));
    } catch {
      // Storage can be disabled in a private browser context.
    }
  }

  function create(tag, className = "", text = "") {
    const value = document.createElement(tag);
    if (className) value.className = className;
    if (text) value.textContent = text;
    return value;
  }

  function button(label, className = "", handler = null) {
    const value = create("button", className, label);
    value.type = "button";
    if (handler) value.addEventListener("click", handler);
    return value;
  }

  function labelFor(text, control) {
    const value = create("label", "light-field", text);
    value.appendChild(control);
    return value;
  }

  function input(value = "", options = {}) {
    const control = document.createElement(options.multiline ? "textarea" : "input");
    if (!options.multiline) control.type = options.type || "text";
    if (options.multiline) control.rows = options.rows || 3;
    if (options.id) control.id = options.id;
    if (options.maxLength) control.maxLength = options.maxLength;
    if (options.placeholder) control.placeholder = options.placeholder;
    if (options.className) control.className = options.className;
    if (options.min !== undefined) control.min = String(options.min);
    if (options.max !== undefined) control.max = String(options.max);
    if (options.step !== undefined) control.step = String(options.step);
    if (options.inputMode) control.inputMode = options.inputMode;
    control.value = value ?? "";
    return control;
  }

  function select(options, value = "", id = "") {
    const control = document.createElement("select");
    if (id) control.id = id;
    options.forEach(([optionValue, optionLabel]) => {
      control.appendChild(new Option(optionLabel, optionValue));
    });
    control.value = value;
    return control;
  }

  function parse(value, fallback = {}) {
    try {
      const result = JSON.parse(value || "");
      return result && typeof result === "object" ? result : fallback;
    } catch {
      return fallback;
    }
  }

  function metadata(variant = state.currentVariant) {
    return parse(variant?.metadata_json, {});
  }

  function outputPaths(variant = state.currentVariant) {
    return parse(variant?.output_paths_json, {});
  }

  function sourceGroup(source) {
    if (source?.provider === "corpus_pool" || source?.content_kind === "corpus_batch") return "pool";
    if (source?.platform === "x" || source?.provider === "fxtwitter" || source?.provider === "signal-studio") return "x";
    if (["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"].includes(source?.platform)) return source.platform;
    return "web";
  }

  function sourceLabel(source) {
    const author = source.author_handle ? `@${source.author_handle}` : source.author_name || "来源";
    const copy = String(source.text_original || "").replace(/\s+/g, " ").slice(0, 52);
    return `${author} · ${copy || source.content_kind || "无正文"}`;
  }

  function isMinimalZine(variant = state.currentVariant) {
    const visualStyle = String(metadata(variant).visual_style || state.brief.visualStyle || "auto");
    return ![
      "photo_editorial",
      "classical_ink",
      "dark_contemplative",
      "seasonal_folk",
      "old_newspaper",
    ].includes(visualStyle);
  }

  function currentCandidate() {
    const candidates = metadata().candidates;
    if (Array.isArray(candidates) && candidates.length) {
      return candidates[state.candidateIndex] || candidates[0];
    }
    return {
      title: state.currentVariant?.title || "",
      subtitle: state.currentVariant?.subtitle || "",
      summary: state.currentVariant?.summary || "",
      body_markdown: state.currentVariant?.body_markdown || "",
      tags: state.currentVariant?.tags || "",
    };
  }

  function normalizeTags(value) {
    return Array.isArray(value) ? value.join(",") : String(value || "");
  }

  function allowed(value, choices, fallback) {
    const normalized = String(value || "").trim();
    return choices.has(normalized) ? normalized : fallback;
  }

  function clamp(value, minimum, maximum, fallback) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return fallback;
    return Math.min(maximum, Math.max(minimum, numeric));
  }

  function normalizeAccent(value) {
    const cleaned = String(value || "").trim().toLowerCase().replaceAll("_", "-").replaceAll(" ", "-");
    return NAMED_ACCENTS.has(cleaned) || /^#[0-9a-f]{6}$/.test(cleaned) ? cleaned : "#1646d8";
  }

  function loadEditorFromCandidate() {
    const candidate = currentCandidate() || {};
    state.editor = {
      title: candidate.title || state.currentVariant?.title || "",
      subtitle: candidate.subtitle || state.currentVariant?.subtitle || "",
      summary: candidate.summary || state.currentVariant?.summary || "",
      body_markdown: candidate.body_markdown || state.currentVariant?.body_markdown || "",
      tags: normalizeTags(candidate.tags || state.currentVariant?.tags),
    };
  }

  function fallbackPhrase(index) {
    const lines = String(state.currentVariant?.body_markdown || "")
      .split(/(?<=[。！？!?])|\n+/)
      .map((value) => value.replace(/\s+/g, " ").trim())
      .filter(Boolean);
    return lines[index] || (index === 0 ? state.currentVariant?.title || "把这一页说清楚" : "把这一页说清楚");
  }

  function normalizeStoryboard(variant = state.currentVariant) {
    const meta = metadata(variant);
    const raw = Array.isArray(meta.poster_specs) ? meta.poster_specs : [];
    const count = Math.max(3, Math.min(6, raw.length || Number(meta.image_count || state.brief.imageCount || 4)));
    return Array.from({ length: count }, (_, index) => {
      const source = raw[index] && typeof raw[index] === "object" ? raw[index] : {};
      return {
        ...source,
        page: index + 1,
        phrase: String(source.phrase || fallbackPhrase(index)).slice(0, 80),
        note: String(source.note || "").slice(0, 180),
        visual_metaphor: String(source.visual_metaphor || source.photo_direction || "真实生活中的单一物件或场景").slice(0, 240),
        layout: allowed(source.layout, LAYOUTS, "center-fragment"),
        anchor: allowed(source.anchor, ANCHORS, "object-specimen"),
        accent: normalizeAccent(source.accent),
        texture: allowed(source.texture, TEXTURES, "xerox-softness"),
        mood: String(source.mood || "quiet").slice(0, 80),
        focus_x: clamp(source.focus_x, 0, 1, 0.5),
        focus_y: clamp(source.focus_y, 0, 1, 0.42),
        zoom: clamp(source.zoom, 0.65, 2, 1),
      };
    });
  }

  function storyboardPayload() {
    return state.storyboard.map((item, index) => ({
      page: index + 1,
      phrase: String(item.phrase || "").trim().slice(0, 80),
      note: String(item.note || "").trim().slice(0, 180),
      visual_metaphor: String(item.visual_metaphor || "").trim().slice(0, 240),
      layout: allowed(item.layout, LAYOUTS, "center-fragment"),
      anchor: allowed(item.anchor, ANCHORS, "object-specimen"),
      accent: normalizeAccent(item.accent),
      texture: allowed(item.texture, TEXTURES, "xerox-softness"),
      mood: String(item.mood || "quiet").trim().slice(0, 80),
      focus_x: clamp(item.focus_x, 0, 1, 0.5),
      focus_y: clamp(item.focus_y, 0, 1, 0.42),
      zoom: clamp(item.zoom, 0.65, 2, 1),
    }));
  }

  function status(text, type = "") {
    state.status = { text, type };
    const target = node("light-status");
    if (!target) return;
    target.textContent = text;
    target.className = `light-status${type ? ` ${type}` : ""}`;
  }

  function setBusy(value, message = "") {
    state.busy = value;
    node("wechat-light-v15")?.setAttribute("aria-busy", String(value));
    document.querySelectorAll("#wechat-light-v15 [data-light-action]").forEach((control) => {
      control.disabled = value;
    });
    if (message) status(message);
  }

  async function run(message, task) {
    if (state.busy) return null;
    setBusy(true, message);
    try {
      return await task();
    } catch (error) {
      status(error.message || String(error), "error");
      return null;
    } finally {
      setBusy(false);
    }
  }

  function upsertVariant(variant) {
    if (!variant?.id) return;
    const index = state.variants.findIndex((item) => item.id === variant.id);
    if (index >= 0) state.variants[index] = variant;
    else state.variants.unshift(variant);
    state.variants.sort((left, right) => Number(right.version || 0) - Number(left.version || 0));
  }

  function setCurrentVariant(variant, options = {}) {
    if (!variant) {
      state.currentVariant = null;
      state.storyboard = [];
      state.pageEvidence.clear();
      return;
    }
    const changed = state.currentVariant?.id !== variant.id;
    state.currentVariant = variant;
    upsertVariant(variant);
    const currentMeta = metadata(variant);
    const candidates = Array.isArray(currentMeta.candidates) ? currentMeta.candidates : [];
    state.candidateIndex = Math.max(0, Math.min(
      Number(currentMeta.selected_candidate_index || state.candidateIndex || 0),
      Math.max(0, candidates.length - 1),
    ));
    if (changed || options.resetEditor) loadEditorFromCandidate();
    if (changed || options.resetStoryboard || !state.storyboard.length) {
      state.storyboard = normalizeStoryboard(variant);
      state.storyboardDirty = false;
      state.selectedPage = Math.min(Math.max(1, state.selectedPage), state.storyboard.length || 1);
    }
  }

  function renderSourceOptions(control) {
    const current = state.brief.sourceId;
    const groups = new Map(SOURCE_GROUPS.map(([id, label]) => {
      const group = document.createElement("optgroup");
      group.label = label;
      return [id, group];
    }));
    state.sources.forEach((source) => {
      groups.get(sourceGroup(source)).appendChild(new Option(sourceLabel(source), source.id));
    });
    control.replaceChildren(...[...groups.values()].filter((group) => group.children.length));
    if (current && state.sources.some((source) => source.id === current)) control.value = current;
    else if (state.sources[0]) {
      control.value = state.sources[0].id;
      state.brief.sourceId = control.value;
    }
  }

  async function loadDrafts() {
    const sourceId = state.brief.sourceId;
    state.drafts = sourceId
      ? await call(`/api/sources/${encodeURIComponent(sourceId)}/drafts`)
      : [];
    if (!state.drafts.some((item) => item.id === state.brief.draftId)) {
      state.brief.draftId = state.drafts[0]?.id || "";
    }
  }

  async function loadWorkspace(preferredVariantId = "") {
    const token = ++state.loadToken;
    state.loading = true;
    try {
      const [sources, variants, corpus] = await Promise.all([
        call("/api/sources?workspace_state=active&include_pool_batches=true&limit=2000"),
        call("/api/platforms/variants?platform=wechat&limit=200"),
        call(`/api/platforms/wechat/light/corpus?recipe=${encodeURIComponent(state.brief.recipe)}&limit=100`),
      ]);
      if (token !== state.loadToken) return;
      state.sources = Array.isArray(sources) ? sources : [];
      state.variants = (Array.isArray(variants) ? variants : []).filter((item) => item.format === "light_series");
      state.corpus = Array.isArray(corpus) ? corpus : [];
      if (!state.sources.some((item) => item.id === state.brief.sourceId)) {
        state.brief.sourceId = state.sources[0]?.id || "";
      }
      await loadDrafts();
      const currentVariantForSource = state.currentVariant?.source_id === state.brief.sourceId
        ? state.currentVariant.id
        : "";
      const targetId = preferredVariantId || currentVariantForSource;
      const target = state.variants.find((item) => item.id === targetId)
        || state.variants.find((item) => item.source_id === state.brief.sourceId)
        || null;
      setCurrentVariant(target, { resetEditor: Boolean(targetId), resetStoryboard: Boolean(targetId) });
      render();
    } catch (error) {
      status(error.message || String(error), "error");
    } finally {
      state.loading = false;
    }
  }

  async function reloadCurrentVariant() {
    if (!state.currentVariant?.id) return null;
    const variant = await call(`/api/platforms/variants/${encodeURIComponent(state.currentVariant.id)}`);
    setCurrentVariant(variant, { resetStoryboard: !state.storyboardDirty });
    return variant;
  }

  function editorPayload(variant = state.currentVariant) {
    return {
      title: state.editor.title || "",
      subtitle: state.editor.subtitle || "",
      summary: state.editor.summary || "",
      body_markdown: state.editor.body_markdown || "",
      tags: state.editor.tags || "",
      theme: variant?.theme || "zen",
    };
  }

  function differs(variant, payload) {
    return ["title", "subtitle", "summary", "body_markdown", "tags", "theme"]
      .some((key) => String(variant?.[key] || "") !== String(payload[key] || ""));
  }

  async function persistCurrent({ adoptCandidate = true } = {}) {
    let variant = state.currentVariant;
    if (!variant) throw new Error("请先生成或选择一个轻内容版本。 ");
    const currentMeta = metadata(variant);
    const candidates = Array.isArray(currentMeta.candidates) ? currentMeta.candidates : [];
    if (
      adoptCandidate
      && candidates.length
      && Number(currentMeta.selected_candidate_index || 0) !== state.candidateIndex
    ) {
      variant = await call(
        `/api/platforms/wechat/light/variants/${encodeURIComponent(variant.id)}/select-candidate`,
        {
          method: "POST",
          body: JSON.stringify({ candidate_index: state.candidateIndex }),
        },
      );
      state.currentVariant = variant;
      upsertVariant(variant);
    }
    const payload = editorPayload(variant);
    if (differs(variant, payload)) {
      variant = await call(`/api/platforms/variants/${encodeURIComponent(variant.id)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      state.currentVariant = variant;
      upsertVariant(variant);
      if (!state.storyboardDirty) state.storyboard = normalizeStoryboard(variant);
    }
    return variant;
  }

  async function saveStoryboardIfDirty(variant) {
    if (!state.storyboardDirty) return variant;
    const revised = await call(
      `/api/platforms/wechat/light/variants/${encodeURIComponent(variant.id)}/storyboard`,
      {
        method: "POST",
        body: JSON.stringify({ pages: storyboardPayload() }),
      },
    );
    state.currentVariant = revised;
    upsertVariant(revised);
    state.storyboard = normalizeStoryboard(revised);
    state.storyboardDirty = false;
    return revised;
  }

  function briefPayload() {
    return {
      source_id: state.brief.sourceId,
      draft_id: state.brief.draftId || null,
      recipe: state.brief.recipe,
      image_count: Number(state.brief.imageCount || 4),
      seasonal_topic: state.brief.seasonalTopic || "",
      audience: state.brief.audience || "",
      tone: state.brief.tone || "自然、具体、克制",
      visual_style: state.brief.visualStyle || "auto",
      quality_mode: state.brief.qualityMode || "studio",
      feedback: state.brief.feedback || "",
      theme: "zen",
      author: "",
    };
  }

  async function generate() {
    const payload = briefPayload();
    if (!payload.source_id) {
      status("请先选择来源。", "error");
      return;
    }
    await run("选题、写作、审稿与视觉导演正在协作…", async () => {
      const variant = await call("/api/platforms/wechat/light/variants", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setCurrentVariant(variant, { resetEditor: true, resetStoryboard: true });
      state.stage = 2;
      saveStage();
      status("已生成候选。先阅读审稿意见并编辑当前版本，再进入视觉分镜。", "ok");
      await loadWorkspace(variant.id);
    });
  }

  async function useCandidate() {
    await run("正在采用当前候选并创建不可变版本…", async () => {
      const variant = await persistCurrent({ adoptCandidate: true });
      status(`候选 ${state.candidateIndex + 1} 已保存为 v${variant.version}。`, "ok");
      render();
    });
  }

  async function saveEdit() {
    await run("正在保存编辑框里的当前文字…", async () => {
      const variant = await persistCurrent({ adoptCandidate: true });
      status(`当前候选与人工修改已保存为 v${variant.version}。`, "ok");
      render();
    });
  }

  async function proceedToVisual() {
    await run("正在先保存当前候选和编辑稿…", async () => {
      await persistCurrent({ adoptCandidate: true });
      state.stage = 3;
      saveStage();
      status("文案已冻结为新版本。现在可以逐页编辑视觉分镜。", "ok");
      render();
    });
  }

  async function iterate() {
    const feedback = node("light-feedback")?.value.trim() || "";
    if (!feedback) {
      status("请写清楚要调整的角度、文字或画面。", "error");
      return;
    }
    await run("正在保存当前稿，并带着反馈重新策划和审稿…", async () => {
      const current = await persistCurrent({ adoptCandidate: true });
      const revised = await call(
        `/api/platforms/wechat/light/variants/${encodeURIComponent(current.id)}/iterate`,
        {
          method: "POST",
          body: JSON.stringify({ feedback, quality_mode: state.brief.qualityMode || "studio" }),
        },
      );
      state.pageEvidence.clear();
      setCurrentVariant(revised, { resetEditor: true, resetStoryboard: true });
      status("新一轮候选与审稿已经加载。", "ok");
      await loadWorkspace(revised.id);
    });
  }

  async function approve() {
    await run("正在批准当前实际编辑稿并加入私有优质语料…", async () => {
      const variant = await persistCurrent({ adoptCandidate: true });
      const note = node("light-feedback")?.value.trim() || "人工确认可作为未来同配方的正向样本";
      await call(`/api/platforms/wechat/light/variants/${encodeURIComponent(variant.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
      status("当前实际编辑稿已批准；未来只学习这版的结构、节奏与判断，不照抄句子。", "ok");
      await loadWorkspace(variant.id);
    });
  }

  async function openMemoryCandidate() {
    await run("正在先冻结当前候选和编辑框内容…", async () => {
      const variant = await persistCurrent({ adoptCandidate: true });
      document.dispatchEvent(new CustomEvent("x2red:memory-source", {
        detail: { kind: "platform_variant", id: variant.id },
      }));
      status(`已冻结为 v${variant.version}，请在池子记忆中检查候选。`, "ok");
    });
  }

  function ingestRenderResult(result) {
    (Array.isArray(result?.pages) ? result.pages : []).forEach((page) => {
      const number = Number(page.page);
      if (Number.isInteger(number) && number > 0) state.pageEvidence.set(number, page);
    });
  }

  function posterKey(page) {
    const evidence = state.pageEvidence.get(page);
    if (evidence?.poster_key) return evidence.poster_key;
    const padded = String(page).padStart(2, "0");
    const files = outputPaths();
    return files[`poster_${padded}`] ? `poster_${padded}` : "";
  }

  function anchorKey(page) {
    const evidence = state.pageEvidence.get(page);
    if (evidence?.anchor_key) return evidence.anchor_key;
    const padded = String(page).padStart(2, "0");
    const files = outputPaths();
    return files[`anchor_${padded}`] ? `anchor_${padded}` : "";
  }

  function renderFileUrl(key) {
    if (!state.currentVariant?.id || !key) return "";
    return `/api/platforms/variants/${encodeURIComponent(state.currentVariant.id)}/files/${encodeURIComponent(key)}?v=${Date.now()}`;
  }

  function selectedPages() {
    const page = Number(state.selectedPage || 1);
    return Number.isInteger(page) && page > 0 ? [page] : [];
  }

  async function renderPages(mode, pages) {
    if (!state.currentVariant) {
      status("请先生成或选择一个轻内容版本。", "error");
      return;
    }
    const uniquePages = [...new Set(pages.map(Number).filter((page) => Number.isInteger(page) && page > 0))];
    if (!uniquePages.length) {
      status("请至少选择一个有效页面。", "error");
      return;
    }
    if (mode === "recompose" && uniquePages.some((page) => !anchorKey(page))) {
      status("该页没有保留原始视觉锚点，不能仅重新排版。请明确选择“重新生成本页（调用图片模型）”。", "error");
      render();
      return;
    }
    const messages = {
      render_missing: "正在保存当前稿和分镜，并生成缺失视觉锚点…",
      recompose: "正在仅重新排版本地成品，不会调用图片模型…",
      regenerate: "正在重新生成视觉锚点：这一步会调用图片模型…",
    };
    await run(messages[mode] || "正在渲染…", async () => {
      let variant = await persistCurrent({ adoptCandidate: true });
      variant = await saveStoryboardIfDirty(variant);
      if (isMinimalZine(variant)) {
        const result = await call(
          `/api/native-skills/minimal-zine/variants/${encodeURIComponent(variant.id)}/render`,
          {
            method: "POST",
            body: JSON.stringify({ mode, pages: uniquePages }),
          },
        );
        ingestRenderResult(result);
        const fresh = await reloadCurrentVariant();
        if (fresh) variant = fresh;
      } else {
        if (mode !== "render_missing") {
          throw new Error("仅 Minimal Zine 支持保留原始锚点后的重新排版或逐页再生图。请先切换到 Minimal Zine 视觉路线。");
        }
        const result = await call(`/api/platforms/variants/${encodeURIComponent(variant.id)}/render`, {
          method: "POST",
          body: JSON.stringify({ package: true }),
        });
        if (result?.variant) {
          variant = result.variant;
          setCurrentVariant(variant, { resetStoryboard: !state.storyboardDirty });
        }
      }
      state.stage = 4;
      saveStage();
      const completed = uniquePages.map((page) => `第 ${page} 页`).join("、");
      const resultMessage = mode === "recompose"
        ? `${completed} 已仅重新排版，未调用图片模型。`
        : mode === "regenerate"
          ? `${completed} 已重新生成视觉锚点，并重建本地版式。`
          : `${completed} 已完成渲染并同步更新预览与发布包。`;
      status(resultMessage, "ok");
      render();
    });
  }

  async function renderMissing() {
    const pages = state.storyboard
      .map((item) => item.page)
      .filter((page) => !posterKey(page));
    await renderPages("render_missing", pages.length ? pages : state.storyboard.map((item) => item.page));
  }

  async function recomposeSelected() {
    await renderPages("recompose", selectedPages());
  }

  async function regenerateSelected() {
    await renderPages("regenerate", selectedPages());
  }

  async function addCorpus() {
    const title = node("light-corpus-title")?.value.trim() || "";
    const body = node("light-corpus-body")?.value.trim() || "";
    if (!title && !body) {
      status("请添加你原创或有权使用的样本。", "error");
      return;
    }
    await run("正在加入授权样本…", async () => {
      await call("/api/platforms/wechat/light/corpus", {
        method: "POST",
        body: JSON.stringify({
          recipe: state.brief.recipe,
          title,
          body_markdown: body,
          visual_style: state.brief.visualStyle,
          note: node("light-corpus-note")?.value || "",
        }),
      });
      status("授权样本已加入；后续只提炼结构与节奏，不复制原句。", "ok");
      await loadWorkspace(state.currentVariant?.id || "");
    });
  }

  async function requestStage(next) {
    const stage = Number(next);
    if (stage === state.stage || state.busy) return;
    if (stage > 1 && !state.currentVariant) {
      status("请先在“任务设置”生成一个轻内容版本。", "error");
      state.stage = 1;
      saveStage();
      renderStageState();
      return;
    }
    if (state.stage === 2 && stage !== 2) {
      await proceedToStage(stage);
      return;
    }
    state.stage = stage;
    saveStage();
    renderStageState();
  }

  async function proceedToStage(stage) {
    await run("正在先保存当前候选和编辑稿…", async () => {
      await persistCurrent({ adoptCandidate: true });
      state.stage = stage;
      saveStage();
      status("当前文案已保存为不可变版本。", "ok");
      render();
    });
  }

  function stageDefinition(number, title, description) {
    const section = create("section", "light-stage");
    section.id = `light-stage-${number}`;
    section.dataset.stage = String(number);
    const header = create("header", "light-stage-header");
    const heading = create("div", "light-stage-heading");
    heading.append(
      create("p", "light-stage-kicker", `阶段 ${String(number).padStart(2, "0")}`),
      create("h3", "", title),
      create("p", "", description),
    );
    const summary = create("p", "light-stage-summary");
    summary.id = `light-stage-summary-${number}`;
    header.append(heading, summary);
    const body = create("div", "light-stage-body");
    body.id = `light-stage-body-${number}`;
    section.append(header, body);
    return section;
  }

  function injectModeTabs(view) {
    const intro = view.querySelector(".page-intro");
    if (!intro || node("wechat-mode-tabs")) return;
    const tabs = create("div", "wechat-mode-tabs");
    tabs.id = "wechat-mode-tabs";
    tabs.setAttribute("role", "tablist");
    [["article", "长文编辑"], ["light", "轻内容图组"]].forEach(([mode, label]) => {
      const tab = button(label, "wechat-mode-tab", () => setMode(mode));
      tab.dataset.mode = mode;
      tab.setAttribute("role", "tab");
      tabs.appendChild(tab);
    });
    intro.appendChild(tabs);
  }

  function injectLab(view) {
    if (node("wechat-light-v15")) return;
    const longLayout = view.querySelector(".platform-studio-layout");
    if (!longLayout) return;
    const lab = create("section", "light-v15");
    lab.id = "wechat-light-v15";
    lab.hidden = true;
    lab.setAttribute("aria-label", "公众号轻内容工作台");
    const statusNode = create("div", "light-status", state.status.text);
    statusNode.id = "light-status";
    statusNode.setAttribute("role", "status");
    const layout = create("div", "light-v15-layout");
    const rail = create("nav", "light-stage-rail");
    rail.setAttribute("aria-label", "轻内容任务阶段");
    rail.appendChild(create("div", "light-stage-nav-label", "轻内容任务流"));
    const canvas = create("div", "light-stage-canvas");
    [
      [1, "任务设置", "选择可追溯来源、内容配方、视觉路线与本轮要求。"],
      [2, "文案候选", "比较候选与审稿意见，采用并编辑当前不可变版本。"],
      [3, "视觉分镜", "逐页编辑视觉说明，再决定只排版还是调用图片模型。"],
      [4, "成品交付", "检查整组图片、预览、清单与发布包，并完成人工复核。"],
    ].forEach(([number, title, description]) => {
      const tab = button("", "light-stage-tab", () => { void requestStage(number); });
      tab.dataset.stage = String(number);
      tab.dataset.lightAction = "true";
      tab.setAttribute("aria-label", `阶段 ${String(number).padStart(2, "0")}：${title}`);
      tab.setAttribute("aria-controls", `light-stage-${number}`);
      tab.append(create("span", "light-stage-tab-number", String(number)), create("span", "", title));
      rail.appendChild(tab);
      canvas.appendChild(stageDefinition(number, title, description));
    });
    layout.append(rail, canvas);
    lab.append(statusNode, layout);
    longLayout.before(lab);
  }

  function choiceGrid(name, values, selectedValue, onChange) {
    const grid = create("div", "light-choice-grid");
    values.forEach(([value, title, note]) => {
      const choice = create("label", "light-choice");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = name;
      radio.value = value;
      radio.checked = value === selectedValue;
      radio.addEventListener("change", () => onChange(value));
      choice.append(radio, create("strong", "", title), create("small", "", note));
      grid.appendChild(choice);
    });
    return grid;
  }

  function actionBar(copy, primary, secondary = []) {
    const bar = create("div", "light-action-bar");
    bar.appendChild(create("div", "light-action-bar-copy", copy));
    const actions = create("div", "light-action-bar-actions");
    if (primary) {
      primary.dataset.lightAction = "true";
      actions.appendChild(primary);
    }
    secondary.forEach((value) => {
      value.dataset.lightAction = "true";
      actions.appendChild(value);
    });
    bar.appendChild(actions);
    return bar;
  }

  function renderTask() {
    const body = node("light-stage-body-1");
    if (!body) return;
    body.replaceChildren();
    const grid = create("div", "light-task-grid");
    const sourceCard = create("section", "light-section-card");
    sourceCard.appendChild(create("h4", "", "任务来源与内容配方"));
    const source = document.createElement("select");
    source.id = "light-source";
    renderSourceOptions(source);
    source.addEventListener("change", async () => {
      state.brief.sourceId = source.value;
      const variant = state.variants.find((item) => item.source_id === state.brief.sourceId) || null;
      setCurrentVariant(variant, { resetEditor: true, resetStoryboard: true });
      await loadDrafts();
      render();
    });
    sourceCard.appendChild(labelFor("来源", source));
    const draft = document.createElement("select");
    draft.id = "light-draft";
    draft.appendChild(new Option("直接使用来源", ""));
    state.drafts.forEach((item) => draft.appendChild(new Option(`v${item.version} · ${item.title || "未命名终稿"}`, item.id)));
    draft.value = state.brief.draftId;
    draft.addEventListener("change", () => { state.brief.draftId = draft.value; });
    sourceCard.appendChild(labelFor("基础终稿", draft));
    sourceCard.appendChild(create("p", "", "内容配方"));
    sourceCard.appendChild(choiceGrid("light-recipe", RECIPES, state.brief.recipe, (value) => {
      state.brief.recipe = value;
      renderTask();
    }));
    if (state.brief.recipe === "seasonal") {
      const topic = input(state.brief.seasonalTopic, { maxLength: 120, placeholder: "例如：处暑、秋分早晚温差" });
      topic.addEventListener("input", () => { state.brief.seasonalTopic = topic.value; });
      sourceCard.appendChild(labelFor("节气或时令主题", topic));
    }

    const settingsCard = create("section", "light-section-card");
    settingsCard.appendChild(create("h4", "", "视觉路线与本轮要求"));
    settingsCard.appendChild(create("p", "", "视觉路线"));
    settingsCard.appendChild(choiceGrid("light-style", STYLES, state.brief.visualStyle, (value) => {
      state.brief.visualStyle = value;
      renderTask();
    }));
    const pair = create("div", "light-field-grid");
    const count = select([["3", "3 张"], ["4", "4 张"], ["5", "5 张"], ["6", "6 张"]], String(state.brief.imageCount));
    count.addEventListener("change", () => { state.brief.imageCount = Number(count.value); });
    const quality = select([["studio", "工作室 · 多路审稿"], ["fast", "快速 · 控制调用"]], state.brief.qualityMode);
    quality.addEventListener("change", () => { state.brief.qualityMode = quality.value; });
    pair.append(labelFor("图片数量", count), labelFor("质量模式", quality));
    settingsCard.appendChild(pair);
    const audience = input(state.brief.audience, { maxLength: 500, placeholder: "例如：高压工作的城市读者" });
    audience.addEventListener("input", () => { state.brief.audience = audience.value; });
    settingsCard.appendChild(labelFor("目标读者", audience));
    const tone = input(state.brief.tone, { maxLength: 300 });
    tone.addEventListener("input", () => { state.brief.tone = tone.value; });
    settingsCard.appendChild(labelFor("语气", tone));
    const feedback = input(state.brief.feedback, { multiline: true, rows: 3, maxLength: 3000, placeholder: "哪些事实边界、角度或表达必须保留？" });
    feedback.addEventListener("input", () => { state.brief.feedback = feedback.value; });
    settingsCard.appendChild(labelFor("本轮要求", feedback));
    const advanced = create("details", "light-advanced");
    const advancedSummary = create("summary", "", "高级设置与授权语料");
    advancedSummary.appendChild(create("span", "light-corpus-count", String(state.corpus.length)));
    const advancedContent = create("div", "light-advanced-content");
    const corpusTitle = input("", { id: "light-corpus-title", maxLength: 160, placeholder: "授权样本标题" });
    const corpusBody = input("", { id: "light-corpus-body", multiline: true, rows: 4, maxLength: 8000, placeholder: "仅添加你原创或有权使用的样本" });
    const corpusNote = input("", { id: "light-corpus-note", maxLength: 3000, placeholder: "喜欢什么结构或节奏，不要照抄句子" });
    const corpusButton = button("加入授权样本", "light-secondary-action", () => { void addCorpus(); });
    corpusButton.dataset.lightAction = "true";
    advancedContent.append(
      labelFor("授权样本标题", corpusTitle),
      labelFor("授权样本正文", corpusBody),
      labelFor("学习备注", corpusNote),
      corpusButton,
    );
    advanced.append(advancedSummary, advancedContent);
    settingsCard.appendChild(advanced);
    grid.append(sourceCard, settingsCard);
    body.appendChild(grid);
    body.appendChild(actionBar(
      "生成后会进入候选比较；不会自动调用任何图片模型。",
      button("生成 3 个文案候选", "light-primary-action", () => { void generate(); }),
      [button("刷新来源与版本", "light-secondary-action", () => { void loadWorkspace(state.currentVariant?.id || ""); })],
    ));
  }

  function reviewCard(title, value, fallback) {
    const card = create("article", "light-review-card");
    card.appendChild(create("strong", "", title));
    const strengths = Array.isArray(value?.strengths) ? value.strengths.filter(Boolean).slice(0, 2).join("；") : "";
    const fixes = Array.isArray(value?.must_fix) ? value.must_fix.filter(Boolean).slice(0, 2).join("；") : "";
    card.appendChild(create("span", "", strengths || fixes || fallback));
    return card;
  }

  function reviewAt(payload, index) {
    const values = Array.isArray(payload?.candidate_reviews) ? payload.candidate_reviews : [];
    return values.find((item) => Number(item.candidate_index) === index) || payload || {};
  }

  function renderCopy() {
    const body = node("light-stage-body-2");
    if (!body) return;
    body.replaceChildren();
    if (!state.currentVariant) {
      body.appendChild(create("div", "light-section-card", "先在“任务设置”生成轻内容候选。"));
      return;
    }
    const grid = create("div", "light-copy-grid");
    const candidateCard = create("section", "light-section-card");
    candidateCard.appendChild(create("h4", "", `v${state.currentVariant.version} · 候选与审阅`));
    const meta = metadata();
    const score = create("div", "light-score-row");
    score.append(create("strong", "", Number(meta.quality_score || 0).toFixed(1)), create("span", "", "/ 10 综合质量"));
    candidateCard.appendChild(score);
    const versions = create("div", "light-version-list");
    const forSource = state.variants.filter((item) => item.source_id === state.brief.sourceId);
    forSource.forEach((variant) => {
      const versionMeta = parse(variant.metadata_json, {});
      const versionButton = button(
        `v${variant.version} · ${versionMeta.recipe_label || "轻内容"}`,
        `light-version-chip${variant.id === state.currentVariant.id ? " active" : ""}`,
        () => {
          setCurrentVariant(variant, { resetEditor: true, resetStoryboard: true });
          render();
        },
      );
      versionButton.dataset.lightAction = "true";
      versions.appendChild(versionButton);
    });
    candidateCard.appendChild(versions);
    const tabs = create("div", "light-candidate-tabs");
    const candidates = Array.isArray(meta.candidates) ? meta.candidates : [];
    candidates.forEach((candidate, index) => {
      const tab = button(
        `候选 ${index + 1} · ${candidate.angle || "不同角度"}`,
        `light-candidate-tab${index === state.candidateIndex ? " active" : ""}`,
        () => {
          state.candidateIndex = index;
          loadEditorFromCandidate();
          renderCopy();
        },
      );
      tab.dataset.lightAction = "true";
      tabs.appendChild(tab);
    });
    if (!candidates.length) tabs.appendChild(create("span", "light-page-state", "人工版本"));
    candidateCard.appendChild(tabs);
    const reviews = create("div", "light-review-list");
    reviews.append(
      reviewCard("目标读者审稿", reviewAt(meta.reviews?.audience, state.candidateIndex), "是否真实、尊重、值得分享"),
      reviewCard("文化事实审校", reviewAt(meta.reviews?.culture, state.candidateIndex), "是否忠于来源、无夸大和刻板印象"),
      reviewCard("总编选择", { strengths: [meta.chief_editor_note], must_fix: [meta.revision_summary] }, "为什么选这版、修改了什么"),
      reviewCard("语料使用", { strengths: [`参考 ${meta.corpus_item_ids?.length || 0} 条已批准语料`] }, "只学习结构与节奏，不照抄句子"),
    );
    candidateCard.appendChild(reviews);

    const editorCard = create("section", "light-section-card");
    editorCard.appendChild(create("h4", "", "当前编辑稿"));
    const fields = [
      ["标题", "title", { maxLength: 160 }],
      ["副标题", "subtitle", { maxLength: 240 }],
      ["摘要", "summary", { multiline: true, rows: 3, maxLength: 1000 }],
      ["短正文", "body_markdown", { multiline: true, rows: 12, maxLength: 50000, className: "light-editor-body" }],
      ["标签", "tags", { maxLength: 1000 }],
    ];
    fields.forEach(([label, key, options]) => {
      const control = input(state.editor[key], options);
      control.id = `light-edit-${key.replace("body_markdown", "body")}`;
      control.addEventListener("input", () => { state.editor[key] = control.value; });
      editorCard.appendChild(labelFor(label, control));
    });
    const actions = create("div", "light-action-row");
    const adopt = button("采用当前候选", "light-secondary-action", () => { void useCandidate(); });
    const save = button("保存当前编辑稿", "light-secondary-action", () => { void saveEdit(); });
    adopt.dataset.lightAction = "true";
    save.dataset.lightAction = "true";
    actions.append(adopt, save);
    editorCard.appendChild(actions);
    const feedback = input("", { id: "light-feedback", multiline: true, rows: 4, maxLength: 3000, placeholder: "指出具体要调整的角度、事实边界、句子或画面。" });
    const feedbackSection = create("div", "light-feedback");
    feedbackSection.append(
      labelFor("继续迭代意见", feedback),
      button("按反馈重新迭代", "light-secondary-action", () => { void iterate(); }),
      button("批准到旧优质语料（兼容）", "light-secondary-action", () => { void approve(); }),
      button("加入池子记忆", "light-secondary-action", () => { void openMemoryCandidate(); }),
    );
    feedbackSection.querySelectorAll("button").forEach((value) => { value.dataset.lightAction = "true"; });
    editorCard.appendChild(feedbackSection);
    grid.append(candidateCard, editorCard);
    body.appendChild(grid);
    body.appendChild(actionBar(
      "离开本阶段前，会先采用当前候选并保存编辑框里的文字，得到新的不可变版本。",
      button("保存当前文案，进入视觉分镜", "light-primary-action", () => { void proceedToVisual(); }),
    ));
  }

  function storyboardField(item, key, label, options = {}) {
    const control = input(String(item[key] ?? ""), options);
    control.addEventListener("input", () => {
      const value = options.type === "number" ? Number(control.value) : control.value;
      if (options.type === "number" && !Number.isFinite(value)) return;
      updateStoryboardValue(item, key, value);
    });
    return labelFor(label, control);
  }

  function updateStoryboardValue(item, key, value) {
    item[key] = value;
    state.storyboardDirty = true;
    renderStageState();
  }

  function storyboardSelectField(item, key, label, options) {
    const control = select(options, String(item[key] ?? ""));
    control.addEventListener("change", () => updateStoryboardValue(item, key, control.value));
    return labelFor(label, control);
  }

  function accentOptionValue(value) {
    const normalized = normalizeAccent(value);
    if (NAMED_ACCENTS.has(normalized)) return normalized;
    return ACCENT_COLOR_NAMES.get(normalized) || "custom";
  }

  function storyboardAccentField(item) {
    const group = create("div", "light-accent-control");
    const selected = accentOptionValue(item.accent);
    const control = select([...ACCENT_OPTIONS, ["custom", "自定义 #RRGGBB"]], selected);
    const normalized = normalizeAccent(item.accent);
    const custom = input(
      /^#[0-9a-f]{6}$/.test(normalized) ? normalized : "#1646d8",
      { type: "color" },
    );
    const customField = labelFor("自定义色（#RRGGBB）", custom);
    customField.classList.add("light-accent-custom");
    customField.hidden = selected !== "custom";
    control.addEventListener("change", () => {
      const isCustom = control.value === "custom";
      customField.hidden = !isCustom;
      if (isCustom) {
        updateStoryboardValue(item, "accent", custom.value.toLowerCase());
        custom.focus();
      } else {
        updateStoryboardValue(item, "accent", control.value);
      }
    });
    custom.addEventListener("input", () => {
      updateStoryboardValue(item, "accent", custom.value.toLowerCase());
    });
    group.append(labelFor("强调色", control), customField);
    return group;
  }

  function pagePrompt(item) {
    return item.final_prompt
      || state.pageEvidence.get(item.page)?.final_prompt
      || "尚未编译最终 Prompt。保存分镜并渲染后，可在这里查看本页使用的 Prompt。";
  }

  function pageActionLabel(page) {
    const evidence = state.pageEvidence.get(page);
    if (evidence?.action === "recomposed") return "已仅重新排版";
    if (evidence?.action === "regenerated") return "已重新生成视觉锚点";
    if (evidence?.action === "cached") return "已使用已有成品";
    if (posterKey(page)) return "已有最终海报";
    return "尚未渲染";
  }

  function selectStoryboardPage(page) {
    if (page === state.selectedPage) return;
    state.selectedPage = page;
    renderVisual();
  }

  function renderStoryboardSummary(item) {
    const card = create("article", "light-storyboard-card light-storyboard-card-compact");
    card.dataset.page = String(item.page);
    const selectPage = button("", "light-storyboard-summary", () => selectStoryboardPage(item.page));
    selectPage.dataset.lightAction = "true";
    selectPage.setAttribute("aria-label", `展开第 ${item.page} 页的视觉分镜编辑`);
    const copy = create("span", "light-storyboard-summary-copy");
    copy.append(
      create("strong", "light-storyboard-summary-phrase", item.phrase || "未填写短句"),
      create("span", "light-storyboard-summary-metaphor", `视觉隐喻 · ${item.visual_metaphor || "未填写"}`),
    );
    selectPage.append(
      create("span", "light-storyboard-summary-page", `第 ${item.page} 页`),
      copy,
      create("span", "light-page-state", pageActionLabel(item.page)),
    );
    card.appendChild(selectPage);
    return card;
  }

  function renderStoryboardCard(item) {
    if (item.page !== state.selectedPage) return renderStoryboardSummary(item);
    const card = create("article", "light-storyboard-card light-storyboard-card-expanded selected");
    card.dataset.page = String(item.page);
    const head = create("div", "light-storyboard-head");
    head.append(
      create("span", "light-page-select", `第 ${item.page} 页 · 正在编辑`),
      create("span", "light-page-state", pageActionLabel(item.page)),
    );
    card.appendChild(head);
    card.append(storyboardField(item, "phrase", "短句", { maxLength: 80 }));
    card.append(storyboardField(item, "note", "说明", { multiline: true, rows: 2, maxLength: 180 }));
    const row = create("div", "light-field-grid");
    row.append(
      storyboardField(item, "visual_metaphor", "视觉隐喻", { maxLength: 240 }),
      storyboardSelectField(item, "layout", "版式", LAYOUT_OPTIONS),
      storyboardSelectField(item, "anchor", "视觉锚点", ANCHOR_OPTIONS),
      storyboardAccentField(item),
      storyboardSelectField(item, "texture", "质感", TEXTURE_OPTIONS),
      storyboardField(item, "mood", "情绪", { maxLength: 80 }),
      storyboardField(item, "focus_x", "焦点 X", {
        type: "number", min: 0, max: 1, step: 0.01, inputMode: "decimal",
      }),
      storyboardField(item, "focus_y", "焦点 Y", {
        type: "number", min: 0, max: 1, step: 0.01, inputMode: "decimal",
      }),
      storyboardField(item, "zoom", "缩放", {
        type: "number", min: 0.65, max: 2, step: 0.05, inputMode: "decimal",
      }),
    );
    card.appendChild(row);
    const prompt = create("details", "light-prompt");
    prompt.append(create("summary", "", "查看编译 Prompt"), create("pre", "", pagePrompt(item)));
    card.appendChild(prompt);
    return card;
  }

  function evidenceFigure(title, key, alt) {
    const figure = create("figure", "light-evidence");
    const image = document.createElement("img");
    image.src = renderFileUrl(key);
    image.alt = alt;
    figure.append(image, create("figcaption", "", title));
    return figure;
  }

  function renderInspector() {
    const card = create("aside", "light-section-card light-page-inspector");
    const page = state.storyboard.find((item) => item.page === state.selectedPage) || state.storyboard[0];
    if (!page) {
      card.appendChild(create("p", "", "生成文案后才会建立逐页视觉分镜。"));
      return card;
    }
    card.appendChild(create("h4", "", `第 ${page.page} 页 · 证据与操作`));
    card.appendChild(create("p", "light-page-inspector-copy", "原始视觉锚点与最终海报分开保存；最终中文排版始终由本地合成。"));
    const raw = anchorKey(page.page);
    const poster = posterKey(page.page);
    if (!raw) {
      card.appendChild(create("p", "light-legacy-note", "此版本没有保留原始视觉锚点。仅重新排版不可用，直到你明确重新生成本页。"));
    }
    const evidence = create("div", "light-evidence-grid");
    if (raw) evidence.appendChild(evidenceFigure("原始视觉锚点", raw, `第 ${page.page} 页原始视觉锚点`));
    if (poster) evidence.appendChild(evidenceFigure("最终本地海报", poster, `第 ${page.page} 页最终海报`));
    if (evidence.children.length) card.appendChild(evidence);
    const actions = create("div", "light-page-actions");
    const recompose = button("仅重新排版（不调用图片模型）", "light-page-action", () => { void recomposeSelected(); });
    recompose.dataset.lightAction = "true";
    recompose.disabled = !raw || !isMinimalZine();
    recompose.title = raw ? "基于已有原始视觉锚点重新本地合成" : "此版本没有保留原始视觉锚点";
    const regenerate = button("重新生成本页（调用图片模型）", "light-page-action regenerate", () => { void regenerateSelected(); });
    regenerate.dataset.lightAction = "true";
    regenerate.disabled = !isMinimalZine();
    actions.append(recompose, regenerate);
    card.appendChild(actions);
    return card;
  }

  function renderVisual() {
    const body = node("light-stage-body-3");
    if (!body) return;
    body.replaceChildren();
    if (!state.currentVariant) {
      body.appendChild(create("div", "light-section-card", "先在“文案候选”完成一版可编辑的轻内容。"));
      return;
    }
    const grid = create("div", "light-visual-grid");
    const listCard = create("section", "light-section-card");
    listCard.append(create("h4", "", "逐页视觉分镜"), create("p", "", "编辑短句、说明或视觉隐喻会创建新的不可变版本；它们不会混进渲染请求。"));
    const storyboard = create("div", "light-storyboard-list");
    state.storyboard.forEach((item) => storyboard.appendChild(renderStoryboardCard(item)));
    listCard.appendChild(storyboard);
    grid.append(listCard, renderInspector());
    body.appendChild(grid);
    const routeNote = isMinimalZine()
      ? "保存分镜后，优先生成缺失页；已有锚点可无成本重新排版，重新生成才会调用图片模型。"
      : "当前视觉路线使用常规图组渲染；要使用逐页无成本重新排版，请切换到 Minimal Zine。";
    body.appendChild(actionBar(
      routeNote,
      button("生成缺失页面（调用图片模型）", "light-primary-action", () => { void renderMissing(); }),
      [button("保存分镜", "light-secondary-action", () => { void saveStoryboardOnly(); })],
    ));
  }

  async function saveStoryboardOnly() {
    if (!state.currentVariant) return;
    await run("正在保存完整视觉分镜为新的不可变版本…", async () => {
      const variant = await persistCurrent({ adoptCandidate: true });
      const revised = await saveStoryboardIfDirty(variant);
      status(`视觉分镜已保存为 v${revised.version}；尚未调用图片模型。`, "ok");
      render();
    });
  }

  function outputLink(key, label) {
    const link = create("a", "", label);
    link.href = `/api/platforms/variants/${encodeURIComponent(state.currentVariant.id)}/files/${encodeURIComponent(key)}`;
    link.target = "_blank";
    link.rel = "noreferrer";
    return link;
  }

  function renderDelivery() {
    const body = node("light-stage-body-4");
    if (!body) return;
    body.replaceChildren();
    if (!state.currentVariant) {
      body.appendChild(create("div", "light-section-card", "完成图组后，这里会显示预览、清单和发布包。"));
      return;
    }
    const card = create("section", "light-section-card");
    const files = outputPaths();
    card.appendChild(create("h4", "", `v${state.currentVariant.version} · 成品交付`));
    card.appendChild(create("p", "", "以下文件来自当前不可变版本。下载或打开预览不会触发重新生成。"));
    const links = create("div", "light-output-links");
    [["manifest", "查看 manifest"], ["preview", "打开整组预览"], ["package", "下载发布包 ZIP"]].forEach(([key, label]) => {
      if (files[key]) links.appendChild(outputLink(key, label));
    });
    if (links.children.length) card.appendChild(links);
    const gallery = create("div", "light-gallery");
    const pages = state.storyboard.map((item) => item.page);
    pages.forEach((page) => {
      const key = posterKey(page);
      if (!key) return;
      const item = state.storyboard.find((value) => value.page === page) || {};
      const figure = create("figure", "light-poster");
      const image = document.createElement("img");
      image.src = renderFileUrl(key);
      image.alt = item.phrase || `第 ${page} 页海报`;
      const caption = create("figcaption");
      caption.append(create("span", "", item.phrase || `第 ${page} 页`), create("span", "", `第 ${page} 页`));
      figure.append(image, caption);
      gallery.appendChild(figure);
    });
    if (gallery.children.length) card.appendChild(gallery);
    else card.appendChild(create("p", "", "当前版本还没有最终海报。回到视觉分镜后明确开始渲染。"));
    card.appendChild(create("div", "light-human-review", "人工复核提醒：请确认事实、引用范围、图片与媒体版权，并检查是否存在异常字符、模型水印或平台标识。X2RED 只生成预览与发布包，不会点击最终发布。"));
    body.appendChild(card);
    body.appendChild(actionBar(
      "成品可继续回到文案或分镜阶段修订；任何改动都会创建新版本。",
      button("返回视觉分镜", "light-primary-action", () => { void requestStage(3); }),
      [
        button("加入池子记忆", "light-secondary-action", () => { void openMemoryCandidate(); }),
        button("刷新当前版本", "light-secondary-action", () => { void refreshDelivery(); }),
      ],
    ));
  }

  async function refreshDelivery() {
    await run("正在读取当前版本的交付文件…", async () => {
      await reloadCurrentVariant();
      render();
      status("已刷新当前版本的预览、清单和发布包状态。", "ok");
    });
  }

  function stageSummary(number) {
    if (number === 1) {
      const source = state.sources.find((item) => item.id === state.brief.sourceId);
      return source ? `${sourceLabel(source)} · ${state.brief.recipe}` : "尚未选择来源";
    }
    if (!state.currentVariant) return "等待前一阶段完成";
    if (number === 2) return `v${state.currentVariant.version} · 候选 ${state.candidateIndex + 1} 已选中`;
    if (number === 3) return state.storyboardDirty ? "分镜有未保存修改" : `${state.storyboard.length} 页分镜已就绪`;
    const posters = state.storyboard.filter((item) => posterKey(item.page)).length;
    return posters ? `${posters}/${state.storyboard.length} 页海报已生成` : "等待生成图组";
  }

  function renderStageState() {
    [1, 2, 3, 4].forEach((number) => {
      const section = node(`light-stage-${number}`);
      const body = node(`light-stage-body-${number}`);
      const summary = node(`light-stage-summary-${number}`);
      const tab = document.querySelector(`#wechat-light-v15 .light-stage-tab[data-stage="${number}"]`);
      const current = number === state.stage;
      const complete = state.currentVariant && ((number === 1) || (number === 2) || (number === 3 && !state.storyboardDirty) || (number === 4 && state.storyboard.some((item) => posterKey(item.page))));
      section?.classList.toggle("is-current", current);
      body.hidden = !current;
      if (summary) summary.textContent = stageSummary(number);
      if (tab) {
        tab.classList.toggle("active", current);
        tab.classList.toggle("done", Boolean(complete && !current));
        tab.setAttribute("aria-current", current ? "step" : "false");
      }
    });
  }

  function render() {
    renderTask();
    renderCopy();
    renderVisual();
    renderDelivery();
    renderStageState();
    const tabs = document.querySelectorAll("#wechat-mode-tabs .wechat-mode-tab");
    tabs.forEach((tab) => {
      const active = tab.dataset.mode === state.mode;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    status(state.status.text, state.status.type);
  }

  async function setMode(mode, sourceId = "") {
    state.mode = mode;
    const view = node("wechat-view");
    const longLayout = view?.querySelector(".platform-studio-layout");
    const lab = node("wechat-light-v15");
    if (longLayout) longLayout.hidden = mode === "light";
    if (lab) lab.hidden = mode !== "light";
    render();
    if (mode !== "light") return;
    if (sourceId) state.brief.sourceId = sourceId;
    const preferredVariantId = sourceId ? "" : state.currentVariant?.id || "";
    await loadWorkspace(preferredVariantId);
  }

  function ensure() {
    const view = node("wechat-view");
    if (!view) return;
    injectModeTabs(view);
    injectLab(view);
    if (!state.ready && node("wechat-light-v15")) {
      state.ready = true;
      void setMode("article");
    }
  }

  function boot() {
    ensure();
    const observer = new MutationObserver(ensure);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("x2red:open-wechat-light", (event) => {
      const sourceId = event.detail?.sourceId || "";
      void setMode("light", sourceId);
    });
    document.addEventListener("x2red:sources-refreshed", (event) => {
      const sources = event.detail?.sources;
      if (!Array.isArray(sources) || !state.ready) return;
      state.sources = sources;
      if (!state.sources.some((item) => item.id === state.brief.sourceId)) {
        state.brief.sourceId = state.sources[0]?.id || "";
      }
      if (state.mode === "light") renderTask();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
