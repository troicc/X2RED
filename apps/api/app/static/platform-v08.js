(() => {
  const platformState = {
    catalog: null,
    sources: [],
    materials: [],
    drafts: [],
    variants: [],
    currentVariant: null,
    currentWritingProject: null,
    pipelineInspectionKey: "",
    pipelineActiveKey: "",
    newArticleSession: false,
    busy: false,
    loadToken: 0,
    draftLoadToken: 0,
  };
  const ARTICLE_SOURCE_KEY = "x2red.workspace.wechat.article.source";
  const ARTICLE_SUPPORT_KEY = "x2red.workspace.wechat.article.supporting-sources";
  const ARTICLE_PROJECT_KEY = "x2red.workspace.wechat.deep-writing.project";
  const PIPELINE_FACTS_MEDIA = window.matchMedia("(max-width: 860px)");
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
    ["draft_revision", "已写草稿版本"],
    ["platform_variant", "已写平台版本"],
  ];
  const SOURCE_GROUP_ORDER = Object.fromEntries(SOURCE_GROUPS.map(([id], index) => [id, index]));

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

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function dateText(value) {
    if (!value) return "";
    try { return new Date(value).toLocaleString("zh-CN", { hour12: false }); }
    catch { return String(value); }
  }

  function storedWritingProjectId() {
    try { return window.localStorage.getItem(ARTICLE_PROJECT_KEY) || ""; }
    catch { return ""; }
  }

  function rememberWritingProject(project) {
    platformState.currentWritingProject = project?.id ? project : null;
    try {
      if (project?.id) window.localStorage.setItem(ARTICLE_PROJECT_KEY, project.id);
      else window.localStorage.removeItem(ARTICLE_PROJECT_KEY);
    } catch {
      // Browser storage is optional.
    }
    renderProductionPipeline();
  }

  async function refreshWritingProject(projectId = platformState.currentWritingProject?.id || storedWritingProjectId()) {
    if (!projectId) return null;
    try {
      const project = await apiCall(`/api/writing/projects/${encodeURIComponent(projectId)}`);
      rememberWritingProject(project);
      return project;
    } catch {
      if (projectId === storedWritingProjectId()) rememberWritingProject(null);
      return null;
    }
  }

  function storedArticleSource() {
    try { return window.localStorage.getItem(ARTICLE_SOURCE_KEY) || ""; }
    catch { return ""; }
  }

  function storedSupportingSources() {
    try {
      const value = JSON.parse(window.localStorage.getItem(ARTICLE_SUPPORT_KEY) || "[]");
      return new Set(
        (Array.isArray(value) ? value : [])
          .map((item) => String(item).includes(":") ? String(item) : `source:${item}`),
      );
    } catch { return new Set(); }
  }

  function saveArticleSelection() {
    try {
      window.localStorage.setItem(ARTICLE_SOURCE_KEY, document.getElementById("wechat-source")?.value || "");
      window.localStorage.setItem(
        ARTICLE_SUPPORT_KEY,
        JSON.stringify(selectedMaterialRefs()),
      );
    } catch {
      // The app remains usable when browser storage is disabled.
    }
  }

  function sourceGroup(source) {
    if (source?.provider === "corpus_pool" || source?.content_kind === "corpus_batch") return "pool";
    if (source?.platform === "x" || ["fxtwitter", "signal-studio"].includes(source?.provider)) return "x";
    if (["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"].includes(source?.platform)) return source.platform;
    return "web";
  }

  function sourceLabel(source) {
    const author = source.author_handle ? `@${source.author_handle}` : source.author_name || "来源";
    const copy = String(source.text_original || "").replace(/\s+/g, " ").slice(0, 64);
    return `${author} · ${copy || source.content_kind || "无正文"}`;
  }

  function activeSourceId() {
    return document.getElementById("wechat-source")?.value || "";
  }

  function selectedMaterialRefs(primary = activeSourceId(), root = document) {
    return [...new Set([
      ...(primary ? [`source:${primary}`] : []),
      ...[...root.querySelectorAll('#wechat-supporting-sources input[type="checkbox"]:checked:not(:disabled)')]
        .map((input) => input.value)
        .filter(Boolean),
    ])];
  }

  function materialGroup(material) {
    if (material.kind !== "source") return material.kind;
    return sourceGroup({ platform: material.platform, provider: "", content_kind: "" });
  }

  function materialLabel(material) {
    const version = material.version ? `v${material.version} · ` : "";
    return `${version}${material.title || material.author || "输入材料"} · ${material.excerpt || "无正文"}`;
  }

  function requiredWechatControl(id, root = document) {
    const control = root?.querySelector?.(`#${id}`);
    if (!control || !control.isConnected) {
      throw new Error("公众号工作台组件未加载完整，请刷新页面后重试");
    }
    return control;
  }

  function requiredFormControl(form, id) {
    return requiredWechatControl(id, form);
  }

  function captureWechatCreateForm(form) {
    const source = requiredFormControl(form, "wechat-source");
    const librarySourceId = source.value || "";
    return {
      librarySourceId,
      materialRefs: selectedMaterialRefs(librarySourceId, form),
      pasteTitle: requiredFormControl(form, "wechat-paste-title").value,
      pasteAuthor: requiredFormControl(form, "wechat-paste-author").value,
      pasteUrl: requiredFormControl(form, "wechat-paste-url").value,
      pasteContent: requiredFormControl(form, "wechat-paste-content").value,
      draftId: requiredFormControl(form, "wechat-draft").value,
      theme: requiredFormControl(form, "wechat-theme").value,
      mode: requiredFormControl(form, "wechat-mode").value,
      author: requiredFormControl(form, "wechat-author").value,
      includeCitations: requiredFormControl(form, "wechat-citations").checked,
      includeIllustrationPlan: requiredFormControl(form, "wechat-illustrations").checked,
    };
  }

  function captureWechatEditorForm(form) {
    return {
      title: requiredFormControl(form, "wechat-title").value,
      subtitle: requiredFormControl(form, "wechat-subtitle").value,
      summary: requiredFormControl(form, "wechat-summary").value,
      body_markdown: requiredFormControl(form, "wechat-body").value,
      tags: requiredFormControl(form, "wechat-tags").value,
      theme: requiredWechatControl("wechat-theme").value,
    };
  }

  const ARTICLE_STAGES = [
    {
      key: "input",
      verb: "确定输入",
      title: "冻结材料",
      reads: "素材库、已写版本、粘贴内容",
      writes: "可追溯的材料选择与事实来源",
      optimize: "优化来源覆盖、主来源选择和材料缺口",
      skill: "人工选择",
      targets: ["wechat-source-fieldset"],
      action: "检查输入材料",
    },
    {
      key: "deep",
      verb: "产生中间稿",
      title: "深度研究与审稿",
      navTitle: "深度研究",
      reads: "冻结材料、读者、文章承诺、核心判断",
      writes: "任务单、证据包、大纲、完整初稿与审稿报告",
      optimize: "优化对应 Agent 的 Prompt、模型或阶段反馈",
      skill: "writing.* / review.*",
      targets: ["wechat-deep-writing"],
      action: "进入深度写作",
    },
    {
      key: "article",
      verb: "产生正文",
      title: "公众号完整成稿",
      navTitle: "公众号成稿",
      reads: "原始证据与可选深度终稿",
      writes: "1800—4500 字公众号 PlatformVariant",
      optimize: "优化叙事、章节、标题和完整度门禁",
      skill: "wechat.adapt_longform",
      targets: ["wechat-create-actions"],
      action: "生成公众号成稿",
    },
    {
      key: "edit",
      verb: "修改版本",
      title: "人工编辑与配图",
      navTitle: "人工编辑",
      reads: "当前公众号不可变版本",
      writes: "新版本、逐段 Prompt 与回传图片",
      optimize: "优化正文细节、配图位置和视觉表达",
      skill: "人工编辑 / article.illustration_plan",
      targets: ["wechat-editor"],
      action: "编辑当前版本",
    },
    {
      key: "package",
      verb: "检查交付",
      title: "排版、审核与发布包",
      navTitle: "审核与发布",
      reads: "已确认正文、图片和主题",
      writes: "HTML、封面、预览、manifest 与 ZIP",
      optimize: "优化兼容排版、质量门和人工复核",
      skill: "wechat.format_article / wechat.qa",
      targets: ["wechat-render", "wechat-preview-frame"],
      action: "排版并检查交付",
    },
  ];

  function pipelineStatus() {
    const materialCount = selectedMaterialRefs().length
      + (document.getElementById("wechat-paste-content")?.value.trim() ? 1 : 0);
    const sourceId = activeSourceId();
    const project = platformState.currentWritingProject?.source_id === sourceId
      ? platformState.currentWritingProject
      : null;
    let variant = null;
    if (project?.wechat_variant_id) {
      variant = platformState.variants.find((item) => item.id === project.wechat_variant_id) || null;
    } else if (project) {
      variant = platformState.variants.find((item) => {
        if (item.source_id !== sourceId) return false;
        try {
          return JSON.parse(item.metadata_json || "{}").writing_project_id === project.id;
        } catch {
          return false;
        }
      }) || null;
    } else if (platformState.currentVariant?.source_id === sourceId) {
      variant = platformState.currentVariant;
    }
    const projectRunning = project && !["claims_blocked", "completed", "failed", "canceled"].includes(project.state);
    const projectBlocked = project?.state === "claims_blocked";
    const packaged = variant?.status === "packaged";
    let active = "input";
    if (materialCount) active = projectRunning || projectBlocked ? "deep" : variant ? (packaged ? "package" : "edit") : "article";
    return {
      materialCount,
      project,
      variant,
      projectRunning,
      projectBlocked,
      packaged,
      active,
      viewingCompletedArtifact: Boolean(packaged && !projectRunning),
    };
  }

  function pipelineContext(status) {
    if (status.projectBlocked) {
      return "深度终稿证据闸门阻断 · 候选终稿不能交接公众号";
    }
    if (status.projectRunning) {
      return `正在创作 · ${status.project.current_stage || "深度写作进行中"}`;
    }
    if (status.variant) {
      return status.packaged
        ? `已选成品 · 公众号 v${status.variant.version} · 发布包已生成`
        : `正在编辑 · 公众号 v${status.variant.version}`;
    }
    if (platformState.newArticleSession) {
      return status.materialCount
        ? `新文章 · 已保留旧成品 · ${status.materialCount} 份材料待使用`
        : "新文章 · 已保留旧成品 · 请先选择材料";
    }
    return status.materialCount
      ? `待生成新文章 · ${status.materialCount} 份材料已就绪`
      : "待生成新文章 · 请先选择材料";
  }

  function renderPipelineSummary(status, stage) {
    const progress = document.getElementById("wechat-pipeline-progress");
    const context = document.getElementById("wechat-pipeline-context");
    const start = document.getElementById("wechat-start-new-article");
    if (!progress || !stage) return;
    const inspectedIndex = ARTICLE_STAGES.findIndex((item) => item.key === stage.key);
    progress.textContent = `正在查看阶段 ${Math.max(inspectedIndex + 1, 1)}/5 · ${stage.title}`;
    progress.className = "status-chip neutral";
    if (context) context.textContent = pipelineContext(status);
    if (start) start.hidden = !status.variant && !status.project;
  }

  function stageRoute(stage, status) {
    if (stage.key === "deep" && status.project?.runs?.length) {
      const models = [...new Set(status.project.runs
        .filter((run) => ["succeeded", "degraded"].includes(run.status) && run.model_name)
        .map((run) => `${run.model_name}${run.reasoning_effort ? ` · ${run.reasoning_effort}` : ""}${run.status === "degraded" ? " · 降级输出" : ""}`))];
      return models.length ? `${stage.skill} · ${models.join(" / ")}` : stage.skill;
    }
    if (status.variant && ["article", "package"].includes(stage.key)) {
      try {
        const profile = JSON.parse(status.variant.skill_profile_json || "{}");
        const names = stage.key === "article"
          ? ["wechat.adapt_longform"]
          : ["wechat.format_article", "wechat.qa"];
        const routes = names.map((name) => {
          const binding = profile[name];
          if (!binding) return name;
          const model = binding.model ? ` · ${binding.model}` : " · 确定性";
          const effort = binding.reasoning_effort ? ` · ${binding.reasoning_effort}` : "";
          return `${name}${model}${effort}`;
        });
        return routes.join(" / ");
      } catch {
        return stage.skill;
      }
    }
    return stage.skill;
  }

  function stageState(stage, status) {
    if (stage.key === "input") {
      return status.materialCount
        ? { kind: "complete", label: `${status.materialCount} 份材料` }
        : { kind: "active", label: "当前" };
    }
    if (stage.key === "deep") {
      if (!status.project) return { kind: "optional", label: "可选" };
      if (status.project.state === "completed") {
        return { kind: "complete", label: `终稿 ${status.project.output_draft_chars || 0} 字符` };
      }
      if (status.project.state === "claims_blocked") return { kind: "error", label: "证据阻断" };
      if (status.project.state === "failed") return { kind: "error", label: "需要处理" };
      if (status.project.state.startsWith("awaiting_")) return { kind: "waiting", label: "等你确认" };
      return { kind: "active", label: "进行中" };
    }
    if (stage.key === "article") {
      return status.variant
        ? { kind: "complete", label: `公众号 v${status.variant.version}` }
        : { kind: status.active === "article" ? "active" : "waiting", label: status.active === "article" ? "当前" : "待开始" };
    }
    if (stage.key === "edit") {
      if (!status.variant) return { kind: "waiting", label: "待成稿" };
      return status.packaged
        ? { kind: "complete", label: "已确认版本" }
        : { kind: "active", label: status.variant.created_by === "human" ? "已人工修改" : "可编辑" };
    }
    if (!status.variant) return { kind: "waiting", label: "待成稿" };
    return status.packaged
      ? { kind: "complete", label: "发布包已生成" }
      : { kind: status.active === "package" ? "active" : "waiting", label: "待排版" };
  }

  function pipelineGuidance(status, stageKey = status.active) {
    if (stageKey === "input") {
      const selected = status.materialCount ? `当前已冻结 ${status.materialCount} 份输入。` : "当前还没有可用输入。";
      return ["先把事实边界定清楚", `${selected} 原始来源决定能写什么；已写版本只提供结构和表达，写作偏好不提供事实。`];
    }
    if (stageKey === "deep") {
      const project = status.project;
      return [
        project ? `深度写作 · ${project.current_stage || "准备中"}` : "重要选题再进入深度写作",
        project?.error || (project
          ? "打开现有项目可查看每个 Agent 的读取内容、产物、模型和对应优化入口。"
          : "这是可选阶段。需要证据研究、完整初稿和三路审稿时再进入；普通长文可以直接生成公众号成稿。"),
      ];
    }
    if (stageKey === "article") {
      const base = status.project?.output_draft_id
        ? `将使用深度终稿 v${status.project.output_draft_version || ""}（${status.project.output_draft_chars || 0} 字符）作为基础稿。`
        : "当前会直接依据材料生成公众号完整长文；深度研究阶段可跳过。";
      return ["生成可独立编辑的公众号版本", `${base} 这里决定整体叙事、章节完整度、标题与阅读节奏。`];
    }
    if (stageKey === "edit") {
      return status.variant
        ? ["人工修改永远创建新版本", `正在处理公众号 v${status.variant.version}。正文、标题和配图槽位都可以调整，保存不会覆盖已有历史。`]
        : ["成稿后再进入编辑", "先完成公众号成稿；届时可以修改正文、标题、摘要，并按章节回传配图。"];
    }
    return status.variant
      ? ["最后检查交付而不是自动发布", "生成 HTML、封面、预览、manifest 和 ZIP 后，仍要人工检查事实、引用、版权、水印、异常文字和公众号粘贴效果。"]
      : ["发布包等待公众号版本", "完成公众号成稿与人工编辑后，再统一排版、预览、审核和打包。"];
  }

  function pipelineTarget(stage, status) {
    const targetIds = stage.key === "package" && status.packaged
      ? ["wechat-preview-frame", "wechat-render"]
      : stage.targets;
    return targetIds
      .map((id) => document.getElementById(id))
      .find((target) => target && !target.hidden && target.offsetParent !== null) || null;
  }

  async function scrollToPipelineTarget(stage, status) {
    if (stage.key === "deep" && status.project?.id && window.openX2redWritingProject) {
      await window.openX2redWritingProject(status.project.id);
      return;
    }
    const target = pipelineTarget(stage, status);
    if (!target) return;
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    target.scrollIntoView({ behavior, block: "start" });
    const focusTarget = target.matches("button,input,select,textarea")
      ? target
      : target.querySelector("button,input,select,textarea,[tabindex]");
    focusTarget?.focus({ preventScroll: true });
  }

  function renderPipelineDetail(status, stage) {
    const guidance = document.getElementById("wechat-pipeline-guidance");
    if (!guidance) return;
    const index = ARTICLE_STAGES.findIndex((item) => item.key === stage.key);
    const state = stageState(stage, status);
    const [title, copy] = pipelineGuidance(status, stage.key);
    const head = el("div", "wechat-pipeline-detail-head");
    const heading = el("div", "wechat-pipeline-detail-title");
    heading.append(
      el("span", "wechat-pipeline-detail-kicker", `阶段 ${String(index + 1).padStart(2, "0")} · ${stage.verb}`),
      el("h4", "", stage.title),
    );
    head.append(heading, el("span", `wechat-pipeline-detail-state is-${state.kind}`, state.label));

    const lead = el("div", "wechat-pipeline-detail-lead");
    lead.append(el("strong", "", title), el("p", "", copy));
    const facts = el("details", "wechat-pipeline-facts");
    facts.open = !PIPELINE_FACTS_MEDIA.matches;
    const factsSummary = el("summary", "wechat-pipeline-facts-summary", "查看读取、产出与优化路径");
    const factsGrid = el("div", "wechat-pipeline-detail-grid");
    [["读取", stage.reads], ["产出", stage.writes], ["优化位置", stage.optimize]].forEach(([label, value]) => {
      const item = el("div", "wechat-pipeline-detail-item");
      item.append(el("span", "", label), el("p", "", value));
      factsGrid.appendChild(item);
    });
    facts.append(factsSummary, factsGrid);

    const footer = el("div", "wechat-pipeline-detail-footer");
    const route = el("div", "wechat-pipeline-route");
    route.append(el("span", "", "模型 / Skill"), el("code", "", stageRoute(stage, status)));
    const action = el("button", "secondary-action wechat-pipeline-jump", stage.key === "deep" && status.project ? "打开现有深度写作" : stage.action);
    action.type = "button";
    const canOpenProject = stage.key === "deep" && status.project?.id && window.openX2redWritingProject;
    action.disabled = !canOpenProject && !pipelineTarget(stage, status);
    action.addEventListener("click", () => scrollToPipelineTarget(stage, status));
    footer.append(route, action);
    guidance.replaceChildren(head, lead, facts, footer);
  }

  function syncPipelineFactsDisclosure(event) {
    const facts = document.querySelector(".wechat-pipeline-facts");
    if (facts) facts.open = !event.matches;
  }

  if (PIPELINE_FACTS_MEDIA.addEventListener) {
    PIPELINE_FACTS_MEDIA.addEventListener("change", syncPipelineFactsDisclosure);
  } else {
    PIPELINE_FACTS_MEDIA.addListener(syncPipelineFactsDisclosure);
  }

  function selectPipelineInspection(status, stageKey) {
    const stage = ARTICLE_STAGES.find((item) => item.key === stageKey) || ARTICLE_STAGES[0];
    platformState.pipelineInspectionKey = stage.key;
    document.querySelectorAll(".wechat-pipeline-step").forEach((item) => {
      const inspected = item.dataset.stage === stage.key;
      item.classList.toggle("is-inspected", inspected);
      const button = item.querySelector(".wechat-pipeline-step-button");
      button?.setAttribute("aria-expanded", String(inspected));
    });
    renderPipelineSummary(status, stage);
    renderPipelineDetail(status, stage);
  }

  function renderProductionPipeline() {
    const list = document.getElementById("wechat-pipeline-steps");
    const meter = document.getElementById("wechat-pipeline-meter");
    const pipeline = document.getElementById("wechat-production-pipeline");
    if (!list || !pipeline) return;
    const status = pipelineStatus();
    if (platformState.pipelineActiveKey !== status.active) {
      platformState.pipelineActiveKey = status.active;
      platformState.pipelineInspectionKey = status.active;
    }
    if (!ARTICLE_STAGES.some((stage) => stage.key === platformState.pipelineInspectionKey)) {
      platformState.pipelineInspectionKey = status.active;
    }
    const view = document.getElementById("wechat-view");
    view?.classList.toggle("is-wechat-preflight", !status.variant);
    view?.classList.toggle("is-wechat-editing", Boolean(status.variant && !status.packaged));
    view?.classList.toggle("is-wechat-packaged", Boolean(status.packaged));
    list.replaceChildren();
    ARTICLE_STAGES.forEach((stage, index) => {
      const state = stageState(stage, status);
      const isCurrent = status.active === stage.key && !status.viewingCompletedArtifact;
      const isResult = status.active === stage.key && status.viewingCompletedArtifact;
      const item = el("li", `wechat-pipeline-step is-${state.kind}${isCurrent ? " is-current" : ""}${isResult ? " is-result" : ""}`);
      item.dataset.stage = stage.key;
      const button = el("button", "wechat-pipeline-step-button");
      button.type = "button";
      button.setAttribute("aria-controls", "wechat-pipeline-guidance");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-label", `查看阶段 ${index + 1}：${stage.title}，${state.label}`);
      if (isCurrent) button.setAttribute("aria-current", "step");
      const marker = el("span", "wechat-pipeline-marker", String(index + 1).padStart(2, "0"));
      const copy = el("span", "wechat-pipeline-step-copy");
      copy.append(el("strong", "", stage.navTitle || stage.title), el("small", "", stage.verb));
      button.append(marker, copy, el("span", "wechat-pipeline-state", state.label));
      button.addEventListener("click", () => selectPipelineInspection(status, stage.key));
      item.appendChild(button);
      list.appendChild(item);
    });
    const activeIndex = ARTICLE_STAGES.findIndex((stage) => stage.key === status.active);
    const progressValue = Math.max(activeIndex + 1, 1);
    pipeline.style.setProperty("--wechat-pipeline-progress", `${progressValue / ARTICLE_STAGES.length * 100}%`);
    if (meter) {
      meter.setAttribute("aria-valuenow", String(progressValue));
      meter.setAttribute("aria-valuetext", `第 ${progressValue} 阶段，共 ${ARTICLE_STAGES.length} 阶段`);
    }
    selectPipelineInspection(status, platformState.pipelineInspectionKey);
  }

  function injectNavigation() {
    const nav = document.querySelector(".primary-nav");
    if (!nav || nav.querySelector('[data-view="wechat-view"]')) return;
    const publish = nav.querySelector('[data-view="publish-view"]');
    const button = el("button", "nav-item");
    button.dataset.view = "wechat-view";
    button.innerHTML = '<span class="nav-icon">公</span><span>公众号工作台</span>';
    nav.insertBefore(button, publish);
    button.addEventListener("click", () => window.setView?.("wechat-view"));
  }

  function injectView() {
    const stack = document.querySelector(".view-stack");
    if (!stack || document.getElementById("wechat-view")) return;
    const publish = document.getElementById("publish-view");
    const view = el("section", "app-view");
    view.id = "wechat-view";
    view.innerHTML = `
      <section class="page-intro studio-intro">
        <span id="wechat-view-kicker" class="section-kicker">WECHAT · LONGFORM</span>
        <h2>公众号工作台</h2>
        <p id="wechat-view-description">长文可直接重构，也可进入深度写作；每一步都保留来源、证据和版本。</p>
      </section>
      <section id="wechat-production-pipeline" class="surface wechat-production-pipeline" aria-labelledby="wechat-pipeline-title">
        <div class="wechat-pipeline-head">
          <div><span class="section-kicker">ARTICLE PIPELINE</span><h3 id="wechat-pipeline-title">公众号长文生产线</h3><p>选择阶段查看细节；深度写作可跳过，结果最终汇入公众号版本。</p></div>
          <div class="wechat-pipeline-summary">
            <span id="wechat-pipeline-progress" class="status-chip neutral" role="status">等待选择材料</span>
            <span id="wechat-pipeline-context" class="wechat-pipeline-context">待生成新文章 · 请先选择材料</span>
            <div id="wechat-pipeline-meter" class="wechat-pipeline-meter" role="progressbar" aria-label="公众号长文进度" aria-valuemin="1" aria-valuemax="5" aria-valuenow="1"><span></span></div>
            <button id="wechat-start-new-article" class="secondary-action wechat-start-new-article" type="button" hidden>开始新文章</button>
          </div>
        </div>
        <ol id="wechat-pipeline-steps" class="wechat-pipeline-steps" aria-label="公众号长文生产阶段"></ol>
        <section id="wechat-pipeline-guidance" class="wechat-pipeline-guidance" aria-live="polite" aria-label="所选阶段详情"></section>
      </section>
      <section class="platform-studio-layout">
        <article class="surface platform-panel">
          <div class="panel-heading"><div><span class="section-kicker">STAGE 01 + 03</span><h3>输入材料与公众号成稿</h3></div><button id="wechat-refresh" class="secondary-action" type="button">刷新</button></div>
          <form id="wechat-create-form" class="platform-form">
            <fieldset class="wechat-source-fieldset">
              <legend>内容输入 · 库内材料与粘贴内容可以同时使用</legend>
              <div id="wechat-library-source-panel" class="wechat-source-panel">
                <label>归档主来源<select id="wechat-source"></select></label>
              </div>
              <details id="wechat-paste-source-panel" class="wechat-source-panel wechat-paste-panel">
                <summary><span>补充粘贴材料</span><small>可选 · 按需展开</small></summary>
                <div class="wechat-paste-fields">
                  <label>来源标题<input id="wechat-paste-title" maxlength="200" placeholder="可选；留空则取正文首句" /></label>
                  <label>原作者<input id="wechat-paste-author" maxlength="160" placeholder="可选" /></label>
                  <label>原文链接<input id="wechat-paste-url" maxlength="2000" inputmode="url" placeholder="可选；http(s)://…" /></label>
                  <label>粘贴正文<textarea id="wechat-paste-content" rows="9" maxlength="200000" placeholder="粘贴文章、访谈、笔记或其他合法内容；提交后会进入语料素材库并保留来源记录。"></textarea></label>
                </div>
              </details>
            </fieldset>
            <section class="wechat-supporting-picker" aria-labelledby="wechat-supporting-title">
              <div class="wechat-supporting-head"><strong id="wechat-supporting-title">素材库材料 · 来源与已写版本均可多选</strong><span id="wechat-supporting-count">已选 0 个</span></div>
              <div class="wechat-supporting-tools"><input id="wechat-supporting-search" type="search" placeholder="搜索来源、版本标题或正文" /><button id="wechat-supporting-clear" class="tool-button" type="button">清空附加材料</button></div>
              <div id="wechat-supporting-sources" class="wechat-supporting-list" role="group" aria-label="可多选的库内来源和已写版本"></div>
              <small>直接勾选即可多选，不需要按住 ⌘ 或 Ctrl。库内材料与上方粘贴内容会合并提交；已写版本可提供结构和表达，具体事实仍回溯原始来源。</small>
            </section>
            <label id="wechat-draft-wrap">基础终稿<select id="wechat-draft"><option value="">直接使用来源</option></select></label>
            <div class="platform-form-row">
              <label>成稿方式<select id="wechat-mode"><option value="adapt">重新组织为公众号长文 · 结构可变</option><option value="preserve">保留深度终稿 · 只做公众号适配</option></select></label>
              <label>排版主题<select id="wechat-theme"><option value="auto">自动选择</option></select></label>
            </div>
            <label>作者署名<input id="wechat-author" maxlength="80" placeholder="可选" /></label>
            <div class="platform-checks">
              <label class="platform-check"><input id="wechat-citations" type="checkbox" checked /><span>整理文末来源</span></label>
              <label class="platform-check"><input id="wechat-illustrations" type="checkbox" checked /><span>生成逐段生图 Prompt</span></label>
            </div>
            <p class="platform-helper">不是二选一：库内来源、已写版本和粘贴内容会作为同一批输入。粘贴内容先保存为标准来源；长文完成后，每个章节都会生成可复制的生图 Prompt。</p>
            <div id="wechat-create-actions" class="platform-editor-actions"><span id="wechat-create-status" class="inline-status" role="status"></span><div><button id="wechat-deep-writing" class="secondary-action" type="button">进入阶段 02 · 深度研究与审稿</button><button id="wechat-create-article" class="primary-action" type="submit">生成阶段 03 · 公众号完整成稿</button></div></div>
          </form>
          <div class="panel-heading" style="margin-top:22px"><div><span class="section-kicker">VERSIONS</span><h3>公众号版本</h3></div></div>
          <div id="wechat-variant-list" class="platform-variant-list"></div>
        </article>

        <article class="surface platform-panel">
          <div id="wechat-editor-empty" class="platform-empty"><div><div class="empty-orbit small">公</div><h3>先生成或选择一个公众号版本</h3><p>平台稿、排版结果和封面对都会独立保存版本。</p></div></div>
          <form id="wechat-editor" class="platform-editor" hidden>
            <div class="panel-heading"><div><span class="section-kicker">WECHAT EDITOR</span><h3>公众号文章编辑器</h3></div><span id="wechat-version-state" class="status-chip neutral"></span></div>
            <label>标题<input id="wechat-title" class="platform-title-input" maxlength="160" /></label>
            <label>封面副标题<input id="wechat-subtitle" maxlength="240" /></label>
            <label>摘要<textarea id="wechat-summary" rows="4" maxlength="1000"></textarea></label>
            <label>Markdown 正文<textarea id="wechat-body" maxlength="50000"></textarea></label>
            <label>内部标签<input id="wechat-tags" maxlength="1000" /></label>
            <section id="wechat-visual-handoff" class="wechat-visual-handoff" hidden>
              <div class="wechat-visual-handoff-head"><div><span class="section-kicker">VISUAL HANDOFF</span><h4>逐段生图 Prompt 与回传</h4></div><span id="wechat-visual-progress" class="status-chip neutral"></span></div>
              <p>逐项复制到带生图 Skill 的 Codex；若刚改过标题或正文，请先保存新版本以刷新 Prompt。生成后把图片上传回对应位置，X2RED 会保存到素材库并在重建发布包时带上。</p>
              <div id="wechat-visual-prompt-list" class="wechat-visual-prompt-list"></div>
            </section>
            <div class="platform-editor-actions">
              <span id="wechat-status" class="inline-status"></span>
              <div><button id="wechat-repair" class="secondary-action" type="button" hidden>检查并续写未完成文章</button><button id="wechat-memory" class="secondary-action" type="button">提炼为写作偏好</button><button id="wechat-save" class="secondary-action" type="submit">保存新版本</button><button id="wechat-render" class="primary-action" type="button">排版并生成发布包</button></div>
            </div>
          </form>
        </article>

        <article class="surface platform-preview-panel">
          <div class="platform-preview-head"><div><span class="section-kicker">WECHAT PREVIEW</span><h3>真实粘贴预览</h3></div><a id="wechat-open-preview" class="tool-button" target="_blank" rel="noreferrer" hidden>打开预览 ↗</a></div>
          <div id="wechat-preview-empty" class="platform-empty"><p>排版后在这里预览公众号正文与封面对。</p></div>
          <iframe id="wechat-preview-frame" class="platform-preview-frame" title="公众号文章预览" hidden></iframe>
          <div id="wechat-validation" class="platform-validation" hidden></div>
          <div id="wechat-cover-pair" class="platform-cover-pair" hidden><figure><img id="wechat-cover-wide" alt="公众号 21:9 主封面" /></figure><figure><img id="wechat-cover-square" alt="公众号 1:1 分享封面" /></figure></div>
          <div id="wechat-downloads" class="platform-downloads"></div>
        </article>
      </section>`;
    stack.insertBefore(view, publish);
  }

  const baseSetView = window.setView;
  window.setView = function setPlatformView(viewId) {
    baseSetView?.(viewId);
    if (viewId === "wechat-view") {
      const title = document.getElementById("page-title");
      if (title) title.textContent = "公众号工作台";
      loadWechat().catch((error) => showStatus(error.message, "error"));
    }
  };

  async function loadCatalog() {
    if (platformState.catalog) return platformState.catalog;
    const catalog = await apiCall("/api/platforms/catalog");
    const themeSelect = requiredWechatControl("wechat-theme");
    catalog.wechat_themes.forEach((theme) => {
      const option = document.createElement("option");
      option.value = theme.id;
      option.textContent = theme.label;
      themeSelect.appendChild(option);
    });
    platformState.catalog = catalog;
    return catalog;
  }

  async function loadWechat(preferredSourceId = "") {
    const token = ++platformState.loadToken;
    await loadCatalog();
    const [sources, materials, variants] = await Promise.all([
      apiCall("/api/sources?workspace_state=active"),
      apiCall("/api/writing/material-options?limit=500"),
      apiCall("/api/platforms/variants?platform=wechat"),
    ]);
    if (token !== platformState.loadToken) return;
    platformState.sources = sources;
    platformState.materials = materials;
    platformState.variants = variants;
    fillSources(preferredSourceId);
    await loadDraftsForSource();
    renderVariants();
    if (platformState.currentVariant) {
      const fresh = variants.find((item) => item.id === platformState.currentVariant.id);
      if (fresh) selectVariant(fresh.id);
    }
    if (!platformState.currentWritingProject && storedWritingProjectId()) {
      await refreshWritingProject();
    }
    renderProductionPipeline();
  }

  function fillSources(preferredSourceId = "") {
    const select = requiredWechatControl("wechat-source");
    const supporting = requiredWechatControl("wechat-supporting-sources");
    const current = preferredSourceId
      || (select.dataset.articleSelectionReady === "true" ? select.value : storedArticleSource())
      || select.value;
    const selectedSupporting = supporting.dataset.selectionReady === "true"
      ? new Set(selectedMaterialRefs())
      : storedSupportingSources();
    select.replaceChildren();
    platformState.sources.forEach((source) => {
      const option = document.createElement("option");
      option.value = source.id;
      option.textContent = sourceLabel(source);
      select.appendChild(option);
    });
    if (current && platformState.sources.some((item) => item.id === current)) select.value = current;
    select.dataset.articleSelectionReady = "true";
    renderSupportingSources(selectedSupporting);
    syncSupportingSources();
    saveArticleSelection();
  }

  function renderSupportingSources(selected = new Set()) {
    const box = requiredWechatControl("wechat-supporting-sources");
    box.replaceChildren();
    const groups = new Map(SOURCE_GROUPS.map(([id, label]) => {
      const section = el("section", "wechat-supporting-group");
      section.dataset.group = id;
      section.appendChild(el("strong", "wechat-supporting-group-title", label));
      section.appendChild(el("div", "wechat-supporting-group-items"));
      return [id, section];
    }));
    platformState.materials
      .slice()
      .sort((left, right) => SOURCE_GROUP_ORDER[materialGroup(left)] - SOURCE_GROUP_ORDER[materialGroup(right)])
      .forEach((material) => {
        const row = el("label", "wechat-supporting-option");
        row.dataset.search = materialLabel(material).toLowerCase();
        row.dataset.sourceId = material.source_id;
        row.dataset.materialRef = material.ref;
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = material.ref;
        input.dataset.kind = material.kind;
        input.dataset.sourceId = material.source_id;
        input.checked = selected.has(material.ref);
        input.addEventListener("change", () => {
          updateSupportingCount();
          saveArticleSelection();
          renderProductionPipeline();
        });
        const copy = el("span", "wechat-supporting-copy");
        const kindLabel = material.kind === "source" ? "来源" : material.kind === "draft_revision" ? "草稿版本" : "平台版本";
        const version = material.version ? ` · v${material.version}` : "";
        copy.appendChild(el("strong", "", `${kindLabel}${version} · ${material.title || material.author || "未命名"}`));
        copy.appendChild(el("small", "", material.excerpt || "无正文"));
        row.append(input, copy);
        groups.get(materialGroup(material)).querySelector(".wechat-supporting-group-items").appendChild(row);
      });
    groups.forEach((section) => {
      if (section.querySelector(".wechat-supporting-option")) box.appendChild(section);
    });
    box.dataset.selectionReady = "true";
    filterSupportingSources();
    updateSupportingCount();
  }

  function filterSupportingSources() {
    const query = document.getElementById("wechat-supporting-search")?.value.trim().toLowerCase() || "";
    document.querySelectorAll("#wechat-supporting-sources .wechat-supporting-group").forEach((group) => {
      let visible = 0;
      group.querySelectorAll(".wechat-supporting-option").forEach((row) => {
        const show = !query || row.dataset.search.includes(query);
        row.hidden = !show;
        if (show) visible += 1;
      });
      group.hidden = visible === 0;
    });
  }

  function updateSupportingCount() {
    const count = selectedMaterialRefs().filter((ref) => ref !== `source:${activeSourceId()}`).length;
    const target = document.getElementById("wechat-supporting-count");
    if (target) target.textContent = `已选 ${count} 个`;
    renderProductionPipeline();
  }

  function syncSupportingSources() {
    const primary = activeSourceId() || document.getElementById("wechat-source")?.value || "";
    const supporting = document.getElementById("wechat-supporting-sources");
    supporting?.querySelectorAll('input[type="checkbox"]').forEach((input) => {
      input.disabled = input.value === `source:${primary}`;
      if (input.disabled) input.checked = false;
      input.closest(".wechat-supporting-option")?.classList.toggle("is-primary", input.disabled);
    });
    updateSupportingCount();
  }

  async function materializePastedSource(formValues) {
    const text = formValues.pasteContent.trim();
    if (!text) return "";
    if (text.length < 20) throw new Error("粘贴材料请至少输入 20 个字符，或留空只使用库内材料");
    const source = await apiCall("/api/sources/manual", {
      method: "POST",
      body: JSON.stringify({
        title: formValues.pasteTitle,
        author_name: formValues.pasteAuthor,
        canonical_url: formValues.pasteUrl,
        text_original: text,
      }),
    });
    const index = platformState.sources.findIndex((item) => item.id === source.id);
    if (index >= 0) platformState.sources[index] = source;
    else platformState.sources.unshift(source);
    document.dispatchEvent(new CustomEvent("x2red:sources-refreshed", {
      detail: { sources: platformState.sources },
    }));
    return source.id;
  }

  async function resolveInputMaterials(formValues) {
    const librarySourceId = formValues.librarySourceId;
    const pastedSourceId = await materializePastedSource(formValues);
    const sourceId = librarySourceId || pastedSourceId;
    if (!sourceId) throw new Error("请至少选择一个库内材料或粘贴一段内容");
    const refs = [...new Set([
      ...(librarySourceId ? [`source:${librarySourceId}`] : []),
      ...formValues.materialRefs,
      ...(pastedSourceId ? [`source:${pastedSourceId}`] : []),
    ])];
    const supportingSourceIds = refs
      .filter((ref) => ref.startsWith("source:"))
      .map((ref) => ref.replace(/^source:/, ""))
      .filter((id) => id !== sourceId);
    return { sourceId, materialRefs: refs, supportingSourceIds, pastedSourceId };
  }

  async function loadDraftsForSource(preferredDraftId = "") {
    const sourceId = activeSourceId();
    const token = ++platformState.draftLoadToken;
    const select = requiredWechatControl("wechat-draft");
    select.replaceChildren(new Option("直接使用来源", ""));
    platformState.drafts = [];
    const drafts = sourceId ? await apiCall(`/api/sources/${encodeURIComponent(sourceId)}/drafts`) : [];
    if (!select.isConnected || token !== platformState.draftLoadToken || sourceId !== activeSourceId()) return;
    platformState.drafts = drafts;
    platformState.drafts.forEach((draft) => {
      const option = document.createElement("option");
      option.value = draft.id;
      option.textContent = `v${draft.version} · ${draft.title || "未命名终稿"} · ${draft.created_by}`;
      select.appendChild(option);
    });
    if (preferredDraftId && platformState.drafts.some((item) => item.id === preferredDraftId)) {
      select.value = preferredDraftId;
    } else if (platformState.drafts.length) {
      select.value = platformState.drafts[0].id;
    }
  }

  function renderVariants() {
    const box = requiredWechatControl("wechat-variant-list");
    box.replaceChildren();
    const sourceId = activeSourceId();
    const values = platformState.variants.filter((item) => !sourceId || item.source_id === sourceId);
    if (!values.length) {
      box.appendChild(el("div", "card-empty", "这个来源还没有公众号版本。"));
      return;
    }
    values.forEach((variant) => {
      const button = el("button", `platform-variant-item${platformState.currentVariant?.id === variant.id ? " active" : ""}`);
      button.type = "button";
      button.dataset.variantId = variant.id;
      button.innerHTML = `<strong>${variant.title || "未命名公众号版本"}</strong><span>v${variant.version} · ${variant.theme} · ${variant.status}</span><small>${dateText(variant.updated_at)}</small>`;
      button.addEventListener("click", () => selectVariant(variant.id));
      box.appendChild(button);
    });
  }

  function clearSelectedVariant() {
    platformState.currentVariant = null;
    const editor = document.getElementById("wechat-editor");
    if (editor) delete editor.dataset.currentVariantId;
    document.getElementById("wechat-editor-empty").hidden = false;
    document.getElementById("wechat-editor").hidden = true;
    document.getElementById("wechat-preview-empty").hidden = false;
    document.getElementById("wechat-preview-frame").hidden = true;
    document.getElementById("wechat-validation").hidden = true;
    document.getElementById("wechat-cover-pair").hidden = true;
    document.getElementById("wechat-downloads").replaceChildren();
    document.getElementById("wechat-visual-handoff").hidden = true;
    document.getElementById("wechat-visual-prompt-list").replaceChildren();
    document.getElementById("wechat-repair").hidden = true;
    renderProductionPipeline();
  }

  function editorHasUnsavedChanges() {
    const variant = platformState.currentVariant;
    const form = document.getElementById("wechat-editor");
    if (!variant || !form || form.hidden) return false;
    const values = captureWechatEditorForm(form);
    return values.title !== (variant.title || "")
      || values.subtitle !== (variant.subtitle || "")
      || values.summary !== (variant.summary || "")
      || values.body_markdown !== (variant.body_markdown || "")
      || values.tags !== (variant.tags || "")
      || values.theme !== (variant.theme || "auto");
  }

  function startNewArticle() {
    if (platformState.busy) return;
    if (editorHasUnsavedChanges() && !window.confirm("当前编辑框有尚未保存的修改。开始新文章会放弃这些未保存修改，但不会删除任何已保存版本。是否继续？")) {
      return;
    }
    rememberWritingProject(null);
    platformState.newArticleSession = true;
    platformState.pipelineActiveKey = "";
    platformState.pipelineInspectionKey = selectedMaterialRefs().length ? "article" : "input";
    clearSelectedVariant();
    renderVariants();
    const draft = document.getElementById("wechat-draft");
    const mode = document.getElementById("wechat-mode");
    if (draft) draft.value = "";
    if (mode) mode.value = "adapt";
    const emptyTitle = document.querySelector("#wechat-editor-empty h3");
    const emptyCopy = document.querySelector("#wechat-editor-empty p");
    if (emptyTitle) emptyTitle.textContent = "正在准备一篇新文章";
    if (emptyCopy) emptyCopy.textContent = "旧成品仍在版本列表中；确认材料后进入阶段 02，或直接生成阶段 03。";
    const status = document.getElementById("wechat-create-status");
    if (status) {
      status.textContent = "已退出旧成品；所有历史版本均已保留。";
      status.className = "inline-status ok";
    }
    const createForm = document.getElementById("wechat-create-form");
    const collapsedRegion = createForm?.closest(".ui-region-collapsible.is-collapsed");
    collapsedRegion?.querySelector(".ui-region-toggle")?.click();
    const target = document.getElementById("wechat-create-actions");
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    target?.scrollIntoView({ behavior, block: "center" });
    document.getElementById("wechat-deep-writing")?.focus({ preventScroll: true });
  }

  function selectVariant(variantId) {
    const variant = platformState.variants.find((item) => item.id === variantId);
    if (!variant) return;
    const form = requiredWechatControl("wechat-editor");
    const title = requiredFormControl(form, "wechat-title");
    const subtitle = requiredFormControl(form, "wechat-subtitle");
    const summary = requiredFormControl(form, "wechat-summary");
    const body = requiredFormControl(form, "wechat-body");
    const tags = requiredFormControl(form, "wechat-tags");
    const theme = requiredWechatControl("wechat-theme");
    platformState.currentVariant = variant;
    platformState.newArticleSession = false;
    document.getElementById("wechat-editor-empty").hidden = true;
    form.hidden = false;
    form.dataset.currentVariantId = variant.id;
    title.value = variant.title;
    subtitle.value = variant.subtitle;
    summary.value = variant.summary;
    body.value = variant.body_markdown;
    tags.value = variant.tags;
    theme.value = variant.theme || "auto";
    const state = document.getElementById("wechat-version-state");
    state.textContent = `v${variant.version} · ${variant.status}`;
    state.className = `status-chip ${variant.status === "failed" ? "error" : variant.status === "packaged" ? "ok" : "neutral"}`;
    const repair = document.getElementById("wechat-repair");
    repair.hidden = !articleLooksIncomplete(variant);
    renderVariants();
    renderVisualHandoff(variant);
    renderOutputs(variant);
    renderProductionPipeline();
  }

  function articleLooksIncomplete(variant) {
    const body = String(variant?.body_markdown || "").trim();
    if (!body) return true;
    if (body.split("```").length % 2 === 0) return true;
    if (!/[。！？!?…）》」』)\]]$/.test(body)) return true;
    let insideFence = false;
    let codeRun = 0;
    for (const line of body.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        insideFence = !insideFence;
        codeRun = 0;
        continue;
      }
      if (insideFence || !trimmed) continue;
      if (/^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s|[\u3400-\u9fff])/.test(trimmed)) {
        codeRun = 0;
        continue;
      }
      if (/(?:=|\(|\)|\[|\]|\{|\}|:|;|->)/.test(trimmed)) {
        codeRun += 1;
        if (codeRun >= 3) return true;
      } else {
        codeRun = 0;
      }
    }
    let metadata = {};
    try { metadata = JSON.parse(variant.metadata_json || "{}"); } catch {}
    const headings = new Set(
      [...body.matchAll(/^##\s+(.+?)\s*$/gm)].map((match) => match[1].replace(/\s+/g, "").toLowerCase()),
    );
    return (metadata.illustration_plan || []).some((item) => {
      const heading = String(item?.after_heading || "").replace(/\s+/g, "").toLowerCase();
      return heading && !headings.has(heading);
    });
  }

  function renderVisualHandoff(variant) {
    const section = document.getElementById("wechat-visual-handoff");
    const list = document.getElementById("wechat-visual-prompt-list");
    let metadata = {};
    try { metadata = JSON.parse(variant.metadata_json || "{}"); } catch {}
    const prompts = Array.isArray(metadata.visual_prompts) ? metadata.visual_prompts : [];
    section.hidden = prompts.length === 0;
    list.replaceChildren();
    if (!prompts.length) return;
    const ready = prompts.filter((item) => item.asset_id).length;
    const progress = document.getElementById("wechat-visual-progress");
    progress.textContent = `已回传 ${ready}/${prompts.length}`;
    progress.className = `status-chip ${ready === prompts.length ? "ok" : "neutral"}`;
    prompts.forEach((item) => {
      const card = el("article", "wechat-visual-prompt-card");
      const top = el("div", "wechat-visual-prompt-top");
      const copy = el("div");
      copy.appendChild(el("strong", "", item.label || item.slot_id || "配图"));
      copy.appendChild(el("small", "", `${item.placement || "待确认位置"} · ${item.aspect_ratio || "按 Prompt"}`));
      top.append(copy, el("span", `wechat-visual-prompt-status${item.asset_id ? " ready" : ""}`, item.asset_id ? "已入素材库" : "待回传"));
      const prompt = document.createElement("textarea");
      prompt.readOnly = true;
      prompt.value = item.prompt || "";
      prompt.setAttribute("aria-label", `${item.label || "配图"} Prompt`);
      const actions = el("div", "wechat-visual-prompt-actions");
      const copyButton = el("button", "", "复制 Prompt");
      copyButton.type = "button";
      copyButton.addEventListener("click", () => copyVisualPrompt(prompt, copyButton));
      const uploadLabel = el("label", "", item.asset_id ? "替换成图" : "上传成图");
      const upload = document.createElement("input");
      upload.type = "file";
      upload.accept = "image/png,image/jpeg,image/webp";
      upload.addEventListener("change", () => {
        const file = upload.files?.[0];
        if (file) uploadVisual(item.slot_id, file);
        upload.value = "";
      });
      uploadLabel.appendChild(upload);
      actions.append(copyButton, uploadLabel);
      card.append(top, prompt, actions);
      if (item.asset_id) {
        const preview = el("div", "wechat-visual-preview");
        const image = document.createElement("img");
        image.src = `/api/assets/${encodeURIComponent(item.asset_id)}/file?v=${Date.now()}`;
        image.alt = item.alt_text || item.label || "已回传配图";
        const link = el("a", "", "查看 / 下载已回传图片 ↗");
        link.href = `/api/assets/${encodeURIComponent(item.asset_id)}/file`;
        link.target = "_blank";
        link.rel = "noreferrer";
        preview.append(image, link);
        card.appendChild(preview);
      }
      list.appendChild(card);
    });
  }

  async function copyVisualPrompt(textarea, button) {
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(textarea.value);
    } catch {
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      textarea.setSelectionRange(0, 0);
    }
    button.textContent = "已复制";
    window.setTimeout(() => { button.textContent = original; }, 1400);
  }

  async function uploadVisual(slotId, file) {
    if (!platformState.currentVariant || platformState.busy) return;
    setBusy(true, `正在回传 ${file.name} 到素材库…`);
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch(
        `/api/platforms/variants/${encodeURIComponent(platformState.currentVariant.id)}/visuals/${encodeURIComponent(slotId)}`,
        { method: "POST", body: form },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `上传失败：${response.status}`);
      }
      const variant = await response.json();
      const index = platformState.variants.findIndex((item) => item.id === variant.id);
      if (index >= 0) platformState.variants[index] = variant;
      else platformState.variants.unshift(variant);
      selectVariant(variant.id);
      showStatus("图片已回传素材库。请重新生成发布包以写入预览和 ZIP。", "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function renderOutputs(variant) {
    let files = {};
    let metadata = {};
    try { files = JSON.parse(variant.output_paths_json || "{}"); } catch {}
    try { metadata = JSON.parse(variant.metadata_json || "{}"); } catch {}
    const hasPreview = Boolean(files.preview);
    document.getElementById("wechat-preview-empty").hidden = hasPreview;
    const frame = document.getElementById("wechat-preview-frame");
    frame.hidden = !hasPreview;
    const open = document.getElementById("wechat-open-preview");
    open.hidden = !hasPreview;
    if (hasPreview) {
      const previewUrl = `/api/platforms/variants/${encodeURIComponent(variant.id)}/preview?v=${Date.now()}`;
      frame.src = previewUrl;
      open.href = previewUrl;
    }
    const coverPair = document.getElementById("wechat-cover-pair");
    const hasCovers = Boolean(files.wide && files.square);
    coverPair.hidden = !hasCovers;
    if (hasCovers) {
      document.getElementById("wechat-cover-wide").src = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/wide?v=${Date.now()}`;
      document.getElementById("wechat-cover-square").src = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/square?v=${Date.now()}`;
    }
    const validation = document.getElementById("wechat-validation");
    const warnings = metadata.validation?.warnings || [];
    validation.hidden = !hasPreview;
    validation.className = `platform-validation${warnings.length ? " warning" : ""}`;
    validation.textContent = warnings.length ? `排版通过，仍有 ${warnings.length} 条建议：${warnings.join("；")}` : "公众号 HTML 确定性校验已通过。";
    const downloads = document.getElementById("wechat-downloads");
    downloads.replaceChildren();
    const labels = { markdown: "Markdown", html: "干净 HTML", preview: "预览页", wide: "21:9 封面", square: "1:1 封面", visual_handoff: "配图交接清单", manifest: "清单", package: "下载发布包 ZIP" };
    Object.keys(files).forEach((key) => {
      const visualLabel = key.startsWith("visual_") && key !== "visual_handoff"
        ? `回传图 · ${key.replace(/^visual_/, "")}`
        : "";
      const link = el("a", "", labels[key] || visualLabel || key);
      link.href = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/${encodeURIComponent(key)}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      downloads.appendChild(link);
    });
  }

  function showStatus(text, kind = "") {
    const target = document.getElementById("wechat-status");
    if (!target) return;
    target.textContent = text;
    target.className = `inline-status${kind ? ` ${kind}` : ""}`;
  }

  function setBusy(value, text = "") {
    platformState.busy = value;
    document.getElementById("wechat-view")?.classList.toggle("platform-busy", value);
    if (text) showStatus(text);
    renderProductionPipeline();
  }

  async function createVariant(event) {
    event.preventDefault();
    if (platformState.busy) return;
    let formValues;
    try {
      formValues = captureWechatCreateForm(event.currentTarget);
    } catch (error) {
      showStatus(error.message, "error");
      return;
    }
    setBusy(true, formValues.pasteContent.trim() ? "正在合并库内材料与粘贴内容…" : "正在调用平台适配 Skill，生成公众号版本…");
    try {
      const inputs = await resolveInputMaterials(formValues);
      showStatus("正在调用平台适配 Skill，生成公众号版本…");
      const variant = await apiCall("/api/platforms/wechat/variants", {
        method: "POST",
        body: JSON.stringify({
          source_id: inputs.sourceId,
          supporting_source_ids: inputs.supportingSourceIds,
          material_refs: inputs.materialRefs,
          draft_id: inputs.sourceId === formValues.librarySourceId
            ? formValues.draftId || null
            : null,
          theme: formValues.theme,
          mode: formValues.mode,
          include_citations: formValues.includeCitations,
          include_illustration_plan: formValues.includeIllustrationPlan,
          author: formValues.author,
        }),
      });
      platformState.variants.unshift(variant);
      platformState.newArticleSession = false;
      selectVariant(variant.id);
      if (platformState.currentWritingProject?.id) await refreshWritingProject();
      showStatus("公众号版本已生成。检查正文后再排版。", "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveVariant(event) {
    event.preventDefault();
    if (!platformState.currentVariant || platformState.busy) return;
    let payload;
    try {
      payload = captureWechatEditorForm(event.currentTarget);
    } catch (error) {
      showStatus(error.message, "error");
      return;
    }
    setBusy(true, "正在保存新的公众号版本…");
    try {
      const revised = await apiCall(`/api/platforms/variants/${encodeURIComponent(platformState.currentVariant.id)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      platformState.variants.unshift(revised);
      selectVariant(revised.id);
      showStatus(`已保存为公众号 v${revised.version}。`, "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function repairIncompleteVariant() {
    if (!platformState.currentVariant || platformState.busy) return;
    setBusy(true, "正在核对来源并完整重写被截断的文章…");
    try {
      const repaired = await apiCall(
        `/api/platforms/variants/${encodeURIComponent(platformState.currentVariant.id)}/repair-incomplete`,
        { method: "POST" },
      );
      platformState.variants.unshift(repaired);
      selectVariant(repaired.id);
      showStatus(`已保存为完整修复版 v${repaired.version}；旧版本保持不变。`, "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function editorValues() {
    return captureWechatEditorForm(requiredWechatControl("wechat-editor"));
  }

  async function openMemoryCandidate() {
    if (!platformState.currentVariant || platformState.busy) return;
    setBusy(true, "正在先冻结当前编辑框内容…");
    try {
      let variant = platformState.currentVariant;
      const payload = editorValues();
      const changed = ["title", "subtitle", "summary", "body_markdown", "tags", "theme"]
        .some((key) => String(variant[key] || "") !== String(payload[key] || ""));
      if (changed) {
        variant = await apiCall(`/api/platforms/variants/${encodeURIComponent(variant.id)}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        platformState.variants.unshift(variant);
        selectVariant(variant.id);
      }
      document.dispatchEvent(new CustomEvent("x2red:memory-source", {
        detail: { kind: "platform_variant", id: variant.id },
      }));
      showStatus(`已冻结为公众号 v${variant.version}，请检查记忆候选。`, "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function renderVariant() {
    if (!platformState.currentVariant || platformState.busy) return;
    setBusy(true, "正在生成内联 HTML、封面对和 ZIP 发布包…");
    try {
      const result = await apiCall(`/api/platforms/variants/${encodeURIComponent(platformState.currentVariant.id)}/render`, {
        method: "POST",
        body: JSON.stringify({ package: true }),
      });
      const index = platformState.variants.findIndex((item) => item.id === result.variant.id);
      if (index >= 0) platformState.variants[index] = result.variant;
      else platformState.variants.unshift(result.variant);
      selectVariant(result.variant.id);
      showStatus(result.validation.warnings.length ? "发布包已生成，请查看排版建议。" : "发布包已生成并通过校验。", "ok");
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function applyProjectMaterials(project) {
    if (!project?.id) return;
    const desired = new Set(
      (project.material_summaries || []).map((item) => item.ref).filter(Boolean),
    );
    if (project.output_draft_id) desired.add(`draft:${project.output_draft_id}`);
    document.querySelectorAll('#wechat-supporting-sources input[type="checkbox"]').forEach((input) => {
      input.checked = desired.has(input.value);
    });
    syncSupportingSources();
    updateSupportingCount();
    saveArticleSelection();
    const mode = document.getElementById("wechat-mode");
    if (mode && project.output_draft_id) mode.value = "preserve";
  }

  async function openWechatForSource(sourceId, draftId = "", variantId = "") {
    window.setView?.("wechat-view");
    await loadWechat(sourceId);
    const source = requiredWechatControl("wechat-source");
    if (sourceId && [...source.options].some((option) => option.value === sourceId)) {
      source.value = sourceId;
      syncSupportingSources();
      saveArticleSelection();
    }
    await loadDraftsForSource(draftId);
    renderVariants();
    if (variantId && platformState.variants.some((item) => item.id === variantId)) {
      selectVariant(variantId);
    }
    renderProductionPipeline();
    document.getElementById("wechat-create-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  window.openX2redWechatForProject = async (project) => {
    if (!project?.id || !project.source_id) {
      throw new Error("深度写作项目缺少来源或项目 ID，无法进入公众号成稿阶段");
    }
    const fresh = await refreshWritingProject(project.id) || project;
    rememberWritingProject(fresh);
    await openWechatForSource(
      fresh.source_id,
      fresh.output_draft_id || "",
      fresh.wechat_variant_id || "",
    );
    applyProjectMaterials(fresh);
    await loadDraftsForSource(fresh.output_draft_id || "");
    if (fresh.wechat_variant_id) selectVariant(fresh.wechat_variant_id);
    renderProductionPipeline();
  };

  function bindEvents() {
    document.getElementById("wechat-create-form").addEventListener("submit", createVariant);
    document.getElementById("wechat-editor").addEventListener("submit", saveVariant);
    document.getElementById("wechat-memory").addEventListener("click", openMemoryCandidate);
    document.getElementById("wechat-render").addEventListener("click", renderVariant);
    document.getElementById("wechat-repair").addEventListener("click", repairIncompleteVariant);
    document.getElementById("wechat-refresh").addEventListener("click", () => {
      loadWechat().catch((error) => showStatus(error.message, "error"));
    });
    document.getElementById("wechat-start-new-article").addEventListener("click", startNewArticle);
    document.getElementById("wechat-deep-writing").addEventListener("click", async (event) => {
      if (platformState.busy) return;
      let formValues;
      try {
        formValues = captureWechatCreateForm(event.currentTarget.closest("form"));
      } catch (error) {
        showStatus(error.message, "error");
        return;
      }
      setBusy(true, formValues.pasteContent.trim() ? "正在合并库内材料与粘贴内容…" : "正在打开深度写作…");
      try {
        const inputs = await resolveInputMaterials(formValues);
        await window.openX2redDeepWriting?.(
          inputs.sourceId,
          inputs.supportingSourceIds,
          inputs.materialRefs,
        );
        showStatus("");
      } catch (error) {
        showStatus(error.message, "error");
      } finally {
        setBusy(false);
      }
    });
    document.getElementById("wechat-supporting-search").addEventListener("input", filterSupportingSources);
    let pasteRenderTimer = 0;
    document.getElementById("wechat-paste-content").addEventListener("input", () => {
      window.clearTimeout(pasteRenderTimer);
      pasteRenderTimer = window.setTimeout(renderProductionPipeline, 120);
    });
    document.getElementById("wechat-draft").addEventListener("change", renderProductionPipeline);
    document.getElementById("wechat-supporting-clear").addEventListener("click", () => {
      document.querySelectorAll('#wechat-supporting-sources input[type="checkbox"]:checked').forEach((input) => {
        input.checked = false;
      });
      updateSupportingCount();
      saveArticleSelection();
    });
    document.getElementById("wechat-source").addEventListener("change", async () => {
      const sourceId = activeSourceId();
      try {
        syncSupportingSources();
        saveArticleSelection();
        rememberWritingProject(null);
        platformState.newArticleSession = true;
        clearSelectedVariant();
        renderVariants();
        await loadDraftsForSource();
        if (sourceId !== activeSourceId()) return;
        renderVariants();
      } catch (error) {
        showStatus(error.message, "error");
      }
    });
    syncSupportingSources();
  }

  function injectSkillPacks() {
    const settingsGrid = document.querySelector("#settings-view .settings-grid");
    if (!settingsGrid || document.getElementById("skill-pack-list")) return;
    const card = el("article", "surface settings-card wide");
    card.innerHTML = `<div class="panel-heading"><div><span class="section-kicker">CURATED SKILL PACKS</span><h3>平台能力包</h3><p class="helper-copy">每个能力包控制一组实际 Skill。AGPL 来源只做独立重写或外置检测，不复制第三方模板和资产。</p></div><button id="refresh-skill-packs" class="secondary-action" type="button">刷新</button></div><div id="skill-pack-list" class="skill-pack-grid"></div>`;
    settingsGrid.appendChild(card);
    document.getElementById("refresh-skill-packs").addEventListener("click", loadSkillPacks);
  }

  async function loadSkillPacks() {
    const box = document.getElementById("skill-pack-list");
    if (!box) return;
    box.textContent = "正在读取能力包…";
    try {
      const packs = await apiCall("/api/settings/skill-packs");
      box.replaceChildren();
      packs.forEach((pack) => {
        const card = el("article", `skill-pack-card${pack.enabled ? " enabled" : ""}`);
        const top = el("div", "skill-pack-top");
        const copy = el("div");
        copy.innerHTML = `<h4>${pack.label}</h4><small>${pack.platform} · ${pack.integration_mode}</small>`;
        const toggle = document.createElement("input");
        toggle.type = "checkbox";
        toggle.className = "skill-pack-toggle";
        toggle.checked = pack.enabled;
        toggle.title = "启用或关闭整套能力";
        toggle.addEventListener("change", async () => {
          toggle.disabled = true;
          try {
            const updated = await apiCall(`/api/settings/skill-packs/${encodeURIComponent(pack.id)}`, {
              method: "PUT",
              body: JSON.stringify({ enabled: toggle.checked }),
            });
            card.classList.toggle("enabled", updated.enabled);
          } catch (error) {
            toggle.checked = !toggle.checked;
            window.alert(error.message);
          } finally { toggle.disabled = false; }
        });
        top.append(copy, toggle);
        const description = el("p", "skill-pack-copy", pack.description);
        const meta = el("div", "skill-pack-meta");
        [...pack.licenses, ...pack.skills.slice(0, 4)].forEach((value) => meta.appendChild(el("span", "", value)));
        const sources = el("div", "skill-pack-sources");
        pack.source_repositories.forEach((repo) => {
          const link = el("a", "", repo);
          link.href = `https://github.com/${repo}`;
          link.target = "_blank";
          link.rel = "noreferrer";
          sources.appendChild(link);
        });
        const note = el("small", "platform-helper", `${pack.notes}${pack.installed_paths.length ? ` · 已检测到：${pack.installed_paths.join(", ")}` : ""}`);
        card.append(top, description, meta, sources, note);
        box.appendChild(card);
      });
    } catch (error) {
      box.textContent = error.message;
    }
  }

  const previousFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await previousFetch(...args);
    try {
      const url = new URL(typeof args[0] === "string" ? args[0] : args[0]?.url || "", window.location.href);
      const method = args[1]?.method || "GET";
      if (response.ok && method.toUpperCase() === "GET" && /^\/api\/writing\/projects\/[^/]+$/.test(url.pathname)) {
        response.clone().json().then((project) => {
          rememberWritingProject(project);
        }).catch(() => {});
      }
    } catch {}
    return response;
  };

  function boot() {
    injectNavigation();
    injectView();
    injectSkillPacks();
    bindEvents();
    renderProductionPipeline();
    document.querySelector('[data-view="settings-view"]')?.addEventListener("click", loadSkillPacks);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
